"""Servidor HTTP local autoalojado para GuarIdA (100% offline, sin dependencias externas)."""

import hashlib
import json
import os
import secrets
import shutil
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import psutil

from guarida_manager import DIRECTORIO_LOGS, menu_actions
from guarida_manager.cache import GestorCache
from guarida_manager.chat import (
    ClienteTensoresChat,
    _es_error_bind_puerto,
    _esperar_servidor_chat,
    _leer_log_desde,
    _sincronizar_puerto,
    _tamano_archivo_seguro,
    calcular_metricas_interaccion,
    extraer_hechos_declarativos,
    medir_tokens_mensaje,
    obtener_parejas_recomendadas,
)
from guarida_manager.comparator import ComparadorModelosHardware
from guarida_manager.downloader.models import CatalogoModelos, DescargadorModelos
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.engine import ClienteLlamaOffline, GestorLlamaServer, LlamaServerConfig
from guarida_manager.engine.server import asegurar_puerto_disponible, puerto_esta_disponible
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.logger import inicializar_logging, obtener_logger
from guarida_manager.proyectos import GestorProyectos
from guarida_manager.telemetry import MetricasTelemetria, MonitorTelemetriaHardware

logger = obtener_logger("web")

DIRECTORIO_STATIC = Path(__file__).resolve().parent / "static"

_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def _cliente_disponible(cli: Any) -> bool:
    """Comprueba disponibilidad tanto para ClienteLlamaOffline como para ClienteTensoresChat."""
    try:
        return bool(cli.esta_disponible(timeout=0.15))
    except TypeError:
        return bool(cli.esta_disponible())
    except Exception:
        return False


def _serializar_json(valor: Any) -> Any:
    if is_dataclass(valor):
        return asdict(valor)
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _serializar_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializar_json(v) for v in valor]
    return valor


