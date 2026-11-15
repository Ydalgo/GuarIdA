"""Submenú de Proyectos y Documentos: crear, indexar, listar, chatear y reanudar sesiones sobre un repositorio local."""

from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.cache import GestorCache
from guarida_manager.proyectos import GestorProyectos


def _elegir_proyecto(
    proyectos: list[dict[str, Any]],
    input_func: Callable[[str], str],
    print_func: Callable[..., Any],
) -> Optional[dict[str, Any]]:
    if not proyectos:
        print_func("\n[!] No hay proyectos. Crea uno primero con la opción [1].")
        return None
    for i, p in enumerate(proyectos, 1):
        print_func(f"  [{i}] {p['nombre']}  ({p['id']})  {p['ruta_directorio']}")
    sel = input_func("Número de proyecto (Enter = cancelar): ").strip()
    if not sel:
        return None
    if sel.isdigit() and 1 <= int(sel) <= len(proyectos):
        return proyectos[int(sel) - 1]
    for p in proyectos:
        if p["id"] == sel:
            return p
    print_func("[!] Selección no válida.")
    return None


def opcion_proyectos(
    gestor_cache: Optional[GestorCache] = None,
    lanzar_chat: Optional[Callable[[Optional[str], Optional[str]], None]] = None,
    input_func: Callable[[str], str] = input,
    print_func: Callable[..., Any] = print,
) -> None:
    """Bucle del submenú. `lanzar_chat(proyecto_id, sesion_id)` abre el chat con RAG sobre el proyecto."""
    cache = gestor_cache or GestorCache()
    gestor = GestorProyectos(gestor_cache=cache)

    while True:
        print_func("\n" + "=" * 75)
        print_func("  PROYECTOS Y DOCUMENTOS (chat con tu repositorio, 100% local)")
        print_func("=" * 75)
        print_func("  [1] Crear proyecto (carpeta de código/documentación)")
        print_func("  [2] Listar proyectos, documentos y sesiones")
        print_func("  [3] Chatear con un proyecto (nueva sesión)")
        print_func("  [4] Reanudar una sesión anterior")
        print_func("  [5] Eliminar proyecto (no borra archivos del disco)")
        print_func("  [0] Volver")
        try:
            op = input_func("Selecciona una opción [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        if op == "0":
            return

        if op == "1":
            nombre = input_func("Nombre del proyecto: ").strip()
            ruta = input_func("Ruta de la carpeta (repositorio o documentos): ").strip().strip('"')
            if not nombre or not ruta:
                print_func("[!] Nombre y ruta son obligatorios.")
                continue
            ruta_p = Path(ruta)
            if not ruta_p.is_dir():
                print_func(f"[!] La ruta no existe o no es una carpeta: {ruta}")
                continue
            desc = input_func("Descripción (opcional): ").strip()
            reg = gestor.crear_proyecto(nombre, ruta_p, desc)
            print_func(f"[OK] Proyecto '{reg.nombre}' creado con id {reg.id}. Se indexará al abrir el chat.")

        elif op == "2":
            proyectos = gestor.listar_proyectos()
            if not proyectos:
                print_func("\n[!] No hay proyectos registrados.")
            for p in proyectos:
                docs = cache.listar_documentos_proyecto(p["id"])
                sesiones = gestor.listar_sesiones(proyecto_id=p["id"])
                print_func(f"\n* {p['nombre']} ({p['id']}) - {p['ruta_directorio']}")
                print_func(f"    Documentos indexados: {len(docs)} | Sesiones: {len(sesiones)}")
                for s in sesiones[:5]:
                    print_func(f"    - sesión {s['id']}: {s['titulo']} (act. {s['fecha_actualizacion'][:19]})")

        elif op == "3":
            p = _elegir_proyecto(gestor.listar_proyectos(), input_func, print_func)
            if p and lanzar_chat:
                lanzar_chat(p["id"], None)

        elif op == "4":
            sesiones = gestor.listar_sesiones()
            if not sesiones:
                print_func("\n[!] No hay sesiones guardadas.")
                continue
            for i, s in enumerate(sesiones[:15], 1):
                print_func(f"  [{i}] {s['id']}  {s['titulo']}  (proyecto: {s['proyecto_id'] or '-'})")
            sel = input_func("Número de sesión (Enter = cancelar): ").strip()
            if sel.isdigit() and 1 <= int(sel) <= min(15, len(sesiones)):
                s = sesiones[int(sel) - 1]
                if lanzar_chat:
                    lanzar_chat(s["proyecto_id"], s["id"])

        elif op == "5":
            p = _elegir_proyecto(gestor.listar_proyectos(), input_func, print_func)
            if p:
                conf = input_func(f"¿Eliminar '{p['nombre']}' y su índice? (s/N): ").strip().lower()
                if conf in ("s", "si", "y", "yes"):
                    gestor.eliminar_proyecto(p["id"])
                    print_func("[OK] Proyecto eliminado.")

        else:
            print_func("[!] Opción no válida.")
