import unittest
from unittest.mock import MagicMock

from guarida_manager.engine.client import ClienteLlamaOffline
from guarida_manager.tuning.bateria import BateriaEstresLlama
from guarida_manager.tuning.perfiles import PerfilBateria


class TestBateriaArbolNodos(unittest.TestCase):
    def setUp(self):
        self.mock_cliente = MagicMock(spec=ClienteLlamaOffline)
        self.perfil = PerfilBateria(
            nombre="test",
            descripcion="Perfil test",
            repeticiones_min=1,
            repeticiones_max=1,
            calentamientos_descartados=0,
            enfriamiento_segundos=0.0,
            escenarios_activos=["embedding", "arbol_nodos"],
        )
        self.bateria = BateriaEstresLlama(self.mock_cliente, self.perfil)

    def test_ejecutar_escenario_embedding(self):
        # Simular retorno del cliente de embeddings
        self.mock_cliente.calcular_embedding.return_value = [0.1] * 768

        resultados = self.bateria.ejecutar_escenario_embedding(
            textos=["def foo(): pass", "def bar(): pass"]
        )

        self.assertEqual(len(resultados), 1)
        res = resultados[0]
        self.assertEqual(res["escenario"], "embedding")
        self.assertEqual(res["exito"], 1)
        self.assertEqual(res["dimensiones_vector"], 768)
        self.assertGreater(res["embeddings_por_s"], 0)

    def test_ejecutar_escenario_arbol_nodos_comparativa(self):
        # Simular embedding para AST
        def fake_embedding(texto: str) -> list[float]:
            if "derivar_clave_maestra" in texto or "shake" in texto.lower():
                return [1.0, 0.0]
            return [0.0, 1.0]

        self.mock_cliente.calcular_embedding.side_effect = fake_embedding

        # Simular respuestas generativas para baseline y asistido
        def fake_completar(prompt: str, **kwargs):
            if "Contexto semántico AST" in prompt:
                return {
                    "content": "Utiliza SHAKE-256 generando 32 bytes con digest().",
                    "timings": {
                        "prompt_n": 45,
                        "predicted_n": 15,
                        "prompt_per_second": 120.0,
                        "predicted_per_second": 35.0,
                    },
                }
            else:
                return {
                    "content": "Aplica una función de derivación.",
                    "timings": {
                        "prompt_n": 180,
                        "predicted_n": 10,
                        "prompt_per_second": 95.0,
                        "predicted_per_second": 25.0,
                    },
                }

        self.mock_cliente.completar_texto.side_effect = fake_completar

        resultados = self.bateria.ejecutar_escenario_arbol_nodos()

        self.assertEqual(len(resultados), 1)
        res = resultados[0]
        self.assertEqual(res["escenario"], "arbol_nodos_comparativa")
        self.assertEqual(res["exito"], 1)
        self.assertIn("comparativa", res)

        comp = res["comparativa"]
        self.assertEqual(comp["prompt_tokens_baseline"], 180)
        self.assertEqual(comp["prompt_tokens_arbol"], 45)
        self.assertGreater(comp["ahorro_tokens_pct"], 70.0)
        self.assertIn("derivar_clave_maestra", comp["nodo_recuperado"])
        self.assertGreater(comp["calidad_arbol_pct"], comp["calidad_baseline_pct"])

    def test_instanciacion_perfil_comparativa_menu(self):
        # Verifica la configuración utilizada en la opción 6 del menú de afinamiento
        perfil_bat = PerfilBateria(
            nombre="comparativa_ast",
            descripcion="Comparativa AST vs Directo",
            repeticiones_min=2,
            repeticiones_max=3,
            calentamientos_descartados=1,
            enfriamiento_segundos=0.5,
            escenarios_activos=["embedding", "arbol_nodos"],
        )
        self.assertEqual(perfil_bat.nombre, "comparativa_ast")
        self.assertIn("arbol_nodos", perfil_bat.escenarios_activos)


if __name__ == "__main__":
    unittest.main()
