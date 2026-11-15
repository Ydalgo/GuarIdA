import unittest

from guarida_manager.comparator import AnalisisCuantizacion, ComparadorModelosHardware


class TestComparator(unittest.TestCase):
    def test_analizar_cuantizaciones_7b(self):
        analisis = ComparadorModelosHardware.analizar_cuantizaciones_7b()
        self.assertGreaterEqual(len(analisis), 4)

        cuantizaciones = [a.cuantizacion for a in analisis]
        self.assertIn("Q5_K_M", cuantizaciones)
        self.assertIn("Q4_K_M", cuantizaciones)
        self.assertIn("Q3_K_M", cuantizaciones)
        self.assertIn("Q2_K", cuantizaciones)

        for a in analisis:
            self.assertIsInstance(a, AnalisisCuantizacion)
            self.assertEqual(a.modelo_base, "Qwen2.5-Coder-7B")
            self.assertGreater(a.tamano_pesos_gb, 0.0)
            self.assertGreater(a.vram_total_16k_gb, a.tamano_pesos_gb)
            self.assertGreater(a.vram_total_32k_gb, a.vram_total_16k_gb)
            self.assertGreater(a.calidad_relativa_pct, 0.0)
            self.assertIsInstance(a.es_viable_16k_gpu, bool)
            self.assertIsInstance(a.es_viable_32k_gpu, bool)

    def test_evaluar_modelo_completo_formulas_y_umbrales(self):
        from guarida_manager.hardware import InformacionHardware
        from guarida_manager.comparator import EstimacionRendimientoModelo

        hw_gpu = InformacionHardware(
            modelo_cpu="Intel i7",
            nucleos_fisicos=8,
            nucleos_logicos=16,
            ram_total_bytes=32 * 1024**3,
            ram_total_gb=32.0,
            gpus=(),
            nombre_gpu_principal="NVIDIA RTX 4070",
            tiene_aceleracion_gpu=True,
            gtt_disponible_gb=12.0,
            hash_hardware="hash_gpu_test",
            memoria_extrema_forzable_gb=28.0,
        )

        # Evaluar modelo pequeño (0.5B) -> debe ser óptimo e instantáneo
        ev_05 = ComparadorModelosHardware.evaluar_modelo_completo("qwen2.5-coder-0.5b-q4", 0.39, hardware=hw_gpu)
        self.assertIsInstance(ev_05, EstimacionRendimientoModelo)
        self.assertGreater(ev_05.tok_s_estimado, 30.0)
        self.assertIn("ÓPTIMO", ev_05.clasificacion_coding)
        self.assertIn("INSTANTÁNEO", ev_05.clasificacion_chat)
        self.assertEqual(ev_05.estrategia_vram, "GPU_COMPLETO")
        self.assertGreater(ev_05.vram_requerida_16k_gb, ev_05.vram_requerida_4k_gb)

        # Evaluar modelo 7B en GPU
        ev_7b = ComparadorModelosHardware.evaluar_modelo_completo("qwen2.5-coder-7b-q4", 4.68, hardware=hw_gpu)
        self.assertGreaterEqual(ev_7b.tok_s_estimado, 15.0)
        self.assertIn("ÓPTIMO", ev_7b.clasificacion_coding)

    def test_apoyo_en_registros_reales_sqlite(self):
        import tempfile
        from pathlib import Path
        from guarida_manager.cache import GestorCache, ConfiguracionOptimaRegistro
        from guarida_manager.hardware import InformacionHardware

        hw = InformacionHardware(
            modelo_cpu="Intel i5",
            nucleos_fisicos=4,
            nucleos_logicos=8,
            ram_total_bytes=16 * 1024**3,
            ram_total_gb=16.0,
            gpus=(),
            nombre_gpu_principal="Intel Iris Xe",
            tiene_aceleracion_gpu=True,
            gtt_disponible_gb=8.0,
            hash_hardware="hash_db_test_123",
            memoria_extrema_forzable_gb=12.0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = GestorCache(Path(tmp_dir) / "test_comp.db")
            # Sin registro previo -> es_medido_real es False
            ev_antes = ComparadorModelosHardware.evaluar_modelo_completo("mod_x", 4.0, hardware=hw, gestor_cache=cache)
            self.assertFalse(ev_antes.es_medido_real)

            # Insertar registro real de benchmark
            from guarida_manager.cache import ModeloRegistro
            cache.guardar_modelo(ModeloRegistro(id="mod_x", repo_hf="x/y", filename="mod_x.gguf", ruta_local="", estado="disponible"))
            cache.guardar_configuracion_optima(ConfiguracionOptimaRegistro(
                modelo_id="mod_x",
                hash_hardware=hw.hash_hardware,
                n_gpu_layers=24,
                ctx_size=4096,
                batch_size=512,
                kv_cache_tipo="q8_0",
                tok_s_medido=27.4,
                gtt_pico_mb=4200.0,
                fecha_afinamiento="2026-11-08T10:00:00Z",
                es_recomendada=True,
            ))

            # Con registro real en BD -> es_medido_real es True y usa el tok/s exacto medido
            ev_despues = ComparadorModelosHardware.evaluar_modelo_completo("mod_x", 4.0, hardware=hw, gestor_cache=cache)
            self.assertTrue(ev_despues.es_medido_real)
            self.assertEqual(ev_despues.tok_s_estimado, 27.4)

    def test_afinamiento_combinado_score_y_recomendacion(self):
        import tempfile
        from pathlib import Path
        from guarida_manager.cache import GestorCache, ModeloRegistro
        from guarida_manager.menu_actions import calcular_afinamiento_combinado

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = GestorCache(Path(tmp_dir) / "test_comb.db")
            cache.guardar_modelo(ModeloRegistro(id="qwen2.5-coder-7b-q4", repo_hf="a/b", filename="a.gguf", ruta_local="", estado="disponible"))
            cache.guardar_modelo(ModeloRegistro(id="jina-embeddings-v2-code-q4", repo_hf="c/d", filename="b.gguf", ruta_local="", estado="disponible"))

            res = calcular_afinamiento_combinado(cache, "qwen2.5-coder-7b-q4", "jina-embeddings-v2-code-q4")
            self.assertIn("score_conjunto", res)
            self.assertGreater(res["score_conjunto"], 0.0)
            self.assertIn("recomendacion_uso", res)
            self.assertIn("refactorización AST", res["recomendacion_uso"])
            self.assertGreater(res["memoria_conjunta_mb"], 0.0)
            self.assertEqual(res["modelo_gen_id"], "qwen2.5-coder-7b-q4")
            self.assertEqual(res["modelo_emb_id"], "jina-embeddings-v2-code-q4")


if __name__ == "__main__":
    unittest.main()
