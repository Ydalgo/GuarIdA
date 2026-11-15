"""Demostración interactiva y visual del flujo RAG y Árbol de Nodos AST en GuarIdA.

Muestra paso a paso:
1. Creación de un repositorio de prueba con código, documentación y archivos sensibles.
2. Escaneo con filtros de seguridad (descarte de .env, bases de datos y archivos grandes).
3. Descomposición sintáctica de código en Árbol de Nodos AST.
4. Fragmentación semántica de documentación y código genérico.
5. Codificación vectorial e indexación incremental en SQLite.
6. Recuperación híbrida RRF (Dense Cosine + Sparse Lexical AST).
7. Ensamblado del prompt final con citas verificables de fuentes.
"""

from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.arbol_nodos import TipoNodoAST
from guarida_manager.cache import GestorCache
from guarida_manager.proyectos import GestorProyectos


def preparar_repositorio_demostracion(directorio_base: Path) -> Path:
    """Genera la estructura de un repositorio representativo para la demostración."""
    directorio_base.mkdir(parents=True, exist_ok=True)

    # 1. Código Python (para Árbol AST)
    codigo_py = (
        '"""Módulo de autenticación y seguridad criptográfica."""\n'
        'import hashlib\n'
        'import hmac\n\n'
        'def calcular_hash_sha256(secreto: str, salt: str) -> str:\n'
        '    """Genera un hash seguro combinando secreto y salt."""\n'
        '    return hashlib.sha256(f"{secreto}:{salt}".encode("utf-8")).hexdigest()\n\n'
        'class GestorTokens:\n'
        '    """Administra la emisión y validación de tokens de sesión."""\n'
        '    def __init__(self, clave_maestra: str):\n'
        '        self.clave_maestra = clave_maestra\n\n'
        '    def validar_token(self, token_recibido: str, token_esperado: str) -> bool:\n'
        '        """Verifica el token recibido usando comparación en tiempo constante."""\n'
        '        return hmac.compare_digest(token_recibido, token_esperado)\n'
    )
    (directorio_base / "autenticacion.py").write_text(codigo_py, encoding="utf-8")

    # 2. Documentación Markdown (para fragmentación por tokens y cabeceras)
    doc_md = (
        "# Arquitectura de Seguridad del Sistema\n\n"
        "Este documento describe el flujo de validación criptográfica y autenticación.\n\n"
        "## Mecanismo de Sesiones\n\n"
        "Cada sesión de usuario requiere un token generado mediante `calcular_hash_sha256`.\n"
        "El gestor `GestorTokens` comprueba los tokens mediante `hmac.compare_digest` para\n"
        "prevenir ataques de temporización (timing attacks).\n\n"
        "## Políticas de Acceso\n\n"
        "El entorno opera en modo fail-closed y solo permite llamadas locales a través de 127.0.0.1.\n"
    )
    (directorio_base / "ARQUITECTURA.md").write_text(doc_md, encoding="utf-8")

    # 3. Código genérico TypeScript (para fragmentación por definiciones)
    codigo_ts = (
        "export interface UsuarioSesion {\n"
        "    id: string;\n"
        "    nombre: string;\n"
        "}\n\n"
        "export function verificarAccesoLocal(ipOrigen: string): boolean {\n"
        "    return ipOrigen === '127.0.0.1' || ipOrigen === 'localhost';\n"
        "}\n"
    )
    (directorio_base / "cliente.ts").write_text(codigo_ts, encoding="utf-8")

    # 4. Archivos que DEBEN ser omitidos por seguridad
    (directorio_base / ".env").write_text("JWT_SECRET=super_secreto_privado\nAPI_KEY=12345", encoding="utf-8")
    (directorio_base / "usuarios.db").write_text("SQLite format 3\x00...", encoding="utf-8")

    return directorio_base


