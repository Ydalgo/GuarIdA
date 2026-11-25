from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import (
    DIRECTORIO_MODELOS,
    RUTA_CONFIG_PREDETERMINADA,
)
from guarida_manager.cache import GestorCache
from guarida_manager.downloader.binaries import GestorBinariosLlama
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.config_store import (
    ConfiguracionBunker,
    guardar_configuracion_bunker,
)
from guarida_manager.downloader.models import (
    CatalogoModelos,
    CestaDescarga,
    DescargadorModelos,
)
from guarida_manager.downloader.packages import GestorPaquetesPython
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.roles import AsignacionRoles


class OrquestadorAprovisionamiento:
    """Orquestador de aprovisionamiento único multirrol para funcionamiento 100% offline."""

    PAQUETES_OPCIONALES = GestorPaquetesPython.PAQUETES_OPCIONALES
    PAQUETES_PINNED = GestorPaquetesPython.PAQUETES_PINNED

    def __init__(
        self,
        ruta_config: Optional[Path] = None,
        gestor_cache: Optional[GestorCache] = None,
        directorio_modelos: Optional[Path] = None,
    ) -> None:
        self.ruta_config = ruta_config or RUTA_CONFIG_PREDETERMINADA
        self.cache = gestor_cache or GestorCache()
        self.directorio_modelos = directorio_modelos or DIRECTORIO_MODELOS

    @staticmethod
    def verificar_paquete_python(nombre_modulo: str) -> bool:
        import importlib
        importlib.invalidate_caches()
        return GestorPaquetesPython.verificar_paquete(nombre_modulo)

    @classmethod
    def instalar_paquete_pip(cls, nombre_paquete: str, permitir_pip_runtime: bool = True) -> bool:
        """Instala dependencias mediante pip con versiones pineadas estrictas (S7)."""
        return GestorPaquetesPython.instalar_paquete_pip(
            nombre_paquete=nombre_paquete,
            permitir_pip_runtime=permitir_pip_runtime,
        )

    def ejecutar_aprovisionamiento_lote(
        self,
        region: RegionNormativa = RegionNormativa.ES_EU,
        interfaz: str = "terminal",
        instalar_pdf: bool = True,
        modelos_ids_lote: Optional[list[str]] = None,
        roles: Optional[AsignacionRoles] = None,
        clave_maestra_boveda: Optional[str] = None,
        permitir_pip_runtime: bool = True,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> ConfiguracionBunker:
        """Aprovisiona todo el búnker en una única sesión de conexión."""
        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        log("Iniciando aprovisionamiento del Búnker GuarIdA...", 0.0)

        # 1. Hardware y espacio en disco
        hardware = obtener_informacion_hardware()
        log(f"Hardware: {hardware.modelo_cpu} | GPU: {hardware.nombre_gpu_principal}", 2.0)

        # 2. Dependencias de Python para entorno offline
        if instalar_pdf and not self.verificar_paquete_python("reportlab"):
            if permitir_pip_runtime:
                log("Instalando soporte para generación de informes PDF offline (reportlab)...", 5.0)
                self.instalar_paquete_pip("reportlab", permitir_pip_runtime=True)
            else:
                log("Aviso: 'reportlab' no instalado y pip runtime está deshabilitado.", 5.0)

        if interfaz == "web" and not self.verificar_paquete_python("fastapi"):
            if permitir_pip_runtime:
                log("Instalando dependencias de interfaz web offline (fastapi, uvicorn)...", 8.0)
                self.instalar_paquete_pip("fastapi", permitir_pip_runtime=True)
                self.instalar_paquete_pip("uvicorn", permitir_pip_runtime=True)
            else:
                log("Aviso: dependencias web no instaladas y pip runtime deshabilitado.", 8.0)
        elif interfaz == "escritorio" and not self.verificar_paquete_python("PyQt6"):
            if permitir_pip_runtime:
                log("Instalando dependencias de interfaz gráfica offline (PyQt6)...", 8.0)
                self.instalar_paquete_pip("PyQt6", permitir_pip_runtime=True)
            else:
                log("Aviso: 'PyQt6' no instalado y pip runtime está deshabilitado.", 8.0)

        # 3. Descarga y verificación del ecosistema de herramientas (llama-server, git, ripgrep)
        log("Verificando herramientas del sistema y binarios del búnker...", 10.0)
        perfil_binario = GestorBinariosLlama.resolver_perfil_sistema()
        try:
            GestorBinariosLlama.descargar_y_desplegar(
                perfil=perfil_binario,
                callback_progreso=lambda msg, p: log(f"Binario inferencia: {msg}", 10.0 + (p * 0.12)),
                gestor_cache=self.cache,
            )
        except Exception as e:
            log(f"Aviso: No se pudo desplegar automáticamente llama-server ({e}). Se requerirá binario local o compilación manual.", 22.0)

        herramientas_listas = []
        if GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server"):
            herramientas_listas.append("llama-server")

        for h in GestorHerramientasBunker.verificar_todas_herramientas():
            if h.id == "llama-server":
                continue
            if h.instalada:
                log(f"Herramienta disponible: {h.nombre} ({h.version or 'OK'})", 24.0)
                herramientas_listas.append(h.id)
            else:
                log(f"Descargando herramienta portátil: {h.nombre}...", 24.0)
                try:
                    GestorHerramientasBunker.descargar_y_desplegar(h.id, gestor_cache=self.cache)
                    herramientas_listas.append(h.id)
                except Exception as e:
                    log(f"Advertencia: no se pudo desplegar automáticamente {h.nombre}: {e}", 24.0)

        # 4. Resolver lista de modelos a descargar
        ids_a_descargar = modelos_ids_lote or [
            "qwen2.5-coder-7b-q4",
            "qwen2.5-3b-chat-q4",
            "bge-m3-q4",
        ]

        descargador = DescargadorModelos(
            directorio_modelos=self.directorio_modelos,
            gestor_cache=self.cache,
        )
        modelos_definiciones = []
        for mid in ids_a_descargar:
            def_m = CatalogoModelos.obtener_modelo(mid)
            if def_m:
                modelos_definiciones.append(def_m)

        cesta = CestaDescarga(modelos=modelos_definiciones)
        suficiente_disco, libre_gb = cesta.verificar_espacio_disco(descargador.directorio_modelos)
        log(f"Espacio libre en disco: {libre_gb:.1f} GB (Requerido: {cesta.tamano_total_gb:.1f} GB)", 28.0)

        if not suficiente_disco:
            log(f"[ALERTA] Espacio en disco muy ajustado para la cesta ({libre_gb:.1f} GB libres).", 28.0)

        # 5. Descarga de modelos de la cesta
        modelos_descargados = []
        try:
            descargador.descargar_cesta(
                cesta=cesta,
                region=region,
                callback_progreso=lambda msg, p: log(msg, 30.0 + (p * 0.65)),
                permitir_inseguro=True,
            )
            modelos_descargados = [m.id for m in modelos_definiciones]
        except Exception as e:
            log(f"Advertencia durante descarga de cesta ({e}). Registrando modelos descargados...", 95.0)
            modelos_descargados = [m.id for m in modelos_definiciones if (self.directorio_modelos / m.filename).exists()]

        # 6. Roles y sellado de configuración
        roles_obj = roles or AsignacionRoles()
        fecha_actual = datetime.now(timezone.utc).isoformat()

        tiene_pdf = self.verificar_paquete_python("reportlab")
        tiene_binario = bool(GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server"))
        tiene_git = "git" in herramientas_listas
        todos_modelos = len(modelos_descargados) == len(modelos_definiciones)

        if tiene_binario and tiene_git and todos_modelos:
            estado_bunker = "OFFLINE_COMPLETO"
        else:
            estado_bunker = "PARCIALMENTE_APROVISIONADO"

        configuracion = ConfiguracionBunker(
            region=region.value,
            interfaz_preferida=interfaz,
            soporte_informes_pdf=tiene_pdf,
            roles=roles_obj.resumen_roles(),
            modelos_instalados=modelos_descargados,
            herramientas_instaladas=herramientas_listas,
            binario_inferencia_instalado=tiene_binario,
            cifrado_postcuantico_activo=bool(clave_maestra_boveda),
            estado_bunker=estado_bunker,
            fecha_aprovisionamiento=fecha_actual,
        )

        guardar_configuracion_bunker(
            configuracion=configuracion,
            ruta_config=self.ruta_config,
            clave_maestra_boveda=clave_maestra_boveda,
        )

        self.cache.registrar_modulo_instalado("bunker-offline-multirole")
        log("¡Aprovisionamiento multirrol finalizado! El búnker está listo para operar 100% desconectado.", 100.0)
        return configuracion
