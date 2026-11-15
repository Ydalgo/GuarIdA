import shutil
import tempfile
import unittest
from pathlib import Path

from guarida_manager.cache import GestorCache
from guarida_manager.proyectos import (
    GestorProyectos,
    extraer_contenido_archivo,
    extraer_texto_docx,
    extraer_texto_odt,
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


class TestProyectosCorrecciones(TestProyectosNotebookLM):
    """Cubre las correcciones de auditoría: seguridad, incrementalidad, RRF, chunking y RAG en el chat."""

    @staticmethod
    def _emb(txt: str) -> list[float]:
        v = float(len(txt) % 7 + 1)
        return [v, 0.5, 0.1, 0.9]

    def test_escaneo_omite_archivos_sensibles_y_grandes(self):
        (self.dir_proyecto / ".env").write_text("TOKEN=secreto", encoding="utf-8")
        (self.dir_proyecto / "clave.pem").write_text("-----BEGIN-----", encoding="utf-8")
        (self.dir_proyecto / "config.json").write_text('{"ok": 1}', encoding="utf-8")
        (self.dir_proyecto / "enorme.txt").write_text("x" * 1_100_000, encoding="utf-8")
        proy = self.gestor.crear_proyecto("Seg", self.dir_proyecto)
        res = self.gestor.escanear_e_indexar_proyecto(proy.id)
        rutas = {d["ruta_relativa"] for d in self.cache.listar_documentos_proyecto(proy.id)}
        self.assertNotIn(".env", rutas)
        self.assertNotIn("clave.pem", rutas)
        self.assertNotIn("enorme.txt", rutas)
        self.assertIn("config.json", rutas)
        self.assertGreaterEqual(res["omitidos_seguridad"], 2)

    def test_indexacion_incremental_reutiliza_embeddings(self):
        llamadas = []

        def emb(txt: str) -> list[float]:
            llamadas.append(txt)
            return self._emb(txt)

        proy = self.gestor.crear_proyecto("Inc", self.dir_proyecto)
        r1 = self.gestor.escanear_e_indexar_proyecto(proy.id, funcion_embedding=emb, modelo_emb_id="m1")
        n1 = len(llamadas)
        self.assertGreater(r1["embeddings_calculados"], 0)

        gestor2 = GestorProyectos(gestor_cache=self.cache)
        r2 = gestor2.escanear_e_indexar_proyecto(proy.id, funcion_embedding=emb, modelo_emb_id="m1")
        self.assertEqual(len(llamadas), n1)
        self.assertEqual(r2["embeddings_calculados"], 0)
        self.assertEqual(r2["embeddings_reutilizados"], r1["embeddings_calculados"])
        self.assertEqual(r2["archivos_sin_cambios"], r2["archivos_procesados"])

        # Otro modelo de embeddings no debe reutilizar vectores ajenos
        r3 = gestor2.escanear_e_indexar_proyecto(proy.id, funcion_embedding=emb, modelo_emb_id="m2")
        self.assertGreater(r3["embeddings_calculados"], 0)

    def test_snapshot_cache_carga_instantanea_y_reutilizacion(self):
        proy = self.gestor.crear_proyecto("SnapTest", self.dir_proyecto)
        # Primera indexación (construye snapshot)
        r1 = self.gestor.escanear_e_indexar_proyecto(proy.id, modelo_emb_id="emb_snap")
        self.assertFalse(r1.get("snapshot_reutilizado", False))

        # Segunda indexación sin cambios: debe cargar snapshot instantáneamente
        gestor2 = GestorProyectos(gestor_cache=self.cache)
        r2 = gestor2.escanear_e_indexar_proyecto(proy.id, modelo_emb_id="emb_snap")
        self.assertTrue(r2.get("snapshot_reutilizado", False))
        self.assertEqual(r2["embeddings_calculados"], 0)
        self.assertEqual(len(gestor2._chunks_texto[proy.id]), len(self.gestor._chunks_texto[proy.id]))

        # Modificación de archivo: invalida el snapshot y vuelve a procesar
        (self.dir_proyecto / "README.md").write_text("# Modificado\nTexto nuevo", encoding="utf-8")
        gestor3 = GestorProyectos(gestor_cache=self.cache)
        r3 = gestor3.escanear_e_indexar_proyecto(proy.id, modelo_emb_id="emb_snap")
        self.assertFalse(r3.get("snapshot_reutilizado", False))

    def test_optimizacion_git_hash_o1_sin_escaneo_archivos(self):
        from unittest.mock import patch
        proy = self.gestor.crear_proyecto("GitTest", self.dir_proyecto)

        with patch("guarida_manager.proyectos._obtener_hash_git_limpio", return_value="abc1234567890def"):
            r1 = self.gestor.escanear_e_indexar_proyecto(proy.id, modelo_emb_id="emb_git")
            self.assertFalse(r1.get("snapshot_reutilizado", False))

        # En la segunda pasada con mismo commit hash, no debe invocarse os.walk
        gestor2 = GestorProyectos(gestor_cache=self.cache)
        with patch("guarida_manager.proyectos._obtener_hash_git_limpio", return_value="abc1234567890def"), \
             patch("os.walk", side_effect=AssertionError("os.walk no debe ejecutarse en modo Git O(1)")):
            r2 = gestor2.escanear_e_indexar_proyecto(proy.id, modelo_emb_id="emb_git")
            self.assertTrue(r2.get("snapshot_reutilizado", False))
            self.assertEqual(r2.get("modo_verificacion"), "git_o1")
            self.assertEqual(len(gestor2._chunks_texto[proy.id]), len(self.gestor._chunks_texto[proy.id]))

    def test_busqueda_solo_lexica_sin_embeddings(self):
        proy = self.gestor.crear_proyecto("Lex", self.dir_proyecto)
        self.gestor.escanear_e_indexar_proyecto(proy.id)
        ctx, fuentes = self.gestor.buscar_contexto_hibrido(proy.id, "calcular hash sha256", top_k=2)
        self.assertTrue(fuentes)
        self.assertIn("calcular_hash_sha256", ctx)
        self.assertTrue(all(0.0 < f["relevancia"] <= 1.0 for f in fuentes))

    def test_chunking_por_tokens(self):
        texto = "# Titulo\n" + "\n".join(f"linea numero {i} con bastante texto de relleno para tokens" for i in range(120))
        chunks = fragmentar_documento_texto("doc.md", texto, max_tokens_chunk=100)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c.texto) // 4 < 400 for c in chunks))

    def test_codigo_generico_se_fragmenta_por_definiciones(self):
        js = (
            "function sumar(a, b) {\n  return a + b;\n}\n\n"
            "class Calculadora {\n  mult(a, b) { return a * b; }\n}\n"
        )
        (self.dir_proyecto / "calc.js").write_text(js, encoding="utf-8")
        proy = self.gestor.crear_proyecto("JS", self.dir_proyecto)
        self.gestor.escanear_e_indexar_proyecto(proy.id)
        ctx, fuentes = self.gestor.buscar_contexto_hibrido(proy.id, "sumar", top_k=3)
        self.assertTrue(any(f["archivo"] == "calc.js" for f in fuentes))
        docs = {d["ruta_relativa"]: d for d in self.cache.listar_documentos_proyecto(proy.id)}
        self.assertEqual(docs["calc.js"]["tipo_documento"], "codigo_generico")
        self.assertGreaterEqual(docs["calc.js"]["nodos_ast_count"], 2)

    def test_chat_inyecta_contexto_rag_sin_inflar_historial(self):
        from unittest.mock import MagicMock, patch

        from guarida_manager.chat import ejecutar_chat_terminal

        proy = self.gestor.crear_proyecto("RAG", self.dir_proyecto)
        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True
        mock_cli.tokenizar.return_value = [1, 2, 3]
        mock_cli.completar_chat.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            "timings": {},
        }
        mock_emb_cli = MagicMock()
        mock_emb_cli.calcular_embedding.side_effect = self._emb
        mock_emb_srv = MagicMock()

        entradas = iter(["calcular hash sha256", "segunda pregunta", "/quit"])
        with patch(
            "guarida_manager.chat.iniciar_servidor_embeddings", return_value=(mock_emb_srv, mock_emb_cli)
        ):
            ejecutar_chat_terminal(
                gestor_cache=self.cache,
                gestor_server=mock_srv,
                cliente=mock_cli,
                modelo_seleccionado="qwen2.5-3b-chat-q4",
                proyecto_id=proy.id,
                input_func=lambda _: next(entradas),
                print_func=lambda *a, **k: None,
            )

        self.assertGreater(mock_emb_cli.calcular_embedding.call_count, 0)
        llamadas = mock_cli.completar_chat.call_args_list
        self.assertEqual(len(llamadas), 2)
        primer_envio = llamadas[0].kwargs["mensajes"][-1]["content"]
        self.assertIn("Contexto del Repositorio", primer_envio)
        self.assertIn("calcular_hash_sha256", primer_envio)
        # Segundo turno: el historial enviado conserva el primer mensaje limpio (sin contexto)
        previos = [m["content"] for m in llamadas[1].kwargs["mensajes"][:-1] if m["role"] == "user"]
        self.assertEqual(previos, ["calcular hash sha256"])
        mock_emb_srv.detener_servidor.assert_called()

    def test_menu_proyectos_crear_y_listar(self):
        from guarida_manager.menu_proyectos import opcion_proyectos

        salidas: list[str] = []
        entradas = iter(["1", "Mi Repo", str(self.dir_proyecto), "desc", "2", "0"])
        opcion_proyectos(self.cache, input_func=lambda _: next(entradas), print_func=salidas.append)
        self.assertEqual(len(self.gestor.listar_proyectos()), 1)
        self.assertIn("Mi Repo", "\n".join(salidas))

    def test_embedding_persistente_roundtrip(self):
        self.cache.guardar_embedding("k1", "m", [0.25, -1.5, 3.0])
        self.assertEqual(self.cache.obtener_embedding("k1"), [0.25, -1.5, 3.0])
        self.assertIsNone(self.cache.obtener_embedding("no-existe"))

    def test_ejecutar_demostracion_completa(self):
        from guarida_manager.demo_rag import ejecutar_demostracion_completa
        salidas: list[str] = []
        dir_demo = Path(self.temp_dir) / "sub_demo"
        res = ejecutar_demostracion_completa(
            ruta_demo=dir_demo,
            gestor_cache=self.cache,
            print_func=salidas.append,
        )
        self.assertEqual(res["archivos"], 3)
        self.assertGreaterEqual(res["nodos_ast"], 3)
        self.assertEqual(res["fuentes_recuperadas"], 2)
        txt = "\n".join(salidas)
        self.assertIn("DEMOSTRACIÓN DIDÁCTICA", txt)
        self.assertIn("GestorTokens", txt)
        self.assertIn("autenticacion.py", txt)


    def test_extraccion_docx_y_odt(self):
        import zipfile

        # Crear archivo .docx de prueba
        ruta_docx = Path(self.temp_dir) / "manual.docx"
        doc_xml = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body>'
            b'<w:p><w:r><w:t>Procedimiento de Expedicion TIE</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Requisitos y tasas aplicables.</w:t></w:r></w:p>'
            b'</w:body></w:document>'
        )
        with zipfile.ZipFile(ruta_docx, "w") as z:
            z.writestr("word/document.xml", doc_xml)

        txt_docx = extraer_texto_docx(ruta_docx)
        self.assertIn("Procedimiento de Expedicion TIE", txt_docx)
        self.assertIn("Requisitos y tasas aplicables.", txt_docx)

        # Crear archivo .odt de prueba
        ruta_odt = Path(self.temp_dir) / "guia.odt"
        odt_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            b'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            b'<office:body><office:text>'
            b'<text:h>Instrucciones de Huella</text:h>'
            b'<text:p>Cita previa obligatoria en extranjeria.</text:p>'
            b'</office:text></office:body></office:document-content>'
        )
        with zipfile.ZipFile(ruta_odt, "w") as z:
            z.writestr("content.xml", odt_xml)

        txt_odt = extraer_texto_odt(ruta_odt)
        self.assertIn("Instrucciones de Huella", txt_odt)
        self.assertIn("Cita previa obligatoria en extranjeria.", txt_odt)

    def test_indexacion_documentos_ofimaticos(self):
        import zipfile

        ruta_docx = self.dir_proyecto / "normativa.docx"
        doc_xml = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body>'
            b'<w:p><w:r><w:t>Manual Oficial TIE 2026</w:t></w:r></w:p>'
            b'</w:body></w:document>'
        )
        with zipfile.ZipFile(ruta_docx, "w") as z:
            z.writestr("word/document.xml", doc_xml)

        proy = self.gestor.crear_proyecto(nombre="Proy Ofimatica", ruta_directorio=self.dir_proyecto)
        res = self.gestor.escanear_e_indexar_proyecto(proy.id)
        docs = self.cache.listar_documentos_proyecto(proy.id)
        nombres = [d["ruta_relativa"] for d in docs]
        self.assertIn("normativa.docx", nombres)
        doc_normativa = next(d for d in docs if d["ruta_relativa"] == "normativa.docx")
        self.assertEqual(doc_normativa["tipo_documento"], "documento_ofimatico")


if __name__ == "__main__":
    unittest.main()
