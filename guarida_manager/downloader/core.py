import hashlib
import hmac
import os
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


def extraer_zip_seguro(archivo_zip: Path, destino: Path) -> None:
    """Extrae un archivo ZIP validando que ninguna ruta sufra Zip Slip / Path Traversal."""
    destino = destino.resolve()
    with zipfile.ZipFile(archivo_zip, "r") as zf:
        for info in zf.infolist():
            ruta_extraida = (destino / info.filename).resolve()
            if not (str(ruta_extraida) == str(destino) or str(ruta_extraida).startswith(str(destino) + os.sep)):
                raise ValueError(f"Detección de Zip Slip / Path Traversal malicioso en archivo: {info.filename}")
        zf.extractall(destino)


def extraer_tar_seguro(archivo_tar: Path, destino: Path) -> None:
    """Extrae un archivo TAR aplicando filtrado de seguridad data o validación estricta de rutas."""
    destino = destino.resolve()
    with tarfile.open(archivo_tar, "r:*") as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(destino, filter="data")
        else:
            for member in tf.getmembers():
                ruta_extraida = (destino / member.name).resolve()
                if not (str(ruta_extraida) == str(destino) or str(ruta_extraida).startswith(str(destino) + os.sep)):
                    raise ValueError(f"Detección de Tar Slip / Path Traversal malicioso en archivo: {member.name}")
            tf.extractall(destino)


def calcular_sha256_archivo(ruta_archivo: Path) -> str:
    """Calcula el hash SHA-256 de un archivo en bloques de 1 MB."""
    hasher = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


class DescargadorSeguro:
    """Motor centralizado de descarga atómica, reintentos con backoff, verificación criptográfica y extracción segura."""

    CHUNK_SIZE = 128 * 1024  # 128 KB por fragmento

    @classmethod
    def descargar_archivo(
        cls,
        url: str,
        ruta_destino: Path,
        sha256_esperado: Optional[str] = None,
        permitir_reanudacion: bool = False,
        permitir_inseguro: bool = False,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        timeout: float = 30.0,
        user_agent: str = "GuarIdA-Bunker-Downloader/1.0",
        max_reintentos: int = 3,
        reintento_backoff: float = 1.0,
    ) -> Path:
        """Descarga un archivo remoto con reintentos exponenciales, de forma atómica y verifica obligatoriamente su hash."""
        if not sha256_esperado and not permitir_inseguro:
            raise ValueError(
                f"Descarga insegura rechazada: falta el hash SHA-256 esperado para '{ruta_destino.name}'. "
                f"El búnker opera bajo política 'fail-closed'. Proporcione sha256_esperado o use permitir_inseguro=True."
            )

        ruta_destino.parent.mkdir(parents=True, exist_ok=True)

        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        ruta_parcial = ruta_destino.with_suffix(ruta_destino.suffix + ".part")

        for intento in range(max_reintentos):
            bytes_existentes = ruta_parcial.stat().st_size if (permitir_reanudacion and ruta_parcial.exists()) else 0
            encabezados = {"User-Agent": user_agent}
            if bytes_existentes > 0:
                encabezados["Range"] = f"bytes={bytes_existentes}-"
                log(f"Reanudando descarga de {ruta_destino.name} desde {bytes_existentes / (1024**2):.1f} MB...", 0.0)
            else:
                log(f"Iniciando descarga de {ruta_destino.name}...", 0.0)

            peticion = urllib.request.Request(url, headers=encabezados)

            try:
                with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
                    codigo_http = getattr(respuesta, "status", getattr(respuesta, "code", 200))

                    if bytes_existentes > 0 and codigo_http == 200:
                        bytes_existentes = 0
                        modo_apertura = "wb"
                    elif bytes_existentes > 0 and codigo_http == 206:
                        modo_apertura = "ab"
                    else:
                        modo_apertura = "wb"

                    longitud_encabezado = respuesta.headers.get("Content-Length")
                    tamano_total = (int(longitud_encabezado) + bytes_existentes) if longitud_encabezado else None

                    descargado = bytes_existentes
                    ultimo_tiempo_log = time.time()
                    ultimo_pct_log = -1.0

                    with open(ruta_parcial, modo_apertura) as f_out:
                        while True:
                            fragmento = respuesta.read(cls.CHUNK_SIZE)
                            if not fragmento:
                                break
                            f_out.write(fragmento)
                            descargado += len(fragmento)

                            ahora = time.time()
                            if tamano_total:
                                porcentaje = min(100.0, max(0.0, (descargado / tamano_total) * 100.0))
                                if (ahora - ultimo_tiempo_log >= 0.25) or (porcentaje - ultimo_pct_log >= 2.0) or (porcentaje >= 99.9):
                                    log(
                                        f"Descargando {ruta_destino.name}: {descargado / (1024**2):.1f}/{tamano_total / (1024**2):.1f} MB",
                                        porcentaje,
                                    )
                                    ultimo_tiempo_log = ahora
                                    ultimo_pct_log = porcentaje
                            else:
                                if ahora - ultimo_tiempo_log >= 0.5:
                                    log(f"Descargando {ruta_destino.name}: {descargado / (1024**2):.1f} MB", 0.0)
                                    ultimo_tiempo_log = ahora

                # Verificación criptográfica SHA-256
                if sha256_esperado:
                    log(f"Verificando integridad criptográfica SHA-256 de {ruta_destino.name}...", 99.0)
                    hash_calculado = calcular_sha256_archivo(ruta_parcial)
                    if not hmac.compare_digest(hash_calculado.lower(), sha256_esperado.lower()):
                        if ruta_parcial.exists():
                            try:
                                ruta_parcial.unlink()
                            except OSError:
                                pass
                        raise ValueError(
                            f"Fallo de integridad SHA-256 en {ruta_destino.name}: "
                            f"esperado {sha256_esperado}, obtenido {hash_calculado}"
                        )
                    log(f"Integridad SHA-256 verificada con éxito para {ruta_destino.name}.", 99.5)

                # Reemplazo atómico final
                os.replace(ruta_parcial, ruta_destino)
                log(f"Descarga finalizada con éxito: {ruta_destino.name}", 100.0)
                return ruta_destino

            except urllib.error.HTTPError as err:
                if err.code == 416:  # Range Not Satisfiable
                    if sha256_esperado and ruta_parcial.exists():
                        hash_calc = calcular_sha256_archivo(ruta_parcial)
                        if hmac.compare_digest(hash_calc.lower(), sha256_esperado.lower()):
                            os.replace(ruta_parcial, ruta_destino)
                            log(f"Descarga ya completada previamente: {ruta_destino.name}", 100.0)
                            return ruta_destino
                    if ruta_parcial.exists():
                        try:
                            ruta_parcial.unlink()
                        except OSError:
                            pass
                    log(f"HTTP 416 (Rango no válido) en {ruta_destino.name}. Reiniciando desde offset 0...", 0.0)
                    continue

                # Errores 4xx permanentes de cliente no deben reintentarse (N11)
                if 400 <= err.code < 500 and err.code != 429:
                    raise

                es_ultimo_intento = (intento == max_reintentos - 1)
                if es_ultimo_intento:
                    raise
                espera = reintento_backoff * (2 ** intento)
                log(f"Error HTTP transitorio {err.code} en descarga. Reintentando en {espera:.1f}s...", 0.0)
                time.sleep(espera)
            except ValueError:
                # No reintentar fallos de hash o errores de validación
                raise
            except Exception as e:
                es_ultimo_intento = (intento == max_reintentos - 1)
                if es_ultimo_intento:
                    if not permitir_reanudacion and ruta_parcial.exists():
                        try:
                            ruta_parcial.unlink()
                        except OSError:
                            pass
                    raise
                espera = reintento_backoff * (2 ** intento)
                log(f"Interrupción transitoria en descarga ({e}). Reintentando en {espera:.1f}s (intento {intento + 1}/{max_reintentos})...", 0.0)
                time.sleep(espera)

        raise RuntimeError(f"Agotados los {max_reintentos} reintentos de descarga para {ruta_destino.name}.")

    @classmethod
    def extraer_archivo_seguro(cls, archivo_comprimido: Path, directorio_destino: Path) -> None:
        """Extrae un archivo comprimido (.zip o .tar/.tar.gz) aplicando protección contra Zip Slip."""
        directorio_destino.mkdir(parents=True, exist_ok=True)
        if archivo_comprimido.suffix == ".zip":
            extraer_zip_seguro(archivo_comprimido, directorio_destino)
        elif ".tar" in archivo_comprimido.name or archivo_comprimido.suffix in (".tgz", ".tar"):
            extraer_tar_seguro(archivo_comprimido, directorio_destino)
        else:
            raise ValueError(f"Formato de archivo comprimido no soportado: {archivo_comprimido.name}")