def ejecutar_demostracion_completa(
    ruta_demo: Optional[Path] = None,
    gestor_cache: Optional[GestorCache] = None,
    funcion_embedding: Optional[Callable[[str], list[float]]] = None,
    print_func: Callable[..., Any] = print,
) -> dict[str, Any]:
    """Ejecuta y explica visualmente todo el proceso de RAG e indexación AST."""
    ruta_base = ruta_demo or Path("repositorio_demo")
    preparar_repositorio_demostracion(ruta_base)

    if gestor_cache is None:
        db_demo = ruta_base / ".guarida_demo.db"
        cache = GestorCache(ruta_base_datos=db_demo)
    else:
        cache = gestor_cache

    gestor_proy = GestorProyectos(gestor_cache=cache)

    print_func("\n" + "=" * 90)
    print_func("     DEMOSTRACIÓN DIDÁCTICA: INDEXACIÓN, CODIFICACIÓN Y RECUPERACIÓN RAG EN GUARIDA")
    print_func("=" * 90)

    # PASO 1: Estructura del repositorio y seguridad
    print_func("\n[PASO 1] ESTRUCTURA DEL REPOSITORIO Y FILTROS DE SEGURIDAD")
    print_func("-" * 90)
    print_func(f"Directorio de trabajo: {ruta_base.resolve()}")
    archivos_presentes = list(ruta_base.iterdir())
    for a in archivos_presentes:
        print_func(f"  * {a.name:<20} ({a.stat().st_size} bytes)")
    print_func("\n  -> Filtro de seguridad activo: '.env' y 'usuarios.db' serán descartados automáticamente")
    print_func("     para impedir que secretos o volcados binarios lleguen al contexto del modelo.")

    # Registro del proyecto
    proy_id = "demo_rag"
    gestor_proy.eliminar_proyecto(proy_id)
    reg_proy = gestor_proy.crear_proyecto(
        nombre="Repositorio Demostrativo RAG",
        ruta_directorio=ruta_base,
        descripcion="Proyecto de demostración de árbol AST y RAG local",
        proyecto_id=proy_id,
    )

    # Embedding determinista si no se provee uno real
    def _emb_simulado(txt: str) -> list[float]:
        # Vector simulado de 8 dimensiones para demostración
        tokens = [t.lower() for t in txt.split() if len(t) > 2]
        h = sum(hash(t) for t in tokens) % 1000
        return [float((h + i * 17) % 10) / 10.0 for i in range(8)]

    fn_emb = funcion_embedding or _emb_simulado
    es_real = funcion_embedding is not None

    # PASO 2 y 3: Indexación y descomposición
    print_func("\n[PASO 2] DESCOMPOSICIÓN EN ÁRBOL DE NODOS AST Y FRAGMENTACIÓN")
    print_func("-" * 90)
    res_idx = gestor_proy.escanear_e_indexar_proyecto(
        proyecto_id=proy_id,
        funcion_embedding=fn_emb,
        modelo_emb_id="demo-emb-v1",
    )
    print_func(f"Archivos procesados:       {res_idx['archivos_procesados']}")
    print_func(f"Archivos omitidos (seg.):  {res_idx['omitidos_seguridad']} (¡.env y usuarios.db descartados con éxito!)")
    print_func(f"Nodos AST detectados:      {res_idx['nodos_ast']}")
    print_func(f"Fragmentos de texto/código:{res_idx['chunks_texto']}")
    print_func(f"Embeddings calculados:     {res_idx['embeddings_calculados']} (Motor: {'llama-server real' if es_real else 'simulado didáctico'})")

    # Inspección de los nodos del AST
    arbol = gestor_proy._arboles_codigo.get(proy_id)
    if arbol:
        print_func("\n  --- DETALLE DE NODOS DEL ÁRBOL SINTÁCTICO (autenticacion.py) ---")
        for n in arbol.nodos.values():
            if n.tipo != TipoNodoAST.MODULO:
                simb_muestra = ", ".join(list(n.simbolos)[:5])
                print_func(f"  [{n.tipo.value.upper():<7}] {n.nombre:<22} Líneas {n.linea_inicio}-{n.linea_fin} | Símbolos AST: [{simb_muestra}]")

    # Inspección de los fragmentos de documentación y TypeScript
    chunks = gestor_proy._chunks_texto.get(proy_id, [])
    if chunks:
        print_func("\n  --- DETALLE DE FRAGMENTOS DOCUMENTALES / CÓDIGO GENÉRICO ---")
        for ch in chunks:
            print_func(f"  [FRAGMENTO] {ch.ruta_archivo:<18} Sección: {ch.seccion:<30} Líneas {ch.linea_inicio}-{ch.linea_fin}")

    # PASO 4: Recuperación Híbrida RRF
    consulta_prueba = "¿Cómo valida los tokens el GestorTokens para evitar ataques de temporización?"
    print_func("\n[PASO 3] RECUPERACIÓN HÍBRIDA RRF ANTE UNA CONSULTA")
    print_func("-" * 90)
    print_func(f"Consulta de usuario: \"{consulta_prueba}\"")

    ctx_recuperado, fuentes = gestor_proy.buscar_contexto_hibrido(
        proyecto_id=proy_id,
        consulta=consulta_prueba,
        top_k=2,
        funcion_embedding=fn_emb,
    )

    print_func(f"\nFuentes recuperadas y clasificadas mediante RRF ({len(fuentes)} mejores):")
    for idx_f, f in enumerate(fuentes, 1):
        nom = f.get("nombre") or f.get("seccion", "")
        print_func(f"  {idx_f}. [{f['tipo'].upper()}] {f['archivo']}:{f['lineas']} ({nom}) -> Score RRF: {f['relevancia']:.4f}")

    # PASO 5: Contexto Inyectado
    print_func("\n[PASO 4] CONTEXTO FINAL INYECTADO AL MODELO (SIN POLUCIÓN DE ARCHIVOS COMPLETOS)")
    print_func("-" * 90)
    print_func(ctx_recuperado)
    print_func("-" * 90)
    print_func("¡Listo! El modelo generativo recibe solo las partes pertinentes con sus firmas y líneas.")
    print_func("=" * 90)

    return {
        "proyecto_id": proy_id,
        "archivos": res_idx["archivos_procesados"],
        "nodos_ast": res_idx["nodos_ast"],
        "fuentes_recuperadas": len(fuentes),
    }


if __name__ == "__main__":
    ejecutar_demostracion_completa()
