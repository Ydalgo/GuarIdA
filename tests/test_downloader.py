import tempfile
import unittest
from pathlib import Path

from guarida_manager.cache import BenchmarkRegistro, GestorCache, ModeloRegistro
from guarida_manager.downloader.binaries import GestorBinariosLlama
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.models import (
    CatalogoModelos,
    CestaDescarga,
    DescargadorModelos,
)


class TestDownloader(unittest.TestCase):
    def test_catalogo_modelos_y_cumplimiento(self):
        modelos_eu = CatalogoModelos.listar_modelos(region=RegionNormativa.ES_EU)
        self.assertGreater(len(modelos_eu), 0)

        # Verificar que el modelo qwen2.5-coder-7b-q4 tiene estatus de cumplimiento
        qwen = CatalogoModelos.obtener_modelo("qwen2.5-coder-7b-q4")
        self.assertIsNotNone(qwen)
        self.assertEqual(qwen.categoria, "coder")

        # Verificar modelo de embeddings para bucles y árboles de nodos
        nomic = CatalogoModelos.obtener_modelo("nomic-embed-text-v1.5")
        self.assertIsNotNone(nomic)
        self.assertEqual(nomic.categoria, "embedding")

        # Verificar modelo conversacional para chat en español
        chat_m = CatalogoModelos.obtener_modelo("qwen2.5-3b-chat-q4")
        self.assertIsNotNone(chat_m)
        self.assertEqual(chat_m.categoria, "chat")

        # Verificar modelo sin censura
        uncensored_m = CatalogoModelos.obtener_modelo("qwen2.5-coder-7b-abliterated-q4")
        self.assertIsNotNone(uncensored_m)
        self.assertTrue(uncensored_m.es_sin_censura)

    def test_agregar_modelo_personalizado(self):
        custom = CatalogoModelos.agregar_modelo_personalizado(
            id_unico="custom-model-test",
            nombre_legible="Custom Model Test",
            repo_hf="user/test-repo",
            filename="test-model-q4.gguf",
            tamano_gb=3.5,
            categoria="coder",
        )
        self.assertEqual(custom.id, "custom-model-test")
        recuperado = CatalogoModelos.obtener_modelo("custom-model-test")
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado.repo_hf, "user/test-repo")

    def test_cesta_descarga(self):
        m1 = CatalogoModelos.obtener_modelo("qwen2.5-coder-1.5b-q4")
        m2 = CatalogoModelos.obtener_modelo("bge-m3-q4")
        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)

        cesta = CestaDescarga(modelos=[m1, m2])
        self.assertAlmostEqual(cesta.tamano_total_gb, m1.tamano_gb + m2.tamano_gb, places=2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            suficiente, libre = cesta.verificar_espacio_disco(Path(tmp_dir))
            self.assertIsInstance(suficiente, bool)
            self.assertGreater(libre, 0.0)

    def test_resolver_perfil_binario_llama(self):
        perfil = GestorBinariosLlama.resolver_perfil_sistema()
        self.assertIsNotNone(perfil.nombre_archivo)
        self.assertIn("llama-", perfil.nombre_archivo)
        self.assertTrue(perfil.url_descarga.startswith("https://github.com/"))

    def test_preservacion_historico_al_archivar_sin_archivo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test_guarida.db"
            models_dir = tmp_path / "models"
            models_dir.mkdir()

            fake_gguf = models_dir / "test_model.gguf"
            fake_gguf.write_text("dummy model content", encoding="utf-8")
            self.assertTrue(fake_gguf.exists())

            cache = GestorCache(db_path)
            descargador = DescargadorModelos(directorio_modelos=models_dir, gestor_cache=cache)

            # Guardar registro inicial
            reg = ModeloRegistro(
                id="test_archivable",
                repo_hf="user/test",
                filename="test_model.gguf",
                ruta_local=str(fake_gguf),
                estado="descargado",
                motivo_descarte=None,
                license="apache-2.0",
                training_summary_url="https://example.com/summary",
            )
            cache.guardar_modelo(reg)

            # Registrar un benchmark medido antes de archivar
            hw_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
            b_reg = BenchmarkRegistro(
                modelo_id="test_archivable",
                hash_hardware=hw_hash,
                binario_usado="gpu",
                n_gpu_layers=28,
                ctx_size=16384,
                tok_s=14.5,
                gtt_pico_mb=6200.0,
                exito_tool_calling=True,
            )
            cache.guardar_benchmark(b_reg)

            # Archivar sin archivo
            exito = descargador.archivar_modelo_sin_archivo("test_archivable")
            self.assertTrue(exito)
            self.assertFalse(fake_gguf.exists(), "El archivo físico debe eliminarse para ahorrar espacio")

            # El registro en base de datos DEBE persistir intacto
            recuperado = cache.obtener_modelo("test_archivable")
            self.assertIsNotNone(recuperado)
            self.assertEqual(recuperado["estado"], "archivado_sin_archivo")
            self.assertEqual(recuperado["ruta_local"], "")
            self.assertEqual(recuperado["license"], "apache-2.0")

            # La mejor configuración afinada DEBE estar disponible para reutilización
            afinamiento = descargador.consultar_afinamiento_guardado("test_archivable", hw_hash)
            self.assertIsNotNone(afinamiento)
            self.assertEqual(afinamiento["n_gpu_layers"], 28)
            self.assertEqual(afinamiento["ctx_size"], 16384)
            self.assertEqual(afinamiento["tok_s_medido"], 14.5)

    def test_descargar_modelo_por_id_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            cache = GestorCache(tmp_path / "test_str.db")
            descargador = DescargadorModelos(directorio_modelos=tmp_path, gestor_cache=cache)
            # Pre-crear archivo simulado para probar resolución por string ID
            def_nomic = CatalogoModelos.obtener_modelo("nomic-embed-text-v1.5")
            assert def_nomic is not None
            fake_path = tmp_path / def_nomic.filename
            fake_path.write_bytes(b"GGUF_FAKE_DATA")

            ruta_res = descargador.descargar_modelo("nomic-embed-text-v1.5", permitir_inseguro=True)
            self.assertEqual(ruta_res, fake_path)


if __name__ == "__main__":
    unittest.main()
