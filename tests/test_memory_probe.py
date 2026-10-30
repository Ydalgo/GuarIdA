import unittest

from guarida_manager.memory_probe import (
    ResultadoPruebaMemoria,
    ejecutar_prueba_estres_memoria,
    probar_asignacion_ram_real,
    probar_asignacion_vulkan_real,
)


class TestMemoryProbe(unittest.TestCase):
    def test_probar_asignacion_ram_real(self):
        # Probar una asignacion real ligera de 512 MB
        gb_asignados, velocidad, integridad = probar_asignacion_ram_real(objetivo_gb=0.5)
        self.assertGreaterEqual(gb_asignados, 0.5)
        self.assertGreater(velocidad, 0.0)
        self.assertTrue(integridad)

    def test_probar_asignacion_vulkan_pequena(self):
        # Si Vulkan esta disponible, probar asignacion de 1 chunk
        vram_gb, chunks, integridad, motivo = probar_asignacion_vulkan_real(
            objetivo_gb=1.0,
            chunk_gb=1.0,
        )
        if chunks > 0:
            self.assertGreaterEqual(vram_gb, 1.0)
            self.assertTrue(integridad)
        else:
            # En entornos sin GPU Vulkan debe fallar de forma controlada sin excepciones
            self.assertIsInstance(motivo, str)

    def test_ejecutar_prueba_estres_resultado_estructura(self):
        mensajes_recibidos = []
        resultado = ejecutar_prueba_estres_memoria(
            limite_forzar_gb=1.5,
            probar_ram=True,
            callback_progreso=lambda msg: mensajes_recibidos.append(msg),
        )
        self.assertIsInstance(resultado, ResultadoPruebaMemoria)
        self.assertGreater(len(mensajes_recibidos), 0)
        self.assertGreater(resultado.memoria_total_verificada_gb, 0.0)
        self.assertTrue(resultado.integridad_verificada)


if __name__ == "__main__":
    unittest.main()
