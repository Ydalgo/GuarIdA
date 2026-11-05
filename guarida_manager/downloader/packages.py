import importlib.util
import subprocess
import sys
from typing import ClassVar


class GestorPaquetesPython:
    """Gestor de dependencias opcionales de Python con fijación estricta de versiones."""

    PAQUETES_OPCIONALES: ClassVar[dict[str, str]] = {
        "pdf": "reportlab",
        "web": "fastapi",
        "escritorio": "PyQt6",
    }

    PAQUETES_PINNED: ClassVar[dict[str, list[str]]] = {
        "reportlab": ["reportlab==4.2.5", "pillow>=10.4.0", "chardet>=5.2.0"],
        "fastapi": [
            "fastapi==0.115.4",
            "starlette==0.41.2",
            "pydantic==2.9.2",
            "pydantic-core>=2.23.4",
            "annotated-types>=0.7.0",
            "typing-extensions>=4.12.2",
            "anyio>=4.6.2",
            "sniffio>=1.3.1",
            "idna>=3.10",
        ],
        "uvicorn": ["uvicorn==0.32.0", "click>=8.1.7", "h11>=0.14.0"],
        "PyQt6": ["PyQt6==6.7.1", "PyQt6-Qt6==6.7.3", "PyQt6-sip==13.8.0"],
    }

    @staticmethod
    def verificar_paquete(nombre_modulo: str) -> bool:
        """Verifica si un módulo Python está disponible en el entorno."""
        return importlib.util.find_spec(nombre_modulo) is not None

    @classmethod
    def instalar_paquete_pip(
        cls,
        nombre_paquete: str,
        permitir_pip_runtime: bool = True,
        timeout_segundos: int = 120,
    ) -> bool:
        """Instala dependencias mediante pip con versiones pineadas estrictas (S7, B4)."""
        if not permitir_pip_runtime:
            return False
        specs = cls.PAQUETES_PINNED.get(nombre_paquete)
        if not specs:
            raise ValueError(
                f"Paquete '{nombre_paquete}' no autorizado para instalación en runtime. "
                f"Solo paquetes de la lista blanca permitida están autorizados: {list(cls.PAQUETES_PINNED.keys())}"
            )
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--no-deps", *specs]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout_segundos)
            return True
        except Exception:
            return False
