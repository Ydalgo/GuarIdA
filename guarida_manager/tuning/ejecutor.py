import os
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import psutil

from guarida_manager import DIRECTORIO_RAIZ_GUARIDA
from guarida_manager.engine.client import ClienteLlamaOffline
from guarida_manager.engine.server import GestorLlamaServer, LlamaServerConfig
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.logger import obtener_logger

logger = obtener_logger("tuning.ejecutor")

DIR_LOGS_TUNING = DIRECTORIO_RAIZ_GUARIDA / "logs_tuning"


def encontrar_puerto_libre(host: str = "127.0.0.1") -> int:
    """Encuentra un puerto TCP disponible dinámicamente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


@dataclass
class MetricasMemoriaIntento:
    mem_modelo_mb: float = 0.0
    mem_kv_mb: float = 0.0
    mem_compute_mb: float = 0.0
    ram_pico_mb: float = 0.0
    vram_pico_mb: float = 0.0
    gtt_pico_mb: float = 0.0


@dataclass
class ResultadoIntentoConfig:
    hash_config: str
    etapa: str
    args: dict[str, Any]
    estado: str  # "ok", "oom", "flag_invalido", "timeout", "crash", "podada"
    error_resumen: Optional[str] = None
    metricas_memoria: MetricasMemoriaIntento = field(default_factory=MetricasMemoriaIntento)
    log_path: Optional[Path] = None
    ejecuciones_crudo: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0


class MonitorMemoriaProceso:
    """Monitorea en segundo plano el consumo pico de RAM del árbol de procesos y VRAM."""

    def __init__(self, pid: int, intervalo_s: float = 0.1):
        self.pid = pid
        self.intervalo_s = intervalo_s
        self.ram_pico_bytes = 0
        self._detener_evento = threading.Event()
        self._hilo: Optional[threading.Thread] = None

    def _loop(self) -> None:
        try:
            padre = psutil.Process(self.pid)
        except Exception:
            return

        while not self._detener_evento.is_set():
            try:
                if not padre.is_running():
                    break
                total = padre.memory_info().rss
                for hijo in padre.children(recursive=True):
                    try:
                        total += hijo.memory_info().rss
                    except Exception:
                        pass
                if total > self.ram_pico_bytes:
                    self.ram_pico_bytes = total
            except Exception:
                pass
            time.sleep(self.intervalo_s)

    def iniciar(self) -> None:
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()

    def detener(self) -> float:
        self._detener_evento.set()
        if self._hilo:
            self._hilo.join(timeout=1.0)
        return self.ram_pico_bytes / (1024 * 1024)


class EjecutorIntentoLlama:
    """Gestiona el ciclo de vida aislado y seguro de un intento con una configuración de llama-server."""

    def __init__(self, dir_logs: Optional[Path] = None):
        self.dir_logs = dir_logs or DIR_LOGS_TUNING
        self.dir_logs.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def parsear_memoria_log(texto_log: str) -> tuple[float, float, float]:
        """Parsea los tamaños de buffer de modelo, kv y compute reportados por llama.cpp en MB."""
        m_mb = 0.0
        kv_mb = 0.0
        c_mb = 0.0

        for match in re.finditer(r"model buffer size\s*=\s*([\d\.]+)\s*(MiB|GiB|MB|GB)", texto_log, re.IGNORECASE):
            val = float(match.group(1))
            unit = match.group(2).upper()
            m_mb = val * 1024 if "G" in unit else val

        for match in re.finditer(r"kv buffer size\s*=\s*([\d\.]+)\s*(MiB|GiB|MB|GB)", texto_log, re.IGNORECASE):
            val = float(match.group(1))
            unit = match.group(2).upper()
            kv_mb = val * 1024 if "G" in unit else val

        for match in re.finditer(r"compute buffer size\s*=\s*([\d\.]+)\s*(MiB|GiB|MB|GB)", texto_log, re.IGNORECASE):
            val = float(match.group(1))
            unit = match.group(2).upper()
            c_mb = val * 1024 if "G" in unit else val

        return m_mb, kv_mb, c_mb

    @staticmethod
    def clasificar_fallo(texto_log: str, returncode: Optional[int]) -> tuple[str, str]:
        """Clasifica la causa del fallo analizando el log de llama.cpp."""
        low = texto_log.lower()
        if "out of memory" in low or "cuda error: out of memory" in low or "ggml_backend_alloc_ctx_tensors: failed" in low or "vk::device::allocatememory" in low:
            return "oom", "Memoria insuficiente (OOM / alloc failed en GPU/VRAM)"
        if any(k in low for k in ("unknown argument", "error: unknown option", "unrecognized option", "invalid argument", "error: invalid option")):
            return "flag_invalido", "Argumento o flag no soportado por el binario"
        if "failed to load model" in low or "error loading model" in low:
            return "crash", "Fallo al cargar pesos del modelo"
        if returncode is not None and returncode != 0:
            return "crash", f"Proceso abortó con código de salida {returncode}"
        return "crash", "Fallo no especificado durante la ejecución"

    def ejecutar_intento(
        self,
        config: LlamaServerConfig,
        hash_config: str,
        etapa: str,
        funcion_bateria: Callable[[ClienteLlamaOffline], list[dict[str, Any]]],
        timeout_arranque_s: float = 60.0,
    ) -> ResultadoIntentoConfig:
        """Arranca el servidor, ejecuta la batería, monitorea memoria y detiene limpiamente."""
        proceso = None
        monitor = None
        log_file = None
        log_path = None
        gestor = GestorLlamaServer()

        try:
            # Asegurar que ningún proceso llama-server previo retenga RAM o VRAM antes de iniciar el intento
            GestorLlamaServer.terminar_procesos_huerfanos("llama-server")
            time.sleep(0.4)

            puerto = config.port if config.port != 8083 else encontrar_puerto_libre(config.host)
            config.port = puerto

            nombre_log = f"bench_{etapa}_{hash_config[:12]}_{puerto}.log"
            log_path = self.dir_logs / nombre_log

            cliente = ClienteLlamaOffline(
                host=config.host,
                port=config.port,
                api_key=config.api_key,
            )

            log_file = open(log_path, "w", encoding="utf-8", errors="replace")
            texto_log_final = ""

            cmd = config.construir_comando()
            logger.info(f"Iniciando intento {etapa} ({hash_config[:8]}): {' '.join(cmd)}")
            proceso = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            gestor._proceso = proceso
            gestor._config_activa = config

            # Monitoreo de memoria
            monitor = MonitorMemoriaProceso(proceso.pid)
            monitor.iniciar()

            # Esperar a que el servidor responda /health
            inicio = time.time()
            servidor_listo = False
            while (time.time() - inicio) < timeout_arranque_s:
                if proceso.poll() is not None:
                    break
                if cliente.esta_disponible(timeout=0.8):
                    servidor_listo = True
                    break
                time.sleep(0.3)

            if not servidor_listo:
                cod = proceso.poll()
                log_file.flush()
                try:
                    texto_log_final = log_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

                estado_fallo, err_msg = self.clasificar_fallo(texto_log_final, cod)
                if cod is None:
                    estado_fallo = "timeout"
                    err_msg = f"Tiempo de espera agotado ({timeout_arranque_s}s) sin responder /health"

                return ResultadoIntentoConfig(
                    hash_config=hash_config,
                    etapa=etapa,
                    args=config.__dict__,
                    estado=estado_fallo,
                    error_resumen=err_msg,
                    log_path=log_path,
                )

            # Ejecutar batería de pruebas
            ejecuciones = funcion_bateria(cliente)

            # Extraer métricas de memoria
            ram_pico = monitor.detener() if monitor else 0.0
            log_file.flush()
            try:
                texto_log_final = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

            m_mb, kv_mb, c_mb = self.parsear_memoria_log(texto_log_final)
            hw = obtener_informacion_hardware()
            vram_gtt_pico = hw.gtt_disponible_gb * 1024 if hw.tiene_aceleracion_gpu else 0.0

            metricas_mem = MetricasMemoriaIntento(
                mem_modelo_mb=m_mb,
                mem_kv_mb=kv_mb,
                mem_compute_mb=c_mb,
                ram_pico_mb=ram_pico,
                vram_pico_mb=vram_gtt_pico,
                gtt_pico_mb=vram_gtt_pico,
            )

            return ResultadoIntentoConfig(
                hash_config=hash_config,
                etapa=etapa,
                args=config.__dict__,
                estado="ok",
                metricas_memoria=metricas_mem,
                log_path=log_path,
                ejecuciones_crudo=ejecuciones,
            )

        except Exception as e:
            logger.error(f"Error en intento {etapa} ({hash_config[:8]}): {e}", exc_info=True)
            return ResultadoIntentoConfig(
                hash_config=hash_config,
                etapa=etapa,
                args=config.__dict__,
                estado="crash",
                error_resumen=f"Excepción en ejecutor: {e}",
                log_path=log_path,
            )

        finally:
            if monitor:
                try:
                    monitor.detener()
                except Exception:
                    pass
            try:
                gestor.detener_servidor(timeout=3.0)
            except Exception:
                pass
            try:
                log_file.close()
            except Exception:
                pass
            time.sleep(0.5)
