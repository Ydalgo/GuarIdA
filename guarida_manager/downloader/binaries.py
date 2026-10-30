import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import (
    DIRECTORIO_BINARIOS_CPU,
    DIRECTORIO_BINARIOS_GPU,
)
from guarida_manager.cache import GestorCache
from guarida_manager.hardware import detectar_soporte_vulkan


@dataclass(frozen=True)
class PerfilBinarioLlama:
    build_tag: str
    nombre_archivo: str
    url_descarga: str
    directorio_destino: Path
    es_vulkan: bool
    sistema_operativo: str


class GestorBinariosLlama:
    """Descarga, verifica y despliega los binarios oficiales precompilados de llama.cpp."""

    BUILD_PREDETERMINADO = "b12017"
    REPO_GITHUB = "ggml-org/llama.cpp"

    @classmethod
    def resolver_perfil_sistema(
        cls,
        forzar_cpu: bool = False,
        build_tag: Optional[str] = None,
    ) -> PerfilBinarioLlama:
        sistema = platform.system()
        tag = build_tag or cls.BUILD_PREDETERMINADO

        soporta_vulkan = detectar_soporte_vulkan() and not forzar_cpu
        directorio = DIRECTORIO_BINARIOS_GPU if soporta_vulkan else DIRECTORIO_BINARIOS_CPU

        if sistema == "Windows":
            if soporta_vulkan:
                nombre_archivo = f"llama-{tag}-bin-win-vulkan-x64.zip"
            else:
                nombre_archivo = f"llama-{tag}-bin-win-avx2-x64.zip"
        elif sistema == "Linux":
            if soporta_vulkan:
                nombre_archivo = f"llama-{tag}-bin-ubuntu-vulkan-x64.tar.gz"
            else:
                nombre_archivo = f"llama-{tag}-bin-ubuntu-x64.tar.gz"
        elif sistema == "Darwin":
            nombre_archivo = f"llama-{tag}-bin-macos-arm64.zip"
        else:
            raise NotImplementedError(f"Sistema operativo no soportado para descarga automática: {sistema}")

        url = f"https://github.com/{cls.REPO_GITHUB}/releases/download/{tag}/{nombre_archivo}"

        return PerfilBinarioLlama(
            build_tag=tag,
            nombre_archivo=nombre_archivo,
            url_descarga=url,
            directorio_destino=directorio,
            es_vulkan=soporta_vulkan,
            sistema_operativo=sistema,
        )

    @classmethod
    def descargar_y_desplegar(
        cls,
        perfil: Optional[PerfilBinarioLlama] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> Path:
        """Descarga el paquete oficial de llama.cpp, lo descomprime y registra el módulo."""
        if perfil is None:
            perfil = cls.resolver_perfil_sistema()

        perfil.directorio_destino.mkdir(parents=True, exist_ok=True)
        nombre_ejecutable = "llama-server.exe" if perfil.sistema_operativo == "Windows" else "llama-server"
        ruta_ejecutable_final = perfil.directorio_destino / nombre_ejecutable

        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        log(f"Iniciando descarga de {perfil.nombre_archivo}...", 0.0)

        # Descarga a un archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(perfil.nombre_archivo).suffix) as temp_file:
            ruta_temporal = Path(temp_file.name)

        try:
            peticion = urllib.request.Request(
                perfil.url_descarga,
                headers={"User-Agent": "GuarIdA-Bunker-Installer/1.0"},
            )

            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                longitud_total = respuesta.headers.get("Content-Length")
                tamano_total = int(longitud_total) if longitud_total else None

                descargado = 0
                chunk_size = 64 * 1024

                with open(ruta_temporal, "wb") as f_out:
                    while True:
                        fragmento = respuesta.read(chunk_size)
                        if not fragmento:
                            break
                        f_out.write(fragmento)
                        descargado += len(fragmento)

                        if tamano_total:
                            porcentaje = (descargado / tamano_total) * 100.0
                            log(f"Descargando {descargado / (1024**2):.1f} MB / {tamano_total / (1024**2):.1f} MB", porcentaje)
                        else:
                            log(f"Descargando {descargado / (1024**2):.1f} MB", 0.0)

            log("Descarga completada. Descomprimiendo binarios...", 100.0)

            # Descomprimir paquete
            if ruta_temporal.suffix == ".zip":
                with zipfile.ZipFile(ruta_temporal, "r") as zf:
                    zf.extractall(perfil.directorio_destino)
            elif ".tar" in ruta_temporal.name:
                with tarfile.open(ruta_temporal, "r:*") as tf:
                    tf.extractall(perfil.directorio_destino)

            # Asegurar permisos de ejecución en sistemas Unix
            if perfil.sistema_operativo != "Windows" and ruta_ejecutable_final.exists():
                os.chmod(ruta_ejecutable_final, 0o755)

            if not ruta_ejecutable_final.exists():
                # En algunos releases los binarios están en un subdirectorio build/bin
                candidatos = list(perfil.directorio_destino.rglob(nombre_ejecutable))
                if candidatos:
                    shutil.move(str(candidatos[0]), str(ruta_ejecutable_final))
                else:
                    raise FileNotFoundError(f"No se encontró {nombre_ejecutable} en el archivo descargado.")

            # Registrar en la caché de SQLite
            nombre_modulo = "llama-server-vulkan" if perfil.es_vulkan else "llama-server-cpu"
            gestor_cache = GestorCache()
            gestor_cache.registrar_modulo_instalado(nombre_modulo)

            log(f"Binario {nombre_ejecutable} instalado con éxito en: {ruta_ejecutable_final}", 100.0)
            return ruta_ejecutable_final

        finally:
            if ruta_temporal.exists():
                try:
                    os.remove(ruta_temporal)
                except Exception:
                    pass
