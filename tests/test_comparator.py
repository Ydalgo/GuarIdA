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


if __name__ == "__main__":
    unittest.main()
