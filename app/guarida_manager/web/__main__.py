"""Punto de entrada CLI para lanzar la interfaz web autoalojada de GuarIdA."""

import argparse
from typing import Optional

from guarida_manager.web.server import iniciar_servidor_web


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Servidor web autoalojado de GuarIdA (interfaz estilo Antigravity IDE)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Interfaz local de escucha")
    parser.add_argument("--port", type=int, default=8080, help="Puerto TCP preferido")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="No abrir automáticamente el navegador al iniciar",
    )
    parser.add_argument(
        "--remoto",
        "--remote",
        action="store_true",
        help="Abrir túnel HTTPS público (cloudflared) con código de acceso",
    )
    args = parser.parse_args(argv)
    iniciar_servidor_web(
        host=args.host,
        port=args.port,
        abrir_navegador=not args.no_browser,
        remoto=args.remoto,
    )


if __name__ == "__main__":
    main()
