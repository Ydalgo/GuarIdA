import argparse
import sys
from pathlib import Path

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.menu_actions import obtener_modelos_locales
from guarida_manager.tuning.buscador import BuscadorAfinamientoEtapas
from guarida_manager.tuning.capacidades import DescubridorCapacidades
from guarida_manager.tuning.informes import GeneradorInformesTuning
from guarida_manager.tuning.perfiles import GestorPerfilesTuning


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI de afinamiento empírico y benchmarking de GuarIdA.")
    parser.add_argument("--modelo", type=str, default=None, help="ID del modelo o ruta al archivo .gguf")
    parser.add_argument("--listar", action="store_true", help="Listar modelos disponibles descargados localmente")
    parser.add_argument("--perfil", type=str, default="estandar", choices=["rapido", "estandar", "exhaustivo"])
    parser.add_argument("--objetivo", type=str, default="equilibrado", choices=["chat", "batch", "agente_contexto_largo", "equilibrado"])
    parser.add_argument("--binario", type=str, default=None, help="Ruta opcional al ejecutable de llama-server")

    args = parser.parse_args()
    cache = GestorCache()

    locales = obtener_modelos_locales(cache)

    if args.listar or not args.modelo:
        print("\nModelos locales disponibles para afinar:")
        if not locales:
            print("  [!] No hay modelos descargados en el disco actualmente.")
        else:
            for idx, m in enumerate(locales, start=1):
                print(f"  [{idx}] ID: {m['id']} -> {m['filename']} ({m['ruta_local']})")
        if not args.modelo:
            print("\nUso: python -m guarida_manager.tuning --modelo <ID_O_ARCHIVO> [--perfil estandar] [--objetivo chat]")
            sys.exit(0 if args.listar else 1)

    # Resolver modelo
    ruta_modelo = Path(args.modelo)
    modelo_id = args.modelo
    if not ruta_modelo.exists():
        encontrado = next((m for m in locales if m["id"] == args.modelo or args.modelo in m["filename"]), None)
        if encontrado:
            ruta_modelo = Path(encontrado["ruta_local"])
            modelo_id = encontrado["id"]
        else:
            print(f"[!] Error: no se encontró el modelo '{args.modelo}'.")
            print("Modelos disponibles:")
            for m in locales:
                print(f"  - {m['id']} ({m['filename']})")
            sys.exit(1)

    # Resolver binario
    binario_path = Path(args.binario) if args.binario else GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    if not binario_path or not binario_path.exists():
        print("[!] Error: no se encontró el binario de llama-server.")
        sys.exit(1)

    print(f">> Descubriendo capacidades de {binario_path}...")
    caps = DescubridorCapacidades.descubrir(binario_path, gestor_cache=cache)

    perfil_barrido = GestorPerfilesTuning.obtener_perfil_barrido(args.perfil)
    perfil_barrido.objetivo_scoring = args.objetivo
    perfil_bateria = GestorPerfilesTuning.obtener_perfil_bateria(args.perfil)

    print(f">> Iniciando afinamiento para '{modelo_id}' con perfil '{args.perfil}' (Objetivo: {args.objetivo})...")

    def _progreso(msg: str, pct: float) -> None:
        print(f"[{pct*100:5.1f}%] {msg}")

    buscador = BuscadorAfinamientoEtapas(
        modelo_path=ruta_modelo,
        modelo_id=modelo_id,
        capacidades=caps,
        perfil_barrido=perfil_barrido,
        perfil_bateria=perfil_bateria,
        gestor_cache=cache,
        callback_progreso=_progreso,
    )

    ganador = buscador.ejecutar_barrido_completo()
    if ganador and ganador.estado == "ok":
        print("\n[OK] ¡Afinamiento completado con éxito!")
        print(f"Mejor configuración guardada en SQLite para el modelo '{modelo_id}'.")
    else:
        print("\n[!] El barrido finalizó sin encontrar una configuración estable.")


if __name__ == "__main__":
    main()
