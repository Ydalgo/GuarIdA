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

        # Verificar modelos margen por abajo (ultraligeros)
        q05 = CatalogoModelos.obtener_modelo("qwen2.5-coder-0.5b-q4")
        self.assertIsNotNone(q05)
        self.assertLess(q05.tamano_gb, 1.0)
        smol = CatalogoModelos.obtener_modelo("smollm2-360m-instruct-q8")
        self.assertIsNotNone(smol)
        self.assertLess(smol.tamano_gb, 0.5)

        # Verificar modelos margen por arriba (alta potencia / workstation)
        q14 = CatalogoModelos.obtener_modelo("qwen2.5-coder-14b-q4")
        self.assertIsNotNone(q14)
        self.assertGreaterEqual(q14.tamano_gb, 8.0)
        q32 = CatalogoModelos.obtener_modelo("qwen2.5-coder-32b-q4")
        self.assertIsNotNone(q32)
        self.assertGreaterEqual(q32.tamano_gb, 18.0)
        deepseek_r1 = CatalogoModelos.obtener_modelo("deepseek-r1-distill-qwen-14b-q4")
        self.assertIsNotNone(deepseek_r1)

    def test_estimacion_y_afinamiento_automatico(self):
        from guarida_manager.hardware import InformacionHardware
        from guarida_manager.menu_actions import estimar_conjunto_modelos_optimo, afinar_modelo_automatico

        # Test HW modesto -> Tier ultraligero
        hw_modesto = InformacionHardware(
            modelo_cpu="Intel Celeron",
            nucleos_fisicos=2,
            nucleos_logicos=2,
            ram_total_bytes=4 * 1024**3,
            ram_total_gb=4.0,
            gpus=(),
            nombre_gpu_principal="None",
            tiene_aceleracion_gpu=False,
            gtt_disponible_gb=0.0,
            hash_hardware="test_modesto_hash",
            memoria_extrema_forzable_gb=3.0,
        )
        est_modesto = estimar_conjunto_modelos_optimo(hw_modesto)
        self.assertEqual(est_modesto["tier"], "ultraligero")
        self.assertIn("qwen2.5-coder-0.5b-q4", est_modesto["modelos"])

        # Test HW potente -> Tier workstation_pro_64gb
        hw_workstation = InformacionHardware(
            modelo_cpu="AMD Ryzen 9",
            nucleos_fisicos=16,
            nucleos_logicos=32,
            ram_total_bytes=64 * 1024**3,
            ram_total_gb=64.0,
            gpus=(),
            nombre_gpu_principal="NVIDIA RTX 4090",
            tiene_aceleracion_gpu=True,
            gtt_disponible_gb=24.0,
            hash_hardware="test_workstation_hash",
            memoria_extrema_forzable_gb=50.0,
        )
        est_workstation = estimar_conjunto_modelos_optimo(hw_workstation)
        self.assertEqual(est_workstation["tier"], "workstation_pro_64gb")
        self.assertIn("qwen2.5-coder-32b-q4", est_workstation["modelos"])

        # Test HW extremo 128 GB VRAM -> Tier ultra_128gb
        hw_128 = InformacionHardware(
            modelo_cpu="Apple M4 Ultra / Dual H100",
            nucleos_fisicos=24,
            nucleos_logicos=24,
            ram_total_bytes=128 * 1024**3,
            ram_total_gb=128.0,
            gpus=(),
            nombre_gpu_principal="NVIDIA H100 80GB HBM3",
            tiene_aceleracion_gpu=True,
            gtt_disponible_gb=120.0,
            hash_hardware="test_128vram_hash",
            memoria_extrema_forzable_gb=120.0,
        )
        est_128 = estimar_conjunto_modelos_optimo(hw_128)
        self.assertEqual(est_128["tier"], "ultra_128gb")
        self.assertIn("qwen2.5-72b-instruct-q4", est_128["modelos"])

        # Test auto-afinamiento en cache
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = GestorCache(Path(tmp_dir) / "test_tune.db")
            reg = afinar_modelo_automatico(cache, "qwen2.5-coder-0.5b-q4")
            self.assertEqual(reg.modelo_id, "qwen2.5-coder-0.5b-q4")
            self.assertGreater(reg.ctx_size, 0)
            self.assertGreater(reg.batch_size, 0)

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