class ControladorWebGuarida:
    """Orquestador de estado, proyectos, modelos, memoria e inferencia para la UI web."""

    def __init__(
        self,
        gestor_cache: Optional[GestorCache] = None,
        gestor_server: Optional[GestorLlamaServer] = None,
        cliente: Optional[Any] = None,
    ) -> None:
        self.cache = gestor_cache or GestorCache()
        self.gestor_server = gestor_server or GestorLlamaServer(gestor_cache=self.cache)
        host = getattr(self.gestor_server, "host", None) or "127.0.0.1"
        port = getattr(self.gestor_server, "port", None) or 8083
        self.cliente: Any = cliente or ClienteLlamaOffline(host=host, port=port, timeout=300.0)
        self.proyectos = GestorProyectos(gestor_cache=self.cache)
        self.modelo_activo_id: Optional[str] = None
        self.motor_emb_id: str = "bge-m3-q4"
        self._lock_motor = threading.Lock()
        self._hw_info: Optional[Any] = None
        self._parejas_cache: Optional[list[dict[str, Any]]] = None
        self._catalogo_cache: Optional[list[dict[str, Any]]] = None
        self._temp_cache: tuple[float, Optional[float]] = (0.0, None)
        self._lock_web = threading.Lock()
        self.cliente_web_conectado: bool = False
        self.ultimo_latido_web: float = 0.0
        self.cierre_pendiente_ts: Optional[float] = None
        self.evento_cierre_web = threading.Event()
        self.peticiones_activas: int = 0

    def reiniciar_monitor_cierre(self) -> None:
        """Reinicia el estado de presencia del navegador para vigilar el cierre de la web."""
        with self._lock_web:
            self.evento_cierre_web.clear()
            self.cliente_web_conectado = False
            self.cierre_pendiente_ts = None
            self.ultimo_latido_web = time.monotonic()

    def registrar_latido_web(self) -> None:
        """Registra actividad del navegador y cancela cierres transitorios por recarga."""
        with self._lock_web:
            self.cliente_web_conectado = True
            self.ultimo_latido_web = time.monotonic()
            self.cierre_pendiente_ts = None

    def solicitar_cierre_web(self, motivo: str = "tab_closed") -> dict[str, Any]:
        """Procesa una señal de cierre manual o de cierre de pestaña del navegador."""
        with self._lock_web:
            if motivo == "manual":
                self.evento_cierre_web.set()
            else:
                self.cierre_pendiente_ts = time.monotonic()
        return {"ok": True, "motivo": motivo}

    def debe_finalizar_por_cierre_web(
        self,
        gracia_beacon_s: float = 2.5,
        timeout_inactividad_s: float = 15.0,
    ) -> bool:
        """Indica si la sesión web se cerró y procede detener la aplicación."""
        with self._lock_web:
            if self.evento_cierre_web.is_set():
                return True
            if self.peticiones_activas > 0:
                return False
            ahora = time.monotonic()
            if (
                self.cierre_pendiente_ts is not None
                and (ahora - self.cierre_pendiente_ts) >= gracia_beacon_s
            ):
                self.evento_cierre_web.set()
                return True
            if (
                self.cliente_web_conectado
                and (ahora - self.ultimo_latido_web) >= timeout_inactividad_s
            ):
                self.evento_cierre_web.set()
                return True
            return False

    def _obtener_hw(self) -> Any:
        if self._hw_info is None:
            self._hw_info = obtener_informacion_hardware()
        return self._hw_info

    def _invalidar_caches_modelos(self) -> None:
        self._parejas_cache = None
        self._catalogo_cache = None

    def _capturar_telemetria_rapida(self, hw: Any) -> MetricasTelemetria:
        """Captura telemetría del sistema sin invocar subprocesos externos en cada sondeo."""
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        ram_usada = (vm.total - vm.available) / (1024 ** 3)
        ram_total = vm.total / (1024 ** 3)
        ram_pct = vm.percent

        vram_total = hw.gtt_disponible_gb if hw.tiene_aceleracion_gpu else 0.0
        vram_usada = min(vram_total, ram_usada * 0.4) if vram_total > 0 else 0.0

        temp: Optional[float] = None
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for entradas in temps.values():
                        for entrada in entradas:
                            if entrada.current and entrada.current > 0:
                                temp = float(entrada.current)
                                break
                        if temp is not None:
                            break
        except Exception:
            temp = None

        try:
            du = shutil.disk_usage(os.getcwd())
            disco_total = du.total / (1024 ** 3)
            disco_usado = du.used / (1024 ** 3)
            disco_libre = du.free / (1024 ** 3)
            disco_pct = (du.used / du.total * 100.0) if du.total > 0 else 0.0
        except Exception:
            disco_total = disco_usado = disco_libre = disco_pct = 0.0

        return MetricasTelemetria(
            cpu_pct=round(cpu, 1),
            ram_usada_gb=round(ram_usada, 2),
            ram_total_gb=round(ram_total, 2),
            ram_pct=round(ram_pct, 1),
            vram_usada_gb=round(vram_usada, 2),
            vram_total_gb=round(vram_total, 2),
            temperatura_c=temp,
            es_critica=temp is not None and temp >= 82.0,
            disco_usado_gb=round(disco_usado, 1),
            disco_total_gb=round(disco_total, 1),
            disco_pct=round(disco_pct, 1),
            disco_libre_gb=round(disco_libre, 1),
            gpu_nombre=hw.nombre_gpu_principal or "CPU",
            gpu_tipo=hw.tipo_gpu_principal or "CPU",
            nucleos_cpu=f"{hw.nucleos_fisicos}C / {hw.nucleos_logicos}T",
        )

    def obtener_estado_sistema(self) -> dict[str, Any]:
        """Devuelve el estado consolidado de hardware, telemetría, motor, parejas y privacidad."""
        hw = self._obtener_hw()
        tel = self._capturar_telemetria_rapida(hw)
        tier = menu_actions.estimar_conjunto_modelos_optimo(hw)
        estado_srv = dict(self.gestor_server.obtener_estado())
        estado_srv["disponible_http"] = _cliente_disponible(self.cliente)
        estado_srv["base_url"] = getattr(self.cliente, "base_url", None)
        estado_srv["modelo_activo_id"] = self.modelo_activo_id
        estado_srv["motor_emb_id"] = self.motor_emb_id
        estado_srv["llama_server_instalado"] = bool(
            GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
        )
        if self._parejas_cache is None:
            self._parejas_cache = obtener_parejas_recomendadas(self.cache)

        return {
            "hardware": {
                "modelo_cpu": hw.modelo_cpu,
                "nucleos_fisicos": hw.nucleos_fisicos,
                "nucleos_logicos": hw.nucleos_logicos,
                "ram_total_gb": round(hw.ram_total_gb, 2),
                "tiene_aceleracion_gpu": hw.tiene_aceleracion_gpu,
                "nombre_gpu_principal": hw.nombre_gpu_principal,
                "tipo_gpu_principal": hw.tipo_gpu_principal,
                "gtt_disponible_gb": round(hw.gtt_disponible_gb, 2),
                "memoria_extrema_forzable_gb": round(hw.memoria_extrema_forzable_gb, 2),
                "hash_hardware": hw.hash_hardware,
            },
            "telemetria": asdict(tel),
            "tier": tier,
            "servidor": estado_srv,
            "parejas_recomendadas": self._parejas_cache,
            "modelos_locales": menu_actions.obtener_modelos_locales(self.cache),
            "privacidad": {
                "modo": self.proyectos.sanitizador.modo,
                "eventos_hmac": len(self.proyectos.sanitizador.historial_auditoria),
            },
        }

    def listar_catalogo_modelos(self) -> list[dict[str, Any]]:
        """Lista todos los modelos del catálogo con evaluación hardware, estado local y afinamiento."""
        if self._catalogo_cache is not None:
            return self._catalogo_cache
        hw = self._obtener_hw()
        locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(self.cache)}
        catalogo = []
        for mod in CatalogoModelos.MODELOS.values():
            ev = ComparadorModelosHardware.evaluar_modelo_completo(
                mod.id, mod.tamano_gb, hw, self.cache
            )
            opt = self.cache.obtener_configuracion_optima(mod.id, hw.hash_hardware)
            loc = locales.get(mod.id)
            catalogo.append(
                {
                    "id": mod.id,
                    "nombre_legible": mod.nombre_legible,
                    "categoria": mod.categoria,
                    "cuantizacion": mod.cuantizacion,
                    "formato": getattr(mod, "formato", "gguf"),
                    "tamano_gb": mod.tamano_gb,
                    "idiomas_destacados": mod.idiomas_destacados,
                    "descripcion": mod.descripcion,
                    "en_disco": loc is not None,
                    "ruta_local": loc.get("ruta_local", "") if loc else "",
                    "tamano_mb": loc.get("tamano_mb") if loc else None,
                    "tok_s_estimado": ev.tok_s_estimado,
                    "es_medido_real": ev.es_medido_real,
                    "clasificacion_chat": ev.clasificacion_chat,
                    "clasificacion_coding": ev.clasificacion_coding,
                    "estrategia_vram": ev.estrategia_vram,
                    "vram_requerida_4k_gb": ev.vram_requerida_4k_gb,
                    "afinamiento": (
                        {
                            "n_gpu_layers": opt.get("n_gpu_layers", 0),
                            "ctx_size": opt.get("ctx_size", 4096),
                            "batch_size": opt.get("batch_size", 512),
                            "kv_cache_tipo": opt.get("kv_cache_tipo", "f16"),
                            "tok_s_medido": opt.get("tok_s_medido", 0.0),
                            "threads": opt.get("threads"),
                        }
                        if opt
                        else None
                    ),
                }
            )
        self._catalogo_cache = catalogo
        return catalogo

    def afinar_modelos(self, modelo_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Auto-afina un modelo concreto o todos los modelos presentes en disco."""
        if modelo_id:
            locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(self.cache)}
            ruta_loc = Path(locales[modelo_id]["ruta_local"]) if modelo_id in locales else None
            reg = menu_actions.afinar_modelo_automatico(
                self.cache, modelo_id, ruta_local=ruta_loc, forzar=True
            )
            self._invalidar_caches_modelos()
            return [asdict(reg)]
        regs = menu_actions.afinar_todos_automatico(self.cache, forzar=True)
        self._invalidar_caches_modelos()
        return [asdict(r) for r in regs]

    def descargar_modelo(self, modelo_id: str) -> dict[str, Any]:
        """Descarga un modelo del catálogo y calcula su afinamiento inicial."""
        if not modelo_id:
            raise ValueError("Se requiere 'modelo_id'.")
        ruta = DescargadorModelos(gestor_cache=self.cache).descargar_modelo(
            modelo_id, permitir_inseguro=True
        )
        reg = menu_actions.afinar_modelo_automatico(
            self.cache, modelo_id, ruta_local=ruta, forzar=False
        )
        self._invalidar_caches_modelos()
        return {
            "ok": True,
            "modelo_id": modelo_id,
            "ruta_local": str(ruta),
            "afinamiento": asdict(reg),
        }

    def iniciar_motor(
        self,
        modelo_id: str,
        motor_emb_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Descarga si falta y arranca llama-server (o motor PyTorch/Safetensors) para el modelo."""
        if not modelo_id:
            raise ValueError("Se requiere 'modelo_id'.")

        with self._lock_motor:
            locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(self.cache)}
            if modelo_id not in locales:
                DescargadorModelos(gestor_cache=self.cache).descargar_modelo(
                    modelo_id, permitir_inseguro=True
                )
                locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(self.cache)}

            mod_reg = locales.get(modelo_id)
            if not mod_reg:
                raise ValueError(f"Modelo '{modelo_id}' no disponible en disco.")

            ruta_m = Path(mod_reg["ruta_local"])
            es_tensores = (
                ruta_m.suffix.lower() in (".safetensors", ".bin", ".pt")
                or ruta_m.is_dir()
                or "safetensors" in modelo_id.lower()
            )

            if es_tensores:
                if self.gestor_server.esta_activo():
                    self.gestor_server.detener_servidor()
                cli_tensores = ClienteTensoresChat(ruta_m, modelo_id)
                cli_tensores.cargar()
                self.cliente = cli_tensores
            else:
                binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
                if not binario:
                    raise RuntimeError(
                        "No se encontró el binario 'llama-server'. Descárgalo primero desde el búnker."
                    )

                if hasattr(self.cliente, "liberar_memoria"):
                    try:
                        self.cliente.liberar_memoria()
                    except Exception:
                        pass
                    self.cliente = ClienteLlamaOffline(timeout=300.0)

                if self.gestor_server.esta_activo():
                    self.gestor_server.detener_servidor()
                    time.sleep(0.5)

                menu_actions.afinar_modelo_automatico(self.cache, modelo_id, ruta_m)
                clave_api = secrets.token_urlsafe(32)
                cfg = LlamaServerConfig.desde_afinamiento(
                    modelo_path=ruta_m,
                    modelo_id=modelo_id,
                    binario_path=binario,
                    gestor_cache=self.cache,
                    api_key=clave_api,
                )
                host_cfg = cfg.host if isinstance(getattr(cfg, "host", None), str) else "127.0.0.1"
                port_cfg = (
                    cfg.port
                    if isinstance(getattr(cfg, "port", None), int) and not isinstance(cfg.port, bool)
                    else 8083
                )
                if not puerto_esta_disponible(host_cfg, port_cfg):
                    self.gestor_server.terminar_procesos_huerfanos("llama-server")
                    time.sleep(0.3)
                    port_cfg = asegurar_puerto_disponible(host_cfg, port_cfg)
                _sincronizar_puerto(cfg, self.cliente, host_cfg, port_cfg)
                self.cliente.api_key = clave_api

                ruta_log_srv = DIRECTORIO_LOGS / "llama-server.log"
                offset_log = _tamano_archivo_seguro(ruta_log_srv)
                self.gestor_server.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
                arranco_ok = _esperar_servidor_chat(self.gestor_server, self.cliente)

                if not arranco_ok:
                    detalle_intento = _leer_log_desde(ruta_log_srv, offset_log)
                    if _es_error_bind_puerto(detalle_intento):
                        self.gestor_server.detener_servidor()
                        time.sleep(0.3)
                        port_cfg = asegurar_puerto_disponible(
                            host_cfg, port_cfg + 1, excluir={port_cfg}
                        )
                        _sincronizar_puerto(cfg, self.cliente, host_cfg, port_cfg)
                        offset_log = _tamano_archivo_seguro(ruta_log_srv)
                        self.gestor_server.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
                        arranco_ok = _esperar_servidor_chat(self.gestor_server, self.cliente)

                if (
                    not arranco_ok
                    and isinstance(getattr(cfg, "n_gpu_layers", None), int)
                    and not isinstance(cfg.n_gpu_layers, bool)
                    and cfg.n_gpu_layers > 0
                ):
                    self.gestor_server.detener_servidor()
                    time.sleep(0.5)
                    port_cfg = asegurar_puerto_disponible(host_cfg, port_cfg)
                    _sincronizar_puerto(cfg, self.cliente, host_cfg, port_cfg)
                    cfg.n_gpu_layers = 0
                    cfg.ctx_size = min(cfg.ctx_size, 2048)
                    cfg.batch_size = 256
                    cfg.ubatch_size = 128
                    cfg.kv_cache_type = "q8_0"
                    if "-nkvo" not in cfg.extra_args:
                        cfg.extra_args.append("-nkvo")
                    offset_log = _tamano_archivo_seguro(ruta_log_srv)
                    self.gestor_server.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
                    arranco_ok = _esperar_servidor_chat(self.gestor_server, self.cliente)

                if not arranco_ok:
                    detalle_err = (
                        _leer_log_desde(ruta_log_srv, offset_log)
                        or _leer_log_desde(ruta_log_srv, 0)
                    )
                    code = self.gestor_server.proceso.poll() if self.gestor_server.proceso else "Timeout"
                    self.gestor_server.detener_servidor()
                    raise RuntimeError(
                        f"No se pudo iniciar llama-server para '{modelo_id}' (código {code}). {detalle_err}"
                    )

            self.modelo_activo_id = modelo_id
            if motor_emb_id:
                self.motor_emb_id = motor_emb_id
            self._invalidar_caches_modelos()

        return self.obtener_estado_sistema()["servidor"]

    def detener_motor(self) -> dict[str, Any]:
        """Detiene el servidor de inferencia activo."""
        with self._lock_motor:
            if hasattr(self.cliente, "liberar_memoria"):
                try:
                    self.cliente.liberar_memoria()
                except Exception:
                    pass
                self.cliente = ClienteLlamaOffline(timeout=300.0)
            self.gestor_server.detener_servidor()
            self.modelo_activo_id = None
            self._invalidar_caches_modelos()
        return self.obtener_estado_sistema()["servidor"]

    def listar_proyectos(self) -> list[dict[str, Any]]:
        """Lista los proyectos registrados con sus contadores de documentos y sesiones."""
        proyectos = self.proyectos.listar_proyectos()
        salida = []
        for p in proyectos:
            item = dict(p)
            item["documentos_count"] = len(self.cache.listar_documentos_proyecto(p["id"]))
            item["sesiones_count"] = len(self.proyectos.listar_sesiones(proyecto_id=p["id"]))
            salida.append(item)
        return salida

    def crear_proyecto(
        self,
        nombre: str,
        ruta_directorio: str,
        descripcion: str = "",
    ) -> dict[str, Any]:
        """Crea un proyecto local y ejecuta la indexación AST/RAG inicial."""
        nombre_limpio = (nombre or "").strip()
        ruta_limpia = (ruta_directorio or "").strip().strip('"')
        if not nombre_limpio or not ruta_limpia:
            raise ValueError("El nombre y la ruta de carpeta son obligatorios.")
        ruta_p = Path(ruta_limpia)
        if not ruta_p.is_dir():
            raise ValueError(f"La ruta no existe o no es una carpeta válida: {ruta_limpia}")
        reg = self.proyectos.crear_proyecto(nombre_limpio, ruta_p, descripcion)
        resumen = self.proyectos.escanear_e_indexar_proyecto(
            reg.id, modelo_emb_id=self.motor_emb_id
        )
        return {"proyecto": asdict(reg), "indexacion": resumen}

    def indexar_proyecto(self, proyecto_id: str) -> dict[str, Any]:
        """Reindexa un proyecto existente de forma incremental."""
        if not proyecto_id:
            raise ValueError("Se requiere 'proyecto_id'.")
        return self.proyectos.escanear_e_indexar_proyecto(
            proyecto_id, modelo_emb_id=self.motor_emb_id
        )

    def eliminar_proyecto(self, proyecto_id: str) -> bool:
        if not proyecto_id:
            raise ValueError("Se requiere 'proyecto_id'.")
        return self.proyectos.eliminar_proyecto(proyecto_id)

    def obtener_archivos_y_grafo_proyecto(
        self,
        proyecto_id: str,
        semilla: Optional[str] = None,
    ) -> dict[str, Any]:
        """Devuelve documentos indexados, nodos/aristas del grafo AST y expansión multihop opcional."""
        if not self.proyectos.obtener_proyecto(proyecto_id):
            raise ValueError(f"Proyecto '{proyecto_id}' no encontrado.")
        documentos = self.cache.listar_documentos_proyecto(proyecto_id)
        with self.cache.sesion_proyectos() as conn:
            nodos = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT * FROM nodos_ast_grafo
                    WHERE proyecto_id = ?
                    ORDER BY ruta_archivo ASC, linea_inicio ASC
                    LIMIT 200;
                    """,
                    (proyecto_id,),
                ).fetchall()
            ]
            relaciones = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM relaciones_ast_grafo WHERE proyecto_id = ? LIMIT 300;",
                    (proyecto_id,),
                ).fetchall()
            ]
        expansion = (
            self.cache.expandir_dependencias_ast_recursivo(
                proyecto_id, [semilla], max_profundidad=2
            )
            if semilla
            else []
        )
        return {
            "proyecto_id": proyecto_id,
            "documentos": documentos,
            "nodos_ast": nodos,
            "relaciones_ast": relaciones,
            "expansion": expansion,
        }

    def listar_sesiones(self, proyecto_id: Optional[str] = None) -> list[dict[str, Any]]:
        return self.proyectos.listar_sesiones(proyecto_id=proyecto_id or None)

    def crear_sesion(
        self,
        modelo_id: Optional[str] = None,
        proyecto_id: Optional[str] = None,
        titulo: str = "",
    ) -> dict[str, Any]:
        mod_id = modelo_id or self.modelo_activo_id
        if not mod_id:
            parejas = obtener_parejas_recomendadas(self.cache)
            mod_id = parejas[0]["modelo_gen_id"] if parejas else "qwen2.5-3b-chat-q4"
        reg = self.proyectos.crear_sesion(
            modelo_id=mod_id,
            titulo=titulo,
            proyecto_id=proyecto_id or None,
        )
        return asdict(reg)

    def eliminar_sesion(self, sesion_id: str) -> bool:
        if not sesion_id:
            raise ValueError("Se requiere 'sesion_id'.")
        return self.cache.eliminar_sesion_chat(sesion_id)

    def obtener_mensajes_sesion(self, sesion_id: str) -> list[dict[str, Any]]:
        if not sesion_id:
            raise ValueError("Se requiere 'sesion_id'.")
        msgs = self.proyectos.obtener_historial_sesion(sesion_id)
        resultado = []
        for m in msgs:
            item = dict(m)
            fuentes = []
            raw_f = item.get("fuentes_ast_json")
            if raw_f:
                try:
                    parsed = json.loads(raw_f)
                    if isinstance(parsed, list):
                        fuentes = parsed
                except Exception:
                    pass
            item["fuentes"] = fuentes
            resultado.append(item)
        return resultado

    def obtener_memoria(
        self,
        proyecto_id: Optional[str] = None,
        sesion_id: Optional[str] = None,
        incluir_superseded: bool = False,
    ) -> list[dict[str, Any]]:
        pid = proyecto_id or None
        sid = sesion_id or None
        if incluir_superseded:
            return self.proyectos.obtener_auditoria_hechos(proyecto_id=pid, sesion_id=sid)
        return self.proyectos.obtener_hechos_activos(proyecto_id=pid, sesion_id=sid)

    def registrar_memoria(
        self,
        sujeto: str,
        predicado: str,
        objeto: str,
        proyecto_id: Optional[str] = None,
        sesion_id: Optional[str] = None,
    ) -> dict[str, Any]:
        hecho_id = self.proyectos.registrar_hecho(
            sujeto,
            predicado,
            objeto,
            proyecto_id=proyecto_id or None,
            sesion_id=sesion_id or None,
            origen_tipo="web",
        )
        return {"id": hecho_id, "sujeto": sujeto, "predicado": predicado, "objeto": objeto}

    def configurar_privacidad(self, modo: str) -> dict[str, Any]:
        self.proyectos.configurar_modo_privacidad(modo)
        return {
            "modo": self.proyectos.sanitizador.modo,
            "eventos_hmac": len(self.proyectos.sanitizador.historial_auditoria),
        }

    def _asegurar_sesion_chat(
        self,
        sesion_id: Optional[str],
        proyecto_id: Optional[str],
        proy_activo: Optional[dict[str, Any]],
        modelo_id: Optional[str],
    ) -> str:
        if sesion_id:
            existente = self.proyectos.obtener_sesion(sesion_id)
            if existente:
                return str(existente["id"])
        mod_id = modelo_id or self.modelo_activo_id
        if not mod_id:
            parejas = obtener_parejas_recomendadas(self.cache)
            mod_id = parejas[0]["modelo_gen_id"] if parejas else "qwen2.5-3b-chat-q4"
        titulo = f"Chat con {mod_id}"
        if proy_activo:
            titulo += f" [{proy_activo['nombre']}]"
        reg = self.proyectos.crear_sesion(
            modelo_id=mod_id,
            titulo=titulo,
            proyecto_id=proyecto_id,
        )
        return reg.id

    def _ejecutar_comando_chat(
        self,
        msg: str,
        sesion_id_activa: str,
        proy_activo: Optional[dict[str, Any]],
        proyecto_id: Optional[str],
    ) -> Optional[dict[str, Any]]:
        msg_lower = msg.lower()
        if msg_lower in ("/ficheros", "/archivos", "/files"):
            if proy_activo:
                docs = self.cache.listar_documentos_proyecto(proy_activo["id"])
                if docs:
                    lineas = [
                        f"**Ficheros indexados en '{proy_activo['nombre']}' ({len(docs)} archivos):**"
                    ]
                    for d in docs:
                        lineas.append(
                            f"- `{d['ruta_relativa']}` [{d['tipo_documento']}] ({d['nodos_ast_count']} fragmentos)"
                        )
                    resp_txt = "\n".join(lineas)
                else:
                    resp_txt = f"No hay archivos indexados en el proyecto '{proy_activo['nombre']}'."
            else:
                resp_txt = "No hay ningún proyecto activo asociado a esta sesión de chat."
            return {
                "sesion_id": sesion_id_activa,
                "respuesta": resp_txt,
                "comando": True,
                "fuentes": [],
                "metricas": None,
                "hechos_detectados": [],
                "redacciones_privacidad": 0,
            }

        if msg_lower.startswith("/remember") or msg_lower.startswith("/recordar"):
            cuerpo = msg.split(None, 1)[1].strip() if len(msg.split(None, 1)) > 1 else ""
            partes = [p.strip() for p in cuerpo.split("|")]
            if len(partes) == 3 and all(partes):
                hecho_id = self.proyectos.registrar_hecho(
                    partes[0],
                    partes[1],
                    partes[2],
                    proyecto_id=proyecto_id,
                    sesion_id=sesion_id_activa,
                    origen_tipo="comando",
                )
                return {
                    "sesion_id": sesion_id_activa,
                    "respuesta": f"[OK] Hecho registrado en memoria inmutable (#{hecho_id}): `{partes[0]} | {partes[1]} | {partes[2]}`",
                    "comando": True,
                    "fuentes": [],
                    "metricas": None,
                    "hechos_detectados": [
                        {"id": hecho_id, "sujeto": partes[0], "predicado": partes[1], "objeto": partes[2]}
                    ],
                    "redacciones_privacidad": 0,
                }
            return {
                "sesion_id": sesion_id_activa,
                "respuesta": "Uso: `/remember <sujeto> | <predicado> | <objeto>`",
                "comando": True,
                "fuentes": [],
                "metricas": None,
                "hechos_detectados": [],
                "redacciones_privacidad": 0,
            }

        if (
            msg_lower == "/recall"
            or msg_lower.startswith("/recall ")
            or msg_lower == "/memoria"
            or msg_lower.startswith("/memoria ")
        ):
            tokens_cmd = msg_lower.split()
            incluir_todo = len(tokens_cmd) > 1 and tokens_cmd[1] in (
                "all",
                "todo",
                "historico",
                "histórico",
            )
            hechos = self.obtener_memoria(
                proyecto_id=proyecto_id,
                sesion_id=sesion_id_activa,
                incluir_superseded=incluir_todo,
            )
            if not hechos:
                resp_txt = "No hay hechos registrados en la memoria de esta sesión/proyecto."
            else:
                titulo = (
                    "AUDITORÍA COMPLETA DE MEMORIA"
                    if incluir_todo
                    else "MEMORIA DECLARATIVA ACTIVA"
                )
                lineas = [f"**[{titulo}] ({len(hechos)} hechos):**"]
                for h in hechos:
                    etiqueta = (
                        f"[SUPERSEDED -> #{h.get('sustituido_por_id')}]"
                        if h.get("estado") == "superseded"
                        else "[ACTIVO]"
                    )
                    sha_corta = str(h.get("sha_origen", ""))[:8]
                    lineas.append(
                        f"- `#{h['id']}` {etiqueta} `{h['sujeto']} | {h['predicado']} | {h['objeto']}` (sha:{sha_corta})"
                    )
                resp_txt = "\n".join(lineas)
            return {
                "sesion_id": sesion_id_activa,
                "respuesta": resp_txt,
                "comando": True,
                "fuentes": [],
                "metricas": None,
                "hechos_detectados": [],
                "redacciones_privacidad": 0,
            }

        if msg_lower == "/rgpd" or msg_lower.startswith("/rgpd "):
            arg = msg_lower.split(None, 1)[1].strip() if len(msg_lower.split(None, 1)) > 1 else "status"
            if arg in ("on", "estricto", "rgpd_estricto", "1", "true"):
                priv = self.configurar_privacidad("rgpd_estricto")
                resp_txt = "[OK] Modo de privacidad: `rgpd_estricto` (anonimización irreversible + auditoría HMAC)."
            elif arg in ("off", "estandar", "estándar", "0", "false"):
                priv = self.configurar_privacidad("estandar")
                resp_txt = "[OK] Modo de privacidad: `estandar` (bloques `<private>` y secretos explícitos)."
            else:
                priv = {
                    "modo": self.proyectos.sanitizador.modo,
                    "eventos_hmac": len(self.proyectos.sanitizador.historial_auditoria),
                }
                resp_txt = (
                    f"[Privacidad] Modo activo: `{priv['modo']}` | "
                    f"Eventos HMAC registrados en sesión: {priv['eventos_hmac']}"
                )
            return {
                "sesion_id": sesion_id_activa,
                "respuesta": resp_txt,
                "comando": True,
                "fuentes": [],
                "metricas": None,
                "hechos_detectados": [],
                "redacciones_privacidad": 0,
                "privacidad": priv,
            }

        return None

    def procesar_turno_chat(
        self,
        mensaje: str,
        sesion_id: Optional[str] = None,
        proyecto_id: Optional[str] = None,
        modelo_id: Optional[str] = None,
        motor_emb_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Procesa un comando o turno conversacional con RAG local, memoria declarativa y métricas."""
        msg = (mensaje or "").strip()
        if not msg:
            raise ValueError("El mensaje no puede estar vacío.")

        proy_id = proyecto_id or None
        proy_activo = self.proyectos.obtener_proyecto(proy_id) if proy_id else None
        sesion_id_activa = self._asegurar_sesion_chat(
            sesion_id=sesion_id,
            proyecto_id=proy_id,
            proy_activo=proy_activo,
            modelo_id=modelo_id,
        )

        res_cmd = self._ejecutar_comando_chat(msg, sesion_id_activa, proy_activo, proy_id)
        if res_cmd is not None:
            return res_cmd

        if motor_emb_id:
            self.motor_emb_id = motor_emb_id

        modelo_objetivo = modelo_id or self.modelo_activo_id
        necesita_arranque = not _cliente_disponible(self.cliente) or bool(
            modelo_id and self.modelo_activo_id and modelo_id != self.modelo_activo_id
        )
        if necesita_arranque:
            if not modelo_objetivo:
                parejas = obtener_parejas_recomendadas(self.cache)
                modelo_objetivo = parejas[0]["modelo_gen_id"] if parejas else "qwen2.5-3b-chat-q4"
            self.iniciar_motor(modelo_objetivo, motor_emb_id=motor_emb_id)

        redacciones_privacidad = 0
        if self.proyectos.sanitizador.necesita_sanitizacion(msg):
            res_san = self.proyectos.sanitizador.sanitizar_texto(
                msg, origen=f"web:{sesion_id_activa}"
            )
            if res_san.total_redacciones > 0:
                msg = res_san.texto_sanitizado
                redacciones_privacidad = res_san.total_redacciones

        hechos_detectados: list[dict[str, Any]] = []
        for subj, pred, obj in extraer_hechos_declarativos(msg):
            sha_msg = hashlib.sha256(msg.encode("utf-8")).hexdigest()
            hid = self.proyectos.registrar_hecho(
                subj,
                pred,
                obj,
                proyecto_id=proy_id,
                sesion_id=sesion_id_activa,
                origen_tipo="chat",
                sha_origen=sha_msg,
            )
            hechos_detectados.append(
                {"id": hid, "sujeto": subj, "predicado": pred, "objeto": obj}
            )

        prompt_sistema = (
            "Eres un asistente de inteligencia artificial preciso y técnico que corre 100% en local "
            "dentro del entorno bunkerizado GuarIdA. Responde en perfecto español de forma concisa y útil."
        )
        historial_previo = self.proyectos.obtener_historial_sesion(sesion_id_activa)

        fuentes_turno: list[dict[str, Any]] = []
        datos_rag_turno: Optional[dict[str, Any]] = None
        prompt_usuario_final = msg

        if proy_activo:
            if (
                proy_activo["id"] not in self.proyectos._chunks_texto
                and proy_activo["id"] not in self.proyectos._arboles_codigo
            ):
                self.proyectos.escanear_e_indexar_proyecto(
                    proy_activo["id"], modelo_emb_id=self.motor_emb_id
                )

            docs_idx = self.cache.listar_documentos_proyecto(proy_activo["id"])
            if docs_idx:
                prompt_sistema += (
                    f"\n\n[PROYECTO ACTIVO]: '{proy_activo['nombre']}' ({len(docs_idx)} archivos indexados).\n"
                    "DIRECTIVAS ESTRICTAS DE RESPUESTA Y FIDELIDAD DOCUMENTAL:\n"
                    "1. Responde ÚNICAMENTE basándote en la información explícita de los fragmentos en [Contexto del Repositorio/Documentación].\n"
                    "2. Si la información no aparece en los fragmentos citados, responde con total sinceridad: "
                    "'No consta en los fragmentos disponibles del documento consultado'.\n"
                    "3. NUNCA inventes requisitos, normativas, excepciones ni nombres de documentos o archivos que no se indiquen explícitamente en el contexto.\n"
                    "4. Cita con precisión las páginas, artículos o secciones que sustentan tu respuesta.\n"
                    "5. Para listar los archivos indexados del proyecto, indícale al usuario que use el comando '/ficheros'."
                )

            consulta_rag = msg
            if len(historial_previo) >= 2 and len(msg.split()) < 15:
                previos_usr = [m["contenido"] for m in historial_previo if m["rol"] == "user"]
                if previos_usr:
                    consulta_rag = f"{previos_usr[-1]} {msg}"

            t_busq_0 = time.perf_counter()
            ctx_doc, fuentes_turno = self.proyectos.buscar_contexto_hibrido(
                proyecto_id=proy_activo["id"],
                consulta=consulta_rag,
                top_k=5,
            )
            t_busq_1 = time.perf_counter()

            t_ctx_0 = time.perf_counter()
            tokens_ctx = 0
            if ctx_doc:
                prompt_usuario_final = (
                    f"{msg}\n\n[Contexto del Repositorio/Documentación]:\n{ctx_doc}"
                )
                tokens_ctx = medir_tokens_mensaje(self.cliente, ctx_doc)
            t_ctx_1 = time.perf_counter()

            n_fragmentos = len(self.proyectos._chunks_texto.get(proy_activo["id"], []))
            ficheros_consultados = list(
                dict.fromkeys(f.get("archivo", "") for f in fuentes_turno if f.get("archivo"))
            )
            datos_rag_turno = {
                "tiempo_busqueda_ms": (t_busq_1 - t_busq_0) * 1000.0,
                "fragmentos_evaluados": n_fragmentos,
                "fragmentos_citados": len(fuentes_turno),
                "top_score": fuentes_turno[0].get("relevancia") if fuentes_turno else None,
                "tiempo_contexto_ms": (t_ctx_1 - t_ctx_0) * 1000.0,
                "tokens_contexto": tokens_ctx,
                "chars_contexto": len(ctx_doc) if ctx_doc else 0,
                "ficheros_consultados": ficheros_consultados,
            }

        ctx_memoria = self.proyectos.formatear_contexto_memoria_canonica(
            proyecto_id=proy_id, sesion_id=sesion_id_activa
        )
        if ctx_memoria:
            prompt_usuario_final = f"{prompt_usuario_final}\n\n{ctx_memoria}"

        mensajes_envio: list[dict[str, str]] = [{"role": "system", "content": prompt_sistema}]
        for m in historial_previo:
            mensajes_envio.append({"role": m["rol"], "content": m["contenido"]})
        mensajes_envio.append({"role": "user", "content": prompt_usuario_final})

        tokens_msg = medir_tokens_mensaje(self.cliente, msg)
        t_inicio = time.perf_counter()
        resp = self.cliente.completar_chat(
            mensajes=mensajes_envio,
            temperatura=0.2,
            max_tokens=1024,
            timeout=300.0,
        )
        tiempo_total_s = time.perf_counter() - t_inicio

        elecciones = resp.get("choices", [])
        contenido_asistente = (
            elecciones[0].get("message", {}).get("content", "") if elecciones else ""
        )

        metricas = calcular_metricas_interaccion(
            tokens_mensaje=tokens_msg,
            respuesta_api=resp,
            tiempo_total_s=tiempo_total_s,
            cliente=self.cliente,
            contenido_salida=contenido_asistente,
            metricas_rag=datos_rag_turno,
        )

        self.proyectos.registrar_mensaje(
            sesion_id=sesion_id_activa,
            rol="user",
            contenido=msg,
            tokens_prompt=metricas["tokens_mensaje"],
        )
        self.proyectos.registrar_mensaje(
            sesion_id=sesion_id_activa,
            rol="assistant",
            contenido=contenido_asistente,
            fuentes=fuentes_turno if fuentes_turno else None,
            tokens_generados=metricas["tokens_generados"],
        )

        return {
            "sesion_id": sesion_id_activa,
            "respuesta": contenido_asistente,
            "fuentes": fuentes_turno,
            "metricas": _serializar_json(metricas),
            "hechos_detectados": hechos_detectados,
            "redacciones_privacidad": redacciones_privacidad,
            "comando": False,
        }


