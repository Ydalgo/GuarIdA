import tempfile
import unittest
from pathlib import Path

from guarida_manager.cache import BenchmarkRegistro, GestorCache, ModeloRegistro


class TestCache(unittest.TestCase):
    def setUp(self):
        self.directorio_temporal = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self.directorio_temporal.name) / "test_guarida.db"
        self.cache = GestorCache(self.ruta_db)

    def tearDown(self):
        self.directorio_temporal.cleanup()

    def test_inicializacion_tablas(self):
        self.assertTrue(self.ruta_db.exists())
        with self.cache.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            tablas = [fila[0] for fila in cursor.fetchall()]
            self.assertIn("modelos", tablas)
            self.assertIn("benchmarks", tablas)
            self.assertIn("modulos_instalados", tablas)

    def test_guardar_y_obtener_modelo(self):
        modelo = ModeloRegistro(
            id="qwen-2.5-0.5b",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
            ruta_local="/fake/path/qwen2.5-0.5b-instruct-q4_k_m.gguf",
            estado="optimo",
            motivo_descarte=None,
            license="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
        )
        self.cache.guardar_modelo(modelo)

        recuperado = self.cache.obtener_modelo("qwen-2.5-0.5b")
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado["repo_hf"], "Qwen/Qwen2.5-0.5B-Instruct-GGUF")
        self.assertEqual(recuperado["estado"], "optimo")

    def test_actualizar_estado_modelo(self):
        modelo = ModeloRegistro(
            id="test-model",
            repo_hf="user/repo",
            filename="model.gguf",
            ruta_local="/path/model.gguf",
            estado="optimo",
        )
        self.cache.guardar_modelo(modelo)

        self.cache.actualizar_estado_modelo(
            modelo_id="test-model",
            estado="descartado",
            motivo_descarte="Fallo en tool calling estructurado",
        )

        actualizado = self.cache.obtener_modelo("test-model")
        self.assertEqual(actualizado["estado"], "descartado")
        self.assertEqual(
            actualizado["motivo_descarte"], "Fallo en tool calling estructurado"
        )

    def test_benchmark_cache_flujo(self):
        modelo = ModeloRegistro(
            id="qwen-0.5b",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen0.5b.gguf",
            ruta_local="/models/qwen0.5b.gguf",
            estado="optimo",
        )
        self.cache.guardar_modelo(modelo)

        hash_hw = "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"

        inexistente = self.cache.obtener_benchmark("qwen-0.5b", hash_hw)
        self.assertIsNone(inexistente)

        benchmark = BenchmarkRegistro(
            modelo_id="qwen-0.5b",
            hash_hardware=hash_hw,
            binario_usado="gpu",
            n_gpu_layers=99,
            ctx_size=8192,
            tok_s=45.8,
            gtt_pico_mb=1450.0,
            exito_tool_calling=True,
        )
        id_benchmark = self.cache.guardar_benchmark(benchmark)
        self.assertGreater(id_benchmark, 0)

        existente = self.cache.obtener_benchmark("qwen-0.5b", hash_hw)
        self.assertIsNotNone(existente)
        self.assertEqual(existente["binario_usado"], "gpu")
        self.assertEqual(existente["tok_s"], 45.8)
        self.assertTrue(existente["exito_tool_calling"])

    def test_modulos_instalados(self):
        self.assertFalse(self.cache.verificar_modulo_instalado("core"))

        self.cache.registrar_modulo_instalado("core")
        self.assertTrue(self.cache.verificar_modulo_instalado("core"))

        modulos = self.cache.obtener_modulos_instalados()
        self.assertEqual(len(modulos), 1)
        self.assertEqual(modulos[0]["nombre"], "core")


if __name__ == "__main__":
    unittest.main()
