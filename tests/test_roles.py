import unittest

from guarida_manager.roles import AsignacionRoles, MensajeInterModelo, RolAgente


class TestRoles(unittest.TestCase):
    def test_roles_valores(self):
        self.assertEqual(RolAgente.CONVERSACIONAL.value, "conversacional")
        self.assertEqual(RolAgente.CODER.value, "coder")
        self.assertEqual(RolAgente.EMBEDDING_INDEXER.value, "embedding_indexer")
        self.assertEqual(RolAgente.REVIEWER.value, "reviewer")

    def test_mensaje_inter_modelo_serializacion(self):
        msg = MensajeInterModelo(
            emisor_rol="conversacional",
            receptor_rol="coder",
            tipo_accion="SOLICITUD_CODIGO",
            idioma_comunicacion="es",
            payload={"tarea": "refactor_cache", "archivo": "cache.py"},
        )
        serialized = msg.serializar_para_prompt()
        self.assertIn('"emisor_rol": "conversacional"', serialized)
        self.assertIn('"tipo_accion": "SOLICITUD_CODIGO"', serialized)

        recuperado = MensajeInterModelo.deserializar(serialized)
        self.assertEqual(recuperado.emisor_rol, msg.emisor_rol)
        self.assertEqual(recuperado.receptor_rol, msg.receptor_rol)
        self.assertEqual(recuperado.payload["archivo"], "cache.py")

    def test_asignacion_roles_resumen(self):
        asignacion = AsignacionRoles(
            modelo_conversacional_id="qwen2.5-3b-chat-q4",
            modelo_coder_id="qwen2.5-coder-7b-q4",
            modelo_embedding_id="bge-m3-q4",
            modelo_sin_censura_id="qwen2.5-coder-7b-abliterated-q4",
        )
        resumen = asignacion.resumen_roles()
        self.assertEqual(resumen["Chat / Interfaz con Usuario"], "qwen2.5-3b-chat-q4")
        self.assertEqual(resumen["Motor de Código (Coder)"], "qwen2.5-coder-7b-q4")
        self.assertEqual(resumen["Memoria y Árboles de Nodos (Embeddings)"], "bge-m3-q4")
        self.assertEqual(resumen["Modelo Sin Censura (Opcional)"], "qwen2.5-coder-7b-abliterated-q4")


if __name__ == "__main__":
    unittest.main()
