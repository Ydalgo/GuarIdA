import os
from pathlib import Path


def resolver_directorio_raiz_guarida() -> Path:
    """Resuelve la carpeta de datos de GuarIdA (env > modo portable > ~/.guarida)."""
    env_home = os.environ.get("GUARIDA_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser().resolve()

    raiz_app = Path(__file__).resolve().parent.parent
    raiz_proyecto = raiz_app.parent if raiz_app.name == "app" else raiz_app
    if (
        (raiz_proyecto / ".portable").exists()
        or (raiz_proyecto / "runtime").exists()
        or (raiz_proyecto / "datos").exists()
    ):
        return raiz_proyecto / "datos"

    return Path.home() / ".guarida"


DIRECTORIO_RAIZ_GUARIDA = resolver_directorio_raiz_guarida()
DIRECTORIO_BINARIOS = DIRECTORIO_RAIZ_GUARIDA / "bin"
DIRECTORIO_BINARIOS_CPU = DIRECTORIO_BINARIOS / "cpu"
DIRECTORIO_BINARIOS_GPU = DIRECTORIO_BINARIOS / "gpu"
DIRECTORIO_HERRAMIENTAS = DIRECTORIO_BINARIOS / "tools"
DIRECTORIO_MODELOS = DIRECTORIO_RAIZ_GUARIDA / "models"
DIRECTORIO_LOGS = DIRECTORIO_RAIZ_GUARIDA / "logs"
DIRECTORIO_TELEMETRIA_LOGS = DIRECTORIO_LOGS / "telemetria"
DIRECTORIO_CACHE_PROYECTOS = DIRECTORIO_RAIZ_GUARIDA / "cache_proyectos"
RUTA_LOG_PREDETERMINADA = DIRECTORIO_LOGS / "guarida.log"
RUTA_DB_CONFIG_PREDETERMINADA = DIRECTORIO_RAIZ_GUARIDA / "config.db"
RUTA_DB_SESIONES_PREDETERMINADA = DIRECTORIO_RAIZ_GUARIDA / "sesiones_chat.db"
RUTA_DB_PROYECTOS_PREDETERMINADA = DIRECTORIO_RAIZ_GUARIDA / "proyecto_grafo.db"
RUTA_BASE_DATOS_PREDETERMINADA = RUTA_DB_CONFIG_PREDETERMINADA
RUTA_CONFIG_PREDETERMINADA = DIRECTORIO_RAIZ_GUARIDA / "config.json"
