import unittest

from guarida_manager.hardware import (
    calcular_hash_hardware,
    calcular_limites_memoria_gpu,
    clasificar_tipo_gpu,
    convertir_cadena_memoria_a_megabytes,
    obtener_informacion_hardware,
    obtener_memoria_ram_total,
    obtener_modelo_cpu,
    obtener_nucleos_cpu,
    parsear_dispositivos_llama,
)


class TestHardware(unittest.TestCase):
    def test_obtener_modelo_cpu(self):
        modelo = obtener_modelo_cpu()
        self.assertIsInstance(modelo, str)
        self.assertGreater(len(modelo), 0)

    def test_obtener_nucleos_cpu(self):
        fisicos, logicos = obtener_nucleos_cpu()
        self.assertIsInstance(fisicos, int)
        self.assertIsInstance(logicos, int)
        self.assertGreaterEqual(fisicos, 1)
        self.assertGreaterEqual(logicos, fisicos)

    def test_obtener_memoria_ram_total(self):
        ram_bytes = obtener_memoria_ram_total()
        self.assertIsInstance(ram_bytes, int)
        self.assertGreater(ram_bytes, 1024 * 1024 * 1024)

    def test_convertir_cadena_memoria_a_megabytes(self):
        self.assertEqual(convertir_cadena_memoria_a_megabytes("16", "GB"), 16384.0)
        self.assertEqual(convertir_cadena_memoria_a_megabytes("8", "GiB"), 8192.0)
        self.assertEqual(convertir_cadena_memoria_a_megabytes("1024", "MB"), 1024.0)
        self.assertEqual(convertir_cadena_memoria_a_megabytes("512", "MiB"), 512.0)

    def test_parsear_dispositivos_llama_vulkan(self):
        salida_vulkan = "Vulkan0: AMD Radeon (16GB)\n"
        dispositivos = parsear_dispositivos_llama(salida_vulkan)

        self.assertEqual(len(dispositivos), 1)
        gpu = dispositivos[0]
        self.assertEqual(gpu.identificador, "Vulkan0")
        self.assertEqual(gpu.nombre, "AMD Radeon")
        self.assertEqual(gpu.memoria_gb, 16.0)
        self.assertEqual(gpu.backend, "Vulkan")

    def test_parsear_dispositivos_llama_solo_cpu(self):
        salida_cpu = "Available devices:\n  CPU\n"
        dispositivos = parsear_dispositivos_llama(salida_cpu)
        self.assertEqual(len(dispositivos), 0)

    def test_parsear_dispositivos_llama_multiples(self):
        salida_multiple = (
            "Available devices:\n"
            "  Vulkan0: AMD Radeon RX 6700 XT (12272 MiB, 12272 MiB free)\n"
            "  Vulkan1: AMD Radeon Graphics (512 MiB, 512 MiB free)\n"
            "  CPU\n"
        )
        dispositivos = parsear_dispositivos_llama(salida_multiple)
        self.assertEqual(len(dispositivos), 2)
        self.assertEqual(dispositivos[0].nombre, "AMD Radeon RX 6700 XT")
        self.assertEqual(dispositivos[0].memoria_mb, 12272.0)
        self.assertEqual(dispositivos[1].nombre, "AMD Radeon Graphics")
        self.assertEqual(dispositivos[1].memoria_mb, 512.0)

    def test_calcular_hash_hardware(self):
        hash_1 = calcular_hash_hardware("AMD Ryzen 7 5700G", 17179869184, "AMD Radeon")
        hash_2 = calcular_hash_hardware("AMD Ryzen 7 5700G", 17179869184, "AMD Radeon")
        hash_distinto_ram = calcular_hash_hardware("AMD Ryzen 7 5700G", 34359738368, "AMD Radeon")
        hash_distinto_gpu = calcular_hash_hardware("AMD Ryzen 7 5700G", 17179869184, "CPU")

        self.assertEqual(hash_1, hash_2)
        self.assertNotEqual(hash_1, hash_distinto_ram)
        self.assertNotEqual(hash_1, hash_distinto_gpu)
        self.assertEqual(len(hash_1), 64)

    def test_clasificar_tipo_gpu(self):
        tipo_iris, es_integ_iris = clasificar_tipo_gpu("Intel(R) Iris(R) Xe Graphics", 0.12)
        self.assertEqual(tipo_iris, "Integrada / APU")
        self.assertTrue(es_integ_iris)

        tipo_rtx, es_integ_rtx = clasificar_tipo_gpu("NVIDIA GeForce RTX 4070", 12.0)
        self.assertEqual(tipo_rtx, "Dedicada")
        self.assertFalse(es_integ_rtx)

        tipo_radeon_apu, es_integ_radeon = clasificar_tipo_gpu("AMD Radeon 780M Graphics", 0.5)
        self.assertEqual(tipo_radeon_apu, "Integrada / APU")
        self.assertTrue(es_integ_radeon)

    def test_calcular_limites_memoria_gpu_integrada(self):
        # Sistema con 32 GB de RAM y APU (ej. 15.82 GB compartida WDDM)
        lim_seguro, lim_extremo, reserva = calcular_limites_memoria_gpu(
            vram_dedicada_gb=0.12,
            memoria_compartida_gb=15.82,
            ram_total_gb=32.0,
            es_integrada=True,
            sistema="Windows",
        )
        self.assertEqual(reserva, 3.5)
        self.assertEqual(lim_seguro, round(15.82 * 0.85, 2))
        # En extremo: 32.0 - 3.5 = 28.5 GB forzables
        self.assertEqual(lim_extremo, 28.5)

    def test_calcular_limites_memoria_gpu_dedicada(self):
        # GPU Dedicada de 16 GB VRAM
        lim_seguro, lim_extremo, reserva = calcular_limites_memoria_gpu(
            vram_dedicada_gb=16.0,
            memoria_compartida_gb=16.0,
            ram_total_gb=32.0,
            es_integrada=False,
            sistema="Linux",
        )
        self.assertEqual(reserva, 1.8)
        self.assertEqual(lim_seguro, 13.6)  # 85% de 16
        self.assertEqual(lim_extremo, 15.5)  # 16.0 - 0.5 GB para display

    def test_obtener_informacion_hardware_sistema_actual(self):
        info = obtener_informacion_hardware()
        self.assertGreater(len(info.modelo_cpu), 0)
        self.assertGreaterEqual(info.nucleos_fisicos, 1)
        self.assertGreater(info.ram_total_bytes, 0)
        self.assertGreater(info.ram_total_gb, 0.0)
        self.assertEqual(len(info.hash_hardware), 64)
        self.assertGreater(info.memoria_extrema_forzable_gb, 0.0)
        self.assertGreater(info.reserva_sistema_gb, 0.0)


if __name__ == "__main__":
    unittest.main()
