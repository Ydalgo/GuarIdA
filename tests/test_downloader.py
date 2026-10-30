import tempfile
import unittest
from pathlib import Path

from guarida_manager.cache import GestorCache, ModeloRegistro
from guarida_manager.downloader.binaries import GestorBinariosLlama
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.models import CatalogoModelos, DescargadorModelos


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
            descargador = DescargadorModelos(directorio_modelos=models_dir)
            descargador.cache = cache

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


if __name__ == "__main__":
    unittest.main()
