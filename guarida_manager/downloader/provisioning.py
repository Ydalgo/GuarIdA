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
from guarida_manager.downloader.compliance import GestorCumplimientoNormativo, RegionNormativa
from guarida_manager.downloader.crypto import BovedaCriptograficaPostcuantica
from guarida_manager.downloader.models import CatalogoModelos, DescargadorModelos
from guarida_manager.hardware import obtener_informacion_hardware


@dataclass
class ConfiguracionBunker:
    region: str
    interfaz_preferida: str           # "terminal", "web", "escritorio"
    soporte_informes_pdf: bool
    modelo_coder_id: str
    modelo_embedding_id: str
    binario_inferencia_instalado: bool
    cifrado_postcuantico_activo: bool
    estado_bunker: str                # "PENDIENTE_APROVISIONAMIENTO", "OFFLINE_COMPLETO"
    fecha_aprovisionamiento: Optional[str] = None


class OrquestadorAprovisionamiento:
    """Orquestador de instalación y aprovisionamiento único para funcionamiento 100% offline."""

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
        """Comprueba si un módulo de Python está disponible en el entorno actual."""
        return importlib.util.find_spec(nombre_modulo) is not None

    @classmethod
    def instalar_paquete_pip(cls, nombre_paquete: str) -> bool:
        """Instala un paquete en el entorno virtual durante la ventana única de conexión."""
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", nombre_paquete]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            return True
        except Exception:
            return False

    def ejecutar_aprovisionamiento(
        self,
        region: RegionNormativa = RegionNormativa.ES_EU,
        interfaz: str = "terminal",
        instalar_pdf: bool = True,
        modelo_coder_id: str = "qwen2.5-coder-7b-q4",
        modelo_embedding_id: str = "nomic-embed-text-v1.5",
        clave_maestra_boveda: Optional[str] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> ConfiguracionBunker:
        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        log("Iniciando aprovisionamiento del Búnker GuarIdA...", 0.0)

        # 1. Diagnóstico de hardware para verificar viabilidad
        hardware = obtener_informacion_hardware()
        log(f"Hardware detectado: {hardware.modelo_cpu} | GPU: {hardware.nombre_gpu_principal}", 5.0)

        # 2. Instalar paquetes de Python necesarios para funciones offline solicitadas
        if instalar_pdf and not self.verificar_paquete_python("reportlab"):
            log("Instalando soporte para generación de informes PDF offline (reportlab)...", 10.0)
            self.instalar_paquete_pip("reportlab")

        if interfaz == "web" and not self.verificar_paquete_python("fastapi"):
            log("Instalando dependencias de interfaz web offline (fastapi, uvicorn)...", 15.0)
            self.instalar_paquete_pip("fastapi")
            self.instalar_paquete_pip("uvicorn")
        elif interfaz == "escritorio" and not self.verificar_paquete_python("PyQt6"):
            log("Instalando dependencias de interfaz gráfica offline (PyQt6)...", 15.0)
            self.instalar_paquete_pip("PyQt6")

        # 3. Descarga y despliegue del binario llama-server
        log("Descargando binario nativo oficial de inferencia llama.cpp...", 20.0)
        perfil_binario = GestorBinariosLlama.resolver_perfil_sistema()
        GestorBinariosLlama.descargar_y_desplegar(
            perfil=perfil_binario,
            callback_progreso=lambda msg, p: log(f"Binario: {msg}", 20.0 + (p * 0.2)),
        )

        # 4. Descarga del modelo de embeddings (para memoria y árboles de nodos)
        descargador = DescargadorModelos()
        mod_emb = CatalogoModelos.obtener_modelo(modelo_embedding_id)
        if mod_emb:
            log(f"Descargando modelo de embeddings para árboles de nodos: {mod_emb.filename}...", 40.0)
            descargador.descargar_modelo(
                modelo=mod_emb,
                region=region,
                callback_progreso=lambda msg, p: log(f"Embeddings: {msg}", 40.0 + (p * 0.2)),
            )

        # 5. Descarga del modelo de programación principal (Coder)
        mod_coder = CatalogoModelos.obtener_modelo(modelo_coder_id)
        if mod_coder:
            log(f"Descargando modelo principal de código: {mod_coder.filename}...", 60.0)
            descargador.descargar_modelo(
                modelo=mod_coder,
                region=region,
                callback_progreso=lambda msg, p: log(f"Coder: {msg}", 60.0 + (p * 0.35)),
            )

        # 6. Generación y almacenamiento de la configuración del Búnker
        fecha_actual = datetime.now(timezone.utc).isoformat()
        configuracion = ConfiguracionBunker(
            region=region.value,
            interfaz_preferida=interfaz,
            soporte_informes_pdf=instalar_pdf,
            modelo_coder_id=modelo_coder_id,
            modelo_embedding_id=modelo_embedding_id,
            binario_inferencia_instalado=True,
            cifrado_postcuantico_activo=bool(clave_maestra_boveda),
            estado_bunker="OFFLINE_COMPLETO",
            fecha_aprovisionamiento=fecha_actual,
        )

        self.ruta_config.parent.mkdir(parents=True, exist_ok=True)
        datos_json = json.dumps(asdict(configuracion), indent=2)

        if clave_maestra_boveda:
            log("Cifrando configuración del búnker con bóveda criptográfica postcuántica...", 97.0)
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

        # Guardar también archivo base local
        with open(self.ruta_config, "w", encoding="utf-8") as f:
            f.write(datos_json)

        self.cache.registrar_modulo_instalado("bunker-offline-core")
        log("¡Aprovisionamiento completado con éxito! El Búnker está listo para operar 100% offline.", 100.0)
        return configuracion
