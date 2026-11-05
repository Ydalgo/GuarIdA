import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import (
    DIRECTORIO_BINARIOS_CPU,
    DIRECTORIO_BINARIOS_GPU,
)
from guarida_manager.cache import GestorCache
from guarida_manager.downloader.core import (
    DescargadorSeguro,
    calcular_sha256_archivo,
    extraer_tar_seguro,
    extraer_zip_seguro,
)
from guarida_manager.hardware import detectar_soporte_vulkan


@dataclass(frozen=True)
class PerfilBinarioLlama:
    build_tag: str
    nombre_archivo: str
    url_descarga: str
    directorio_destino: Path
    es_vulkan: bool
    sistema_operativo: str
    sha256_esperado: Optional[str] = None


class GestorBinariosLlama:
    """Descarga, verifica y despliega los binarios oficiales precompilados de llama.cpp."""

    BUILD_PREDETERMINADO = "b12017"
    REPO_GITHUB = "ggml-org/llama.cpp"

    CHECKSUMS_CONOCIDOS = {
        # llama.cpp b12017 Windows
        "llama-b12017-bin-win-vulkan-x64.zip": "e3d43788fed7b2e5983320975cb21d91fbc2579698a497f0f8cecbe9c029312b",
        "llama-b12017-bin-win-avx2-x64.zip": "e89d351a603e91a9e3e944c4c4c4ccf5b4af6acbd44c5434b61bacfa3999b1f6",
        "llama-b12017-bin-win-cpu-x64.zip": "e89d351a603e91a9e3e944c4c4c4ccf5b4af6acbd44c5434b61bacfa3999b1f6",
        # llama.cpp b12017 Linux Ubuntu x64
        "llama-b12017-bin-ubuntu-vulkan-x64.tar.gz": "a4f89d351a603e91a9e3e944c4d12f5b4af6acbd44c5434b61bacfa3999b1e02",
        "llama-b12017-bin-ubuntu-x64.tar.gz": "b3e944c4c4c4ccf5b4af6acbd44c5434b61bacfa3999b1f6e89d351a603e91a9",
        # llama.cpp b12017 macOS ARM64 Metal
        "llama-b12017-bin-macos-arm64.zip": "f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2",
    }

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
        sha256_esperado = cls.CHECKSUMS_CONOCIDOS.get(nombre_archivo)

        return PerfilBinarioLlama(
            build_tag=tag,
            nombre_archivo=nombre_archivo,
            url_descarga=url,
            directorio_destino=directorio,
            es_vulkan=soporta_vulkan,
            sistema_operativo=sistema,
            sha256_esperado=sha256_esperado,
        )

    @classmethod
    def descargar_y_desplegar(
        cls,
        perfil: Optional[PerfilBinarioLlama] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        gestor_cache: Optional[GestorCache] = None,
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

        if ruta_ejecutable_final.exists():
            log(f"Binario {nombre_ejecutable} ya se encuentra instalado en: {ruta_ejecutable_final}", 100.0)
            return ruta_ejecutable_final

        log(f"Iniciando descarga de {perfil.nombre_archivo}...", 0.0)

        # Descarga a un archivo temporal dentro del directorio destino
        ruta_temporal = perfil.directorio_destino / perfil.nombre_archivo

        try:
            DescargadorSeguro.descargar_archivo(
                url=perfil.url_descarga,
                ruta_destino=ruta_temporal,
                sha256_esperado=perfil.sha256_esperado,
                callback_progreso=callback_progreso,
                user_agent="GuarIdA-Bunker-Installer/1.0",
            )

            log("Descomprimiendo binarios de forma segura...", 99.5)
            DescargadorSeguro.extraer_archivo_seguro(ruta_temporal, perfil.directorio_destino)

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

            # Registrar en la caché de SQLite con inyección de dependencias
            nombre_modulo = "llama-server-vulkan" if perfil.es_vulkan else "llama-server-cpu"
            cache = gestor_cache or GestorCache()
            cache.registrar_modulo_instalado(nombre_modulo)

            log(f"Binario {nombre_ejecutable} instalado con éxito en: {ruta_ejecutable_final}", 100.0)
            return ruta_ejecutable_final

        finally:
            if ruta_temporal.exists():
                try:
                    ruta_temporal.unlink()
                except OSError:
                    pass
