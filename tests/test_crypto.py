import tempfile
import unittest
from pathlib import Path

from guarida_manager.downloader.crypto import BovedaCriptograficaPostcuantica


class TestCrypto(unittest.TestCase):
    def test_cifrado_y_descifrado_postcuantico_texto(self):
        clave_maestra = "GuarIdA_Super_Secret_Bunker_Key_2026!"
        mensaje_original = "Configuración ultrasecreta del búnker offline."

        sobre = BovedaCriptograficaPostcuantica.cifrar_datos(mensaje_original, clave_maestra)
        self.assertEqual(sobre.algoritmo, "PQC-SHAKE256-SHA3_512-V1")
        self.assertNotEqual(sobre.datos_cifrados_b64, mensaje_original)

        descifrado = BovedaCriptograficaPostcuantica.descifrar_datos(sobre, clave_maestra)
        self.assertEqual(descifrado.decode("utf-8"), mensaje_original)

    def test_falla_autenticacion_si_clave_es_erronea(self):
        clave_correcta = "clave_bunker_1"
        clave_erronea = "clave_bunker_2"

        sobre = BovedaCriptograficaPostcuantica.cifrar_datos("datos protegidos", clave_correcta)
        with self.assertRaises(ValueError):
            BovedaCriptograficaPostcuantica.descifrar_datos(sobre, clave_erronea)

    def test_cifrado_archivo_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            ruta_origen = dir_path / "config.json"
            ruta_cifrada = dir_path / "config.pqc.json"

            clave = "clave_prueba"
            ruta_origen.write_text('{"modo": "bunker", "postcuantico": true}', encoding="utf-8")

            BovedaCriptograficaPostcuantica.cifrar_archivo_json(ruta_origen, ruta_cifrada, clave)
            self.assertTrue(ruta_cifrada.exists())

            recuperado_texto = BovedaCriptograficaPostcuantica.descifrar_archivo_json(ruta_cifrada, clave)
            self.assertIn('"modo": "bunker"', recuperado_texto)


if __name__ == "__main__":
    unittest.main()