class MotorDescargasBunker:
    """Motor central unificado e instanciable para gestionar descargas de binarios, herramientas y modelos."""

    def __init__(
        self,
        gestor_cache: Optional[Any] = None,
        directorio_modelos: Optional[Path] = None,
        directorio_herramientas: Optional[Path] = None,
    ) -> None:
        from guarida_manager import DIRECTORIO_HERRAMIENTAS, DIRECTORIO_MODELOS
        from guarida_manager.cache import GestorCache

        self.cache = gestor_cache or GestorCache()
        self.directorio_modelos = directorio_modelos or DIRECTORIO_MODELOS
        self.directorio_herramientas = directorio_herramientas or DIRECTORIO_HERRAMIENTAS

    def descargar_binario_llama(
        self,
        perfil: Optional[Any] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> Path:
        from guarida_manager.downloader.binaries import GestorBinariosLlama
        if perfil is None:
            perfil = GestorBinariosLlama.resolver_perfil_sistema()
        return GestorBinariosLlama.descargar_y_desplegar(
            perfil=perfil,
            callback_progreso=callback_progreso,
            gestor_cache=self.cache,
        )

    def descargar_herramienta(
        self,
        herramienta_id: str,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> Path:
        from guarida_manager.downloader.tools import GestorHerramientasBunker
        return GestorHerramientasBunker.descargar_y_desplegar(
            herramienta_id=herramienta_id,
            callback_progreso=callback_progreso,
            gestor_cache=self.cache,
        )

    def descargar_modelo(
        self,
        modelo: Any,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> Path:
        from guarida_manager.downloader.models import DescargadorModelos
        descargador = DescargadorModelos(
            directorio_modelos=self.directorio_modelos,
            gestor_cache=self.cache,
        )
        return descargador.descargar_modelo(modelo=modelo, callback_progreso=callback_progreso)

    def descargar_cesta(
        self,
        cesta: Any,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> list[Path]:
        from guarida_manager.downloader.models import DescargadorModelos
        descargador = DescargadorModelos(
            directorio_modelos=self.directorio_modelos,
            gestor_cache=self.cache,
        )
        return descargador.descargar_cesta(cesta=cesta, callback_progreso=callback_progreso)
