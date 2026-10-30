import unittest

from guarida_manager.downloader.compliance import (
    EstadoCumplimiento,
    GestorCumplimientoNormativo,
    RegionNormativa,
)


class TestCompliance(unittest.TestCase):
    def test_evaluacion_modelo_conforme_eu_ai_act(self):
        evaluacion = GestorCumplimientoNormativo.evaluar_modelo(
            modelo_id="qwen-coder",
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
            copyright_compliant=True,
            region=RegionNormativa.ES_EU,
        )
        self.assertEqual(evaluacion.estado, EstadoCumplimiento.CONFORME)
        self.assertTrue(evaluacion.es_apto_para_uso)
        self.assertIn("EU AI Act", evaluacion.resumen_legal)

    def test_evaluacion_modelo_sin_resumen_entrenamiento(self):
        evaluacion = GestorCumplimientoNormativo.evaluar_modelo(
            modelo_id="modelo-privado",
            licencia="apache-2.0",
            training_summary_url=None,
            copyright_compliant=True,
            region=RegionNormativa.ES_EU,
        )
        self.assertEqual(evaluacion.estado, EstadoCumplimiento.REQUIERE_REVISION)
        self.assertTrue(evaluacion.es_apto_para_uso)

    def test_evaluacion_region_global(self):
        evaluacion = GestorCumplimientoNormativo.evaluar_modelo(
            modelo_id="cualquier-modelo",
            licencia="custom-license",
            training_summary_url=None,
            copyright_compliant=False,
            region=RegionNormativa.GLOBAL,
        )
        self.assertEqual(evaluacion.estado, EstadoCumplimiento.CONFORME)
        self.assertTrue(evaluacion.es_apto_para_uso)


if __name__ == "__main__":
    unittest.main()
