import shutil
import tempfile
import unittest
from pathlib import Path

from guarida_manager.cache import GestorCache
from guarida_manager.proyectos import (
    GestorProyectos,
    fragmentar_documento_texto,
)


class TestProyectosNotebookLM(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_proy.db"
        self.cache = GestorCache(ruta_base_datos=self.db_path)
        self.gestor = GestorProyectos(gestor_cache=self.cache)

        # Crear carpeta de proyecto de prueba con archivos
        self.dir_proyecto = Path(self.temp_dir) / "mi_repo"
        self.dir_proyecto.mkdir(parents=True)

        # Archivo Python
        codigo_py = (
            "def calcular_hash_sha256(texto: str) -> str:\n"
            "    '''Calcula el hash seguro SHA-256.'''\n"
            "    import hashlib\n"
            "    return hashlib.sha256(texto.encode('utf-8')).hexdigest()\n\n"
            "class GestorPrueba:\n"
            "    def __init__(self, nombre: str):\n"
            "        self.nombre = nombre\n\n"
            "    def ejecutar_accion(self):\n"
            "        return f'Accion ejecutada por {self.nombre}'\n"
        )
        (self.dir_proyecto / "modulo.py").write_text(codigo_py, encoding="utf-8")

        # Archivo Markdown
        doc_md = (
            "# Especificación del Sistema\n\n"
            "Este proyecto corre 100% offline sin telemetría.\n\n"
            "## Arquitectura de Seguridad\n\n"
            "Los permisos se gestionan a nivel de proceso en la Fase 4.\n"
        )
        (self.dir_proyecto / "README.md").write_text(doc_md, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_crear_y_listar_proyectos(self):
        proy = self.gestor.crear_proyecto(
            nombre="Repo GuarIdA Test",
            ruta_directorio=self.dir_proyecto,
            descripcion="Repositorio de pruebas offline",
        )
        self.assertEqual(proy.nombre, "Repo GuarIdA Test")

        lista = self.gestor.listar_proyectos()
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["id"], proy.id)

    def test_fragmentar_documento_texto(self):
        md = "# Titulo 1\nLinea A\nLinea B\n# Titulo 2\nLinea C\nLinea D"
        chunks = fragmentar_documento_texto("docs/info.md", md)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].seccion, "Titulo 1")
        self.assertEqual(chunks[1].seccion, "Titulo 2")

    def test_escanear_e_indexar_proyecto(self):
        proy = self.gestor.crear_proyecto(
            nombre="Repo Test",
            ruta_directorio=self.dir_proyecto,
        )

        def mock_embedding(txt: str) -> list[float]:
            # Genera un vector simulado determinista de 4 dimensiones
            v = float(len(txt) % 10)
            return [v, v * 0.5, 0.1, 0.9]

        resumen = self.gestor.escanear_e_indexar_proyecto(
            proyecto_id=proy.id,
            funcion_embedding=mock_embedding,
        )
        self.assertGreaterEqual(resumen["total_archivos"], 2)
        self.assertGreaterEqual(resumen["nodos_ast"], 2)
        self.assertGreaterEqual(resumen["chunks_texto"], 1)

        # Probar búsqueda híbrida sobre el repo
        ctx, fuentes = self.gestor.buscar_contexto_hibrido(
            proyecto_id=proy.id,
            consulta="calcular hash sha256",
            vector_consulta=mock_embedding("calcular hash sha256"),
            top_k=3,
        )
        self.assertTrue(len(fuentes) > 0)
        self.assertIn("calcular_hash_sha256", ctx)

    def test_sesion_chat_y_persistencia_mensajes(self):
        proy = self.gestor.crear_proyecto(
            nombre="Repo Chat",
            ruta_directorio=self.dir_proyecto,
        )
        sesion = self.gestor.crear_sesion(
            modelo_id="qwen2.5-coder-7b",
            titulo="Auditoría de Código",
            proyecto_id=proy.id,
        )
        self.assertEqual(sesion.modelo_id, "qwen2.5-coder-7b")

        id_m1 = self.gestor.registrar_mensaje(
            sesion_id=sesion.id,
            rol="user",
            contenido="¿Dónde se calcula el hash?",
            tokens_prompt=8,
        )
        self.assertGreater(id_m1, 0)

        id_m2 = self.gestor.registrar_mensaje(
            sesion_id=sesion.id,
            rol="assistant",
            contenido="En modulo.py línea 1.",
            fuentes=[{"archivo": "modulo.py", "lineas": "1-4"}],
            tokens_generados=12,
        )
        self.assertGreater(id_m2, 0)

        historial = self.gestor.obtener_historial_sesion(sesion.id)
        self.assertEqual(len(historial), 2)
        self.assertEqual(historial[0]["rol"], "user")
        self.assertEqual(historial[1]["rol"], "assistant")
        self.assertIn("modulo.py", historial[1]["fuentes_ast_json"])


if __name__ == "__main__":
    unittest.main()