class ManejadorHTTPGuarida(BaseHTTPRequestHandler):
    """Manejador HTTP/JSON offline para la aplicación web GuarIdA."""

    server_version = "GuarIdA-Web/1.0"

    @property
    def controlador(self) -> ControladorWebGuarida:
        return self.server.controlador  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("HTTP %s - " + format, self.address_string(), *args)

    def _enviar_bytes(self, codigo: int, content_type: str, datos: bytes) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _enviar_json(self, codigo: int, payload: Any) -> None:
        cuerpo = json.dumps(_serializar_json(payload), ensure_ascii=False).encode("utf-8")
        self._enviar_bytes(codigo, "application/json; charset=utf-8", cuerpo)

    def _leer_json_body(self) -> dict[str, Any]:
        try:
            longitud = int(self.headers.get("Content-Length") or "0")
        except ValueError as exc:
            raise ValueError("Content-Length inválido.") from exc
        if longitud <= 0:
            return {}
        if longitud > 2_000_000:
            raise ValueError("Cuerpo JSON demasiado grande.")
        crudo = self.rfile.read(longitud).decode("utf-8", errors="replace")
        if not crudo.strip():
            return {}
        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido: {exc}") from exc
        if not isinstance(datos, dict):
            raise ValueError("El cuerpo JSON debe ser un objeto.")
        return datos

    def _servir_estatico(self, ruta_rel: str) -> None:
        nombre = "index.html" if ruta_rel in ("", "/") else ruta_rel.lstrip("/")
        if "/" in nombre or "\\" in nombre or ".." in nombre:
            self._enviar_json(HTTPStatus.NOT_FOUND, {"error": "Recurso no encontrado"})
            return
        archivo = (DIRECTORIO_STATIC / nombre).resolve()
        if not archivo.is_file() or archivo.parent != DIRECTORIO_STATIC.resolve():
            self._enviar_json(HTTPStatus.NOT_FOUND, {"error": "Recurso no encontrado"})
            return
        mime = _MIME_TYPES.get(archivo.suffix.lower(), "application/octet-stream")
        self._enviar_bytes(HTTPStatus.OK, mime, archivo.read_bytes())

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        ruta = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        ctrl = self.controlador

        with ctrl._lock_web:
            ctrl.peticiones_activas += 1
        try:
            if ruta in ("/", "/app.js", "/styles.css", "/api/status"):
                ctrl.registrar_latido_web()

            if not ruta.startswith("/api/"):
                self._servir_estatico(ruta)
                return

            if ruta == "/api/status":
                self._enviar_json(HTTPStatus.OK, ctrl.obtener_estado_sistema())
            elif ruta == "/api/models":
                self._enviar_json(HTTPStatus.OK, {"modelos": ctrl.listar_catalogo_modelos()})
            elif ruta == "/api/projects":
                self._enviar_json(HTTPStatus.OK, {"proyectos": ctrl.listar_proyectos()})
            elif ruta == "/api/projects/files":
                pid = (qs.get("proyecto_id") or [""])[0]
                if not pid:
                    raise ValueError("Se requiere 'proyecto_id'.")
                semilla = (qs.get("semilla") or [None])[0]
                self._enviar_json(
                    HTTPStatus.OK,
                    ctrl.obtener_archivos_y_grafo_proyecto(pid, semilla=semilla),
                )
            elif ruta == "/api/sessions":
                pid = (qs.get("proyecto_id") or [None])[0]
                self._enviar_json(HTTPStatus.OK, {"sesiones": ctrl.listar_sesiones(proyecto_id=pid)})
            elif ruta == "/api/sessions/messages":
                sid = (qs.get("sesion_id") or [""])[0]
                self._enviar_json(HTTPStatus.OK, {"mensajes": ctrl.obtener_mensajes_sesion(sid)})
            elif ruta == "/api/memory":
                pid = (qs.get("proyecto_id") or [None])[0]
                sid = (qs.get("sesion_id") or [None])[0]
                inc = (qs.get("incluir_superseded") or [""])[0].lower() in ("1", "true", "si")
                self._enviar_json(
                    HTTPStatus.OK,
                    {"hechos": ctrl.obtener_memoria(proyecto_id=pid, sesion_id=sid, incluir_superseded=inc)},
                )
            else:
                self._enviar_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint no encontrado: {ruta}"})
        except (ValueError, FileNotFoundError) as exc:
            self._enviar_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            logger.error(f"Error en GET {ruta}: {exc}", exc_info=True)
            self._enviar_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            with ctrl._lock_web:
                ctrl.peticiones_activas = max(0, ctrl.peticiones_activas - 1)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        ruta = parsed.path
        ctrl = self.controlador

        with ctrl._lock_web:
            ctrl.peticiones_activas += 1
        try:
            body = self._leer_json_body()
            if ruta == "/api/web/close":
                motivo = str(body.get("motivo") or "tab_closed")
                self._enviar_json(HTTPStatus.OK, ctrl.solicitar_cierre_web(motivo))
            elif ruta == "/api/models/tune":
                res = ctrl.afinar_modelos(modelo_id=body.get("modelo_id"))
                self._enviar_json(HTTPStatus.OK, {"afinados": res})
            elif ruta == "/api/models/download":
                res = ctrl.descargar_modelo(str(body.get("modelo_id") or ""))
                self._enviar_json(HTTPStatus.OK, res)
            elif ruta == "/api/server/start":
                srv = ctrl.iniciar_motor(
                    modelo_id=str(body.get("modelo_id") or ""),
                    motor_emb_id=body.get("motor_emb_id"),
                )
                self._enviar_json(HTTPStatus.OK, {"servidor": srv})
            elif ruta == "/api/server/stop":
                self._enviar_json(HTTPStatus.OK, {"servidor": ctrl.detener_motor()})
            elif ruta == "/api/projects":
                res = ctrl.crear_proyecto(
                    nombre=str(body.get("nombre") or ""),
                    ruta_directorio=str(body.get("ruta_directorio") or ""),
                    descripcion=str(body.get("descripcion") or ""),
                )
                self._enviar_json(HTTPStatus.CREATED, res)
            elif ruta == "/api/projects/index":
                res = ctrl.indexar_proyecto(str(body.get("proyecto_id") or ""))
                self._enviar_json(HTTPStatus.OK, {"resumen": res})
            elif ruta == "/api/sessions":
                res = ctrl.crear_sesion(
                    modelo_id=body.get("modelo_id"),
                    proyecto_id=body.get("proyecto_id"),
                    titulo=str(body.get("titulo") or ""),
                )
                self._enviar_json(HTTPStatus.CREATED, {"sesion": res})
            elif ruta == "/api/memory":
                res = ctrl.registrar_memoria(
                    sujeto=str(body.get("sujeto") or ""),
                    predicado=str(body.get("predicado") or ""),
                    objeto=str(body.get("objeto") or ""),
                    proyecto_id=body.get("proyecto_id"),
                    sesion_id=body.get("sesion_id"),
                )
                self._enviar_json(HTTPStatus.CREATED, {"hecho": res})
            elif ruta == "/api/privacy":
                res = ctrl.configurar_privacidad(str(body.get("modo") or ""))
                self._enviar_json(HTTPStatus.OK, res)
            elif ruta == "/api/chat":
                res = ctrl.procesar_turno_chat(
                    mensaje=str(body.get("mensaje") or ""),
                    sesion_id=body.get("sesion_id"),
                    proyecto_id=body.get("proyecto_id"),
                    modelo_id=body.get("modelo_id"),
                    motor_emb_id=body.get("motor_emb_id"),
                )
                self._enviar_json(HTTPStatus.OK, res)
            else:
                self._enviar_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint no encontrado: {ruta}"})
        except (ValueError, FileNotFoundError) as exc:
            self._enviar_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            logger.error(f"Error en POST {ruta}: {exc}", exc_info=True)
            self._enviar_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            with ctrl._lock_web:
                ctrl.peticiones_activas = max(0, ctrl.peticiones_activas - 1)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        ruta = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        ctrl = self.controlador

        try:
            body = self._leer_json_body()
            if ruta == "/api/projects":
                pid = str(body.get("proyecto_id") or (qs.get("proyecto_id") or [""])[0])
                self._enviar_json(HTTPStatus.OK, {"eliminado": ctrl.eliminar_proyecto(pid)})
            elif ruta == "/api/sessions":
                sid = str(body.get("sesion_id") or (qs.get("sesion_id") or [""])[0])
                self._enviar_json(HTTPStatus.OK, {"eliminado": ctrl.eliminar_sesion(sid)})
            else:
                self._enviar_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint no encontrado: {ruta}"})
        except (ValueError, FileNotFoundError) as exc:
            self._enviar_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            logger.error(f"Error en DELETE {ruta}: {exc}", exc_info=True)
            self._enviar_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


