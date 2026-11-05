import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Optional

from guarida_manager import DIRECTORIO_LOGS, RUTA_LOG_PREDETERMINADA

_LOGGER_INICIALIZADO = False


def inicializar_logging(
    ruta_log: Optional[Path] = None,
    nivel: int = logging.INFO,
    capturar_excepciones_globales: bool = True,
    forzar_reconfiguracion: bool = False,
) -> logging.Logger:
    """Configura el sistema centralizado de logging de GuarIdA en archivo y captura excepciones no controladas."""
    global _LOGGER_INICIALIZADO

    archivo_log = ruta_log or RUTA_LOG_PREDETERMINADA
    try:
        archivo_log.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    logger = logging.getLogger("guarida")
    logger.setLevel(nivel)

    if not _LOGGER_INICIALIZADO or forzar_reconfiguracion:
        if forzar_reconfiguracion:
            logger.handlers.clear()
        try:
            handler = logging.handlers.RotatingFileHandler(
                filename=str(archivo_log),
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
                errors="replace",
            )
            formato = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s:%(filename)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formato)
            handler.setLevel(nivel)
            logger.addHandler(handler)
        except Exception:
            pass

        if capturar_excepciones_globales:
            def _excepthook_personalizado(exc_type, exc_value, exc_traceback):
                if issubclass(exc_type, KeyboardInterrupt):
                    sys.__excepthook__(exc_type, exc_value, exc_traceback)
                    return

                msg_error = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                logger.critical(f"EXCEPCIÓN NO CONTROLADA:\n{msg_error}")
                print("\n" + "!" * 75)
                print(f"[ERROR CRÍTICO]: Se produjo un error no controlado en el sistema.")
                print(f"Detalle: {exc_value}")
                print(f"El informe detallado del fallo se ha registrado en:\n  {archivo_log}")
                print("!" * 75)
                try:
                    input("\nPresiona [Enter] para continuar...")
                except Exception:
                    pass

            sys.excepthook = _excepthook_personalizado

        _LOGGER_INICIALIZADO = True

    return logger


def obtener_logger(nombre: str = "guarida") -> logging.Logger:
    """Devuelve un logger configurado bajo el espacio de nombres de GuarIdA."""
    if not _LOGGER_INICIALIZADO:
        inicializar_logging()
    return logging.getLogger(f"guarida.{nombre}")


def obtener_ultimas_lineas_log(n_lineas: int = 50, ruta_log: Optional[Path] = None) -> list[str]:
    """Lee y devuelve las últimas N líneas del archivo de log del sistema."""
    archivo = ruta_log or RUTA_LOG_PREDETERMINADA
    try:
        if not archivo.exists():
            return [f"El archivo de log no existe aún ({archivo})."]
        with open(archivo, "r", encoding="utf-8", errors="replace") as f:
            lineas = f.readlines()
            return lineas[-n_lineas:] if len(lineas) > n_lineas else lineas
    except Exception as e:
        return [f"Error al leer el archivo de log: {e}"]
