import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path
ruta_raiz = Path(__file__).resolve().parent
if str(ruta_raiz) not in sys.path:
    sys.path.insert(0, str(ruta_raiz))

from guarida_manager.menu import iniciar_menu

if __name__ == "__main__":
    iniciar_menu()