class ServidorWebGuarida(ThreadingHTTPServer):
    """Servidor HTTP multihilo local para alojar la UI y API de GuarIdA."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        controlador: Optional[ControladorWebGuarida] = None,
    ) -> None:
        self.controlador = controlador or ControladorWebGuarida()
        super().__init__(server_address, ManejadorHTTPGuarida)


_SERVIDOR_WEB_BG: Optional[ServidorWebGuarida] = None
_WEB_BG_LOCK = threading.Lock()


def crear_servidor_web(
    host: str = "127.0.0.1",
    port: int = 8080,
    controlador: Optional[ControladorWebGuarida] = None,
) -> ServidorWebGuarida:
    """Construye una instancia lista de ServidorWebGuarida en un puerto libre."""
    puerto_final = 0 if port == 0 else asegurar_puerto_disponible(host, port)
    ctrl = controlador or ControladorWebGuarida()
    return ServidorWebGuarida((host, puerto_final), ctrl)


def asegurar_servidor_web_en_segundo_plano(
    host: str = "127.0.0.1",
    port: int = 8080,
    gestor_cache: Optional[GestorCache] = None,
) -> str:
    """Garantiza que la web de GuarIdA esté escuchando en segundo plano y devuelve su URL."""
    global _SERVIDOR_WEB_BG
    with _WEB_BG_LOCK:
        if _SERVIDOR_WEB_BG is not None:
            puerto_activo = int(_SERVIDOR_WEB_BG.server_address[1])
            return f"http://{host}:{puerto_activo}"
        if not puerto_esta_disponible(host, port):
            return f"http://{host}:{port}"
        ctrl = ControladorWebGuarida(gestor_cache=gestor_cache)
        srv = crear_servidor_web(host=host, port=port, controlador=ctrl)
        _SERVIDOR_WEB_BG = srv
        hilo = threading.Thread(target=srv.serve_forever, daemon=True)
        hilo.start()
        puerto_real = int(srv.server_address[1])
        return f"http://{host}:{puerto_real}"


def ejecutar_web_hasta_cierre(
    host: str = "127.0.0.1",
    port: int = 8080,
    abrir_navegador: bool = True,
    minimizar_consola: bool = True,
    gestor_cache: Optional[GestorCache] = None,
) -> None:
    """Mantiene GuarIdA en segundo plano sirviendo la web hasta que se cierre en el navegador."""
    global _SERVIDOR_WEB_BG
    inicializar_logging()
    url = asegurar_servidor_web_en_segundo_plano(
        host=host, port=port, gestor_cache=gestor_cache
    )
    with _WEB_BG_LOCK:
        srv = _SERVIDOR_WEB_BG
        if srv is None:
            puerto_alt = asegurar_puerto_disponible(host, port + 1, excluir={port})
            ctrl = ControladorWebGuarida(gestor_cache=gestor_cache)
            srv = crear_servidor_web(host=host, port=puerto_alt, controlador=ctrl)
            _SERVIDOR_WEB_BG = srv
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            url = f"http://{host}:{int(srv.server_address[1])}"

    srv.controlador.reiniciar_monitor_cierre()
    print(f"\n[OK] Interfaz Web Autoalojada activa en: {url}", flush=True)
    print("     GuarIdA permanecerá en segundo plano hasta que cierres la web.", flush=True)

    if abrir_navegador:
        webbrowser.open(url)

    if minimizar_consola and os.name == "nt":
        try:
            import ctypes

            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)
        except Exception:
            pass

    try:
        while not srv.controlador.debe_finalizar_por_cierre_web():
            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            srv.controlador.detener_motor()
        except Exception:
            pass
        with _WEB_BG_LOCK:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
            if _SERVIDOR_WEB_BG is srv:
                _SERVIDOR_WEB_BG = None


def iniciar_servidor_web(
    host: str = "127.0.0.1",
    port: int = 8080,
    abrir_navegador: bool = True,
    gestor_cache: Optional[GestorCache] = None,
) -> None:
    """Arranca el servidor web autoalojado de GuarIdA y abre opcionalmente el navegador."""
    inicializar_logging()
    ctrl = ControladorWebGuarida(gestor_cache=gestor_cache)
    servidor = crear_servidor_web(host=host, port=port, controlador=ctrl)
    puerto_real = int(servidor.server_address[1])
    url = f"http://{host}:{puerto_real}"

    print("=" * 75, flush=True)
    print("  GUARIDA // INTERFAZ WEB AUTOALOJADA (ESTILO ANTIGRAVITY IDE)", flush=True)
    print("=" * 75, flush=True)
    print(f"  URL local soberana:  {url}", flush=True)
    print("  Modo:                100% offline / loopback local", flush=True)
    print("  Detener servidor:    Ctrl+C", flush=True)
    print("=" * 75, flush=True)

    if abrir_navegador:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor web GuarIdA...")
    finally:
        try:
            ctrl.detener_motor()
        except Exception:
            pass
        servidor.server_close()
