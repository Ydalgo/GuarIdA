import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from guarida_manager.downloader.crypto import BovedaCriptograficaPostcuantica, SobreCriptografico


@dataclass
class ConfiguracionBunker:
    region: str
    interfaz_preferida: str                   # "terminal", "web", "escritorio"
    soporte_informes_pdf: bool
    roles: dict[str, str]                     # Mapeo de roles a modelos
    modelos_instalados: list[str]             # Todos los modelos descargados en lote
    herramientas_instaladas: list[str]        # Herramientas listas (llama-server, git, ripgrep)
    binario_inferencia_instalado: bool
    cifrado_postcuantico_activo: bool
    estado_bunker: str                        # "PENDIENTE_APROVISIONAMIENTO", "OFFLINE_COMPLETO"
    fecha_aprovisionamiento: Optional[str] = None


def escribir_archivo_atomico(ruta_destino: Path, contenido: str, encoding: str = "utf-8") -> None:
    """Escribe contenido de manera atómica usando un archivo temporal y os.replace con permisos 0o600."""
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    directorio = ruta_destino.parent
    ruta_temp = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=directorio, delete=False, encoding=encoding) as f_temp:
            f_temp.write(contenido)
            f_temp.flush()
            os.fsync(f_temp.fileno())
            ruta_temp = Path(f_temp.name)

        try:
            os.chmod(ruta_temp, 0o600)
        except OSError:
            pass

        os.replace(ruta_temp, ruta_destino)
        ruta_temp = None
    finally:
        if ruta_temp and ruta_temp.exists():
            try:
                ruta_temp.unlink()
            except OSError:
                pass


def guardar_configuracion_bunker(
    configuracion: ConfiguracionBunker,
    ruta_config: Path,
    clave_maestra_boveda: Optional[str] = None,
) -> Path:
    """Guarda la configuración del búnker, cifrándola si se proporciona una clave maestra."""
    datos_dict = asdict(configuracion)
    datos_json = json.dumps(datos_dict, indent=2, ensure_ascii=False)
    ruta_cifrada = ruta_config.with_suffix(".pqc.json")

    if clave_maestra_boveda:
        sobre = BovedaCriptograficaPostcuantica.cifrar_datos(datos_json, clave_maestra_boveda)
        payload_cifrado = json.dumps(
            {
                "version": sobre.version,
                "algoritmo": sobre.algoritmo,
                "salt_hex": sobre.salt_hex,
                "nonce_hex": sobre.nonce_hex,
                "datos_cifrados_b64": sobre.datos_cifrados_b64,
                "mac_autenticacion_hex": sobre.mac_autenticacion_hex,
            },
            indent=2,
        )
        escribir_archivo_atomico(ruta_cifrada, payload_cifrado)

        # Prevenir persistencia en claro (S2)
        if ruta_config.exists():
            ruta_config.unlink()
        return ruta_cifrada
    else:
        escribir_archivo_atomico(ruta_config, datos_json)
        # Limpiar configuración cifrada obsoleta al pasar a claro (B6)
        if ruta_cifrada.exists():
            ruta_cifrada.unlink()
        return ruta_config


def cargar_configuracion_bunker(
    ruta_config: Path,
    clave_maestra_boveda: Optional[str] = None,
) -> ConfiguracionBunker:
    """Carga y opcionalmente descifra la configuración del búnker."""
    ruta_cifrada = ruta_config.with_suffix(".pqc.json")

    if ruta_cifrada.exists():
        if not clave_maestra_boveda:
            raise PermissionError("La configuración está cifrada y requiere la clave maestra de la bóveda.")
        with open(ruta_cifrada, "r", encoding="utf-8") as f:
            datos_raw = json.load(f)

        sobre = SobreCriptografico(
            version=datos_raw["version"],
            algoritmo=datos_raw["algoritmo"],
            salt_hex=datos_raw["salt_hex"],
            nonce_hex=datos_raw["nonce_hex"],
            datos_cifrados_b64=datos_raw["datos_cifrados_b64"],
            mac_autenticacion_hex=datos_raw["mac_autenticacion_hex"],
        )
        datos_json = BovedaCriptograficaPostcuantica.descifrar_datos(sobre, clave_maestra_boveda)
        dict_config = json.loads(datos_json)
        return ConfiguracionBunker(**dict_config)

    if ruta_config.exists():
        with open(ruta_config, "r", encoding="utf-8") as f:
            dict_config = json.load(f)
        return ConfiguracionBunker(**dict_config)

    raise FileNotFoundError(f"No se encontró archivo de configuración en {ruta_config} ni {ruta_cifrada}")
