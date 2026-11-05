import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import (
    DIRECTORIO_BINARIOS_CPU,
    DIRECTORIO_BINARIOS_GPU,
    DIRECTORIO_HERRAMIENTAS,
)
from guarida_manager.cache import GestorCache
from guarida_manager.downloader.core import DescargadorSeguro
from guarida_manager.downloader.binaries import GestorBinariosLlama


@dataclass(frozen=True)
class DefinicionHerramienta:
    id: str
    nombre: str
    descripcion: str
    es_critica: bool
    comando_comprobacion: list[str]
    nombre_binario_final: str
    url_win_x64: Optional[str] = None
    url_linux_x64: Optional[str] = None
    sha256_win_x64: Optional[str] = None
    sha256_linux_x64: Optional[str] = None


@dataclass(frozen=True)
class EstadoHerramienta:
    id: str
    nombre: str
    instalada: bool
    es_critica: bool
    ruta: Optional[Path]
    version: Optional[str]
    descripcion: str


class GestorHerramientasBunker:
    """Gestiona, verifica y descarga las herramientas de sistema y binarios del búnker offline."""

    HERRAMIENTAS: dict[str, DefinicionHerramienta] = {
        "llama-server": DefinicionHerramienta(
            id="llama-server",
            nombre="llama-server (Motor de Inferencia)",
            descripcion="Servidor oficial de inferencia local de llama.cpp con aceleración Vulkan o CPU.",
            es_critica=True,
            comando_comprobacion=["--version"],
            nombre_binario_final="llama-server.exe" if platform.system() == "Windows" else "llama-server",
        ),
        "git": DefinicionHerramienta(
            id="git",
            nombre="Git (Control de Versiones y Worktrees)",
            descripcion="Control de versiones necesario para crear worktrees aislados donde el Coder aplica parches.",
            es_critica=True,
            comando_comprobacion=["--version"],
            nombre_binario_final="git.exe" if platform.system() == "Windows" else "git",
            # MinGit Portable para Windows (versión oficial ligera sin instalador)
            url_win_x64="https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/MinGit-2.47.0.2-64-bit.zip",
            url_linux_x64=None,  # En Linux habitualmente forma parte del sistema base
            sha256_win_x64="c4a5d3a2adda98b25fe59349733fca56b3843360b962dba5535282a9d8120b31",
        ),
        "ripgrep": DefinicionHerramienta(
            id="ripgrep",
            nombre="ripgrep (Búsqueda Ultrarrápida de Código)",
            descripcion="Motor de búsqueda en código a hipervelocidad offline para navegación y AST del agente.",
            es_critica=False,
            comando_comprobacion=["--version"],
            nombre_binario_final="rg.exe" if platform.system() == "Windows" else "rg",
            url_win_x64="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-pc-windows-msvc.zip",
            url_linux_x64="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz",
            sha256_win_x64="d0f534024c42afd6cb4d38907c25cd2b249b79bbe6cc1dbee8e3e37c2b6e25a1",
            sha256_linux_x64="4cf9f2741e6c465ffdb7c26f38056a59e2a2544b51f7cc128ef28337eeae4d8e",
        ),
    }

    @classmethod
    def resolver_ruta_ejecutable(cls, herramienta_id: str) -> Optional[Path]:
        """Localiza el ejecutable de una herramienta en su carpeta aislada, en el búnker o en PATH."""
        herramienta = cls.HERRAMIENTAS.get(herramienta_id)
        if not herramienta:
            return None

        binario_nombre = herramienta.nombre_binario_final
        dir_herramienta = DIRECTORIO_HERRAMIENTAS / herramienta_id

        # 1. Comprobar rutas específicas por herramienta
        rutas_preferidas: list[Path] = []
        if herramienta_id == "git":
            rutas_preferidas.extend([
                dir_herramienta / "cmd" / binario_nombre,
                dir_herramienta / "bin" / binario_nombre,
                DIRECTORIO_HERRAMIENTAS / "cmd" / binario_nombre,
            ])
        elif herramienta_id == "ripgrep":
            rutas_preferidas.extend([
                dir_herramienta / binario_nombre,
                DIRECTORIO_HERRAMIENTAS / binario_nombre,
            ])
        elif herramienta_id == "llama-server":
            rutas_preferidas.extend([
                DIRECTORIO_BINARIOS_GPU / binario_nombre,
                DIRECTORIO_BINARIOS_CPU / binario_nombre,
            ])

        for c in rutas_preferidas:
            try:
                if c.exists() and os.access(c, os.X_OK if platform.system() != "Windows" else os.F_OK):
                    return c
            except (OSError, PermissionError):
                continue

        try:
            if dir_herramienta.exists():
                candidatos_dir = sorted(dir_herramienta.rglob(binario_nombre))
                for c in candidatos_dir:
                    try:
                        if c.exists() and os.access(c, os.X_OK if platform.system() != "Windows" else os.F_OK):
                            return c
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass

        # 2. Comprobar en el PATH global del sistema
        en_path = shutil.which(binario_nombre.replace(".exe", ""))
        if en_path:
            return Path(en_path)

        return None

    @classmethod
    def verificar_estado_herramienta(cls, herramienta_id: str) -> EstadoHerramienta:
        herramienta = cls.HERRAMIENTAS[herramienta_id]
        ruta = cls.resolver_ruta_ejecutable(herramienta_id)

        if not ruta:
            return EstadoHerramienta(
                id=herramienta.id,
                nombre=herramienta.nombre,
                instalada=False,
                es_critica=herramienta.es_critica,
                ruta=None,
                version=None,
                descripcion=herramienta.descripcion,
            )

        # Intentar ejecutar comando de versión
        version_str = None
        try:
            cmd = [str(ruta)] + herramienta.comando_comprobacion
            proceso = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            salida = (proceso.stdout or proceso.stderr).strip().splitlines()
            if salida:
                version_str = salida[0].strip()
        except Exception:
            version_str = "Instalada (sin respuesta de versión)"

        return EstadoHerramienta(
            id=herramienta.id,
            nombre=herramienta.nombre,
            instalada=True,
            es_critica=herramienta.es_critica,
            ruta=ruta,
            version=version_str,
            descripcion=herramienta.descripcion,
        )

    @classmethod
    def verificar_todas_herramientas(cls) -> list[EstadoHerramienta]:
        return [cls.verificar_estado_herramienta(hid) for hid in cls.HERRAMIENTAS]

    @classmethod
    def descargar_y_desplegar(
        cls,
        herramienta_id: str,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        gestor_cache: Optional[GestorCache] = None,
    ) -> Path:
        """Descarga e integra una herramienta portable en el búnker con inyección de caché."""
        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        herramienta = cls.HERRAMIENTAS.get(herramienta_id)
        if not herramienta:
            raise ValueError(f"Herramienta desconocida: {herramienta_id}")

        ruta_existente = cls.resolver_ruta_ejecutable(herramienta_id)
        if ruta_existente:
            log(f"Herramienta {herramienta.nombre} ya disponible en: {ruta_existente}", 100.0)
            return ruta_existente

        # Caso especial para llama-server
        if herramienta_id == "llama-server":
            perfil = GestorBinariosLlama.resolver_perfil_sistema()
            return GestorBinariosLlama.descargar_y_desplegar(
                perfil=perfil,
                callback_progreso=callback_progreso,
                gestor_cache=gestor_cache,
            )

        sistema = platform.system()
        url = herramienta.url_win_x64 if sistema == "Windows" else herramienta.url_linux_x64

        if not url:
            raise NotImplementedError(
                f"No hay paquete de descarga automática directa para {herramienta.nombre} en {sistema}. "
                "Por favor, instala la herramienta mediante el gestor de paquetes de tu distribución."
            )

        dir_herramienta = DIRECTORIO_HERRAMIENTAS / herramienta_id
        dir_herramienta.mkdir(parents=True, exist_ok=True)
        log(f"Iniciando descarga de {herramienta.nombre}...", 0.0)

        nombre_archivo_temp = Path(url).name or f"{herramienta_id}.zip"
        ruta_temporal = dir_herramienta / nombre_archivo_temp
        sha256_esperado = herramienta.sha256_win_x64 if sistema == "Windows" else herramienta.sha256_linux_x64

        try:
            DescargadorSeguro.descargar_archivo(
                url=url,
                ruta_destino=ruta_temporal,
                sha256_esperado=sha256_esperado,
                callback_progreso=callback_progreso,
                user_agent="GuarIdA-Tools-Installer/1.0",
            )

            log(f"Descomprimiendo {herramienta.nombre} de forma segura en {dir_herramienta}...", 90.0)
            DescargadorSeguro.extraer_archivo_seguro(ruta_temporal, dir_herramienta)

            ruta_resuelta = cls.resolver_ruta_ejecutable(herramienta_id)

            if not ruta_resuelta:
                raise FileNotFoundError(f"No se encontró el binario {herramienta.nombre_binario_final} tras la extracción en {dir_herramienta}.")

            if sistema != "Windows":
                os.chmod(ruta_resuelta, 0o755)

            # Registrar en la caché con inyección de dependencias
            cache = gestor_cache or GestorCache()
            cache.registrar_modulo_instalado(f"tool-{herramienta_id}")
            log(f"Herramienta {herramienta.nombre} instalada con éxito en: {ruta_resuelta}", 100.0)
            return ruta_resuelta

        finally:
            if ruta_temporal.exists():
                try:
                    ruta_temporal.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    print("=== GUARIDA: ESTADO DE HERRAMIENTAS Y BINARIOS DEL BÚNKER ===")
    estados = GestorHerramientasBunker.verificar_todas_herramientas()
    for h in estados:
        estado_str = f"INSTALADA ({h.version})" if h.instalada else "NO DETECTADA"
        critica_str = "[CRÍTICA]" if h.es_critica else "[OPCIONAL]"
        print(f"* {h.nombre} {critica_str}: {estado_str}")
        print(f"  - Ruta: {h.ruta or 'Pendiente de descarga'}")
        print(f"  - Uso:  {h.descripcion}\n")

