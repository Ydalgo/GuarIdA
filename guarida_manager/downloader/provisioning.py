import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import RUTA_CONFIG_PREDETERMINADA
from guarida_manager.cache import GestorCache
from guarida_manager.downloader.binaries import GestorBinariosLlama
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.crypto import BovedaCriptograficaPostcuantica
from guarida_manager.downloader.models import (
    CatalogoModelos,
    CestaDescarga,
    DescargadorModelos,
)
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.roles import AsignacionRoles


@dataclass
class ConfiguracionBunker:
    region: str
    interfaz_preferida: str                   # "terminal", "web", "escritorio"
    soporte_informes_pdf: bool
    roles: dict[str, str]                     # Mapeo de roles a modelos
    modelos_instalados: list[str]             # Todos los modelos descargados en lote
    binario_inferencia_instalado: bool
    cifrado_postcuantico_activo: bool
    estado_bunker: str                        # "PENDIENTE_APROVISIONAMIENTO", "OFFLINE_COMPLETO"
    fecha_aprovisionamiento: Optional[str] = None


class OrquestadorAprovisionamiento:
    """Orquestador de aprovisionamiento único multirrol para funcionamiento 100% offline."""

    PAQUETES_OPCIONALES = {
        "pdf": "reportlab",
        "web": "fastapi",
        "escritorio": "PyQt6",
    }

    def __init__(self, ruta_config: Optional[Path] = None) -> None:
        self.ruta_config = ruta_config or RUTA_CONFIG_PREDETERMINADA
        self.cache = GestorCache()

    @staticmethod
    def verificar_paquete_python(nombre_modulo: str) -> bool:
        return importlib.util.find_spec(nombre_modulo) is not None

    @classmethod
    def instalar_paquete_pip(cls, nombre_paquete: str) -> bool:
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", nombre_paquete]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            return True
        except Exception:
            return False

    def ejecutar_aprovisionamiento_lote(
        self,
        region: RegionNormativa = RegionNormativa.ES_EU,
        interfaz: str = "terminal",
        instalar_pdf: bool = True,
        modelos_ids_lote: Optional[list[str]] = None,
        roles: Optional[AsignacionRoles] = None,
        clave_maestra_boveda: Optional[str] = None,
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
            log("Instalando soporte para generación de informes PDF offline (reportlab)...", 5.0)
            self.instalar_paquete_pip("reportlab")

        if interfaz == "web" and not self.verificar_paquete_python("fastapi"):
            log("Instalando dependencias de interfaz web offline (fastapi, uvicorn)...", 8.0)
            self.instalar_paquete_pip("fastapi")
            self.instalar_paquete_pip("uvicorn")
        elif interfaz == "escritorio" and not self.verificar_paquete_python("PyQt6"):
            log("Instalando dependencias de interfaz gráfica offline (PyQt6)...", 8.0)
            self.instalar_paquete_pip("PyQt6")

        # 3. Descarga del motor de inferencia llama.cpp
        log("Descargando binario oficial de inferencia llama.cpp...", 12.0)
        perfil_binario = GestorBinariosLlama.resolver_perfil_sistema()
        GestorBinariosLlama.descargar_y_desplegar(
            perfil=perfil_binario,
            callback_progreso=lambda msg, p: log(f"Binario: {msg}", 12.0 + (p * 0.15)),
        )

        # 4. Resolver lista de modelos a descargar
        ids_a_descargar = modelos_ids_lote or [
            "qwen2.5-coder-7b-q4",
            "qwen2.5-3b-chat-q4",
            "bge-m3-q4",
        ]

        descargador = DescargadorModelos()
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

        # 5. Descarga de todos los modelos de la cesta
        descargador.descargar_cesta(
            cesta=cesta,
            region=region,
            callback_progreso=lambda msg, p: log(msg, 30.0 + (p * 0.65)),
        )

        # 6. Roles y sellado de configuración
        roles_obj = roles or AsignacionRoles()
        fecha_actual = datetime.now(timezone.utc).isoformat()

        configuracion = ConfiguracionBunker(
            region=region.value,
            interfaz_preferida=interfaz,
            soporte_informes_pdf=instalar_pdf,
            roles=roles_obj.resumen_roles(),
            modelos_instalados=[m.id for m in modelos_definiciones],
            binario_inferencia_instalado=True,
            cifrado_postcuantico_activo=bool(clave_maestra_boveda),
            estado_bunker="OFFLINE_COMPLETO",
            fecha_aprovisionamiento=fecha_actual,
        )

        self.ruta_config.parent.mkdir(parents=True, exist_ok=True)
        datos_json = json.dumps(asdict(configuracion), indent=2, ensure_ascii=False)

        if clave_maestra_boveda:
            log("Cifrando configuración del búnker con bóveda postcuántica...", 98.0)
            sobre = BovedaCriptograficaPostcuantica.cifrar_datos(datos_json, clave_maestra_boveda)
            ruta_cifrada = self.ruta_config.with_suffix(".pqc.json")
            with open(ruta_cifrada, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": sobre.version,
                        "algoritmo": sobre.algoritmo,
                        "salt_hex": sobre.salt_hex,
                        "nonce_hex": sobre.nonce_hex,
                        "datos_cifrados_b64": sobre.datos_cifrados_b64,
                        "mac_autenticacion_hex": sobre.mac_autenticacion_hex,
                    },
                    f,
                    indent=2,
                )

        with open(self.ruta_config, "w", encoding="utf-8") as f:
            f.write(datos_json)

        self.cache.registrar_modulo_instalado("bunker-offline-multirole")
        log("¡Aprovisionamiento multirrol finalizado! El búnker está listo para operar 100% desconectado.", 100.0)
        return configuracion
