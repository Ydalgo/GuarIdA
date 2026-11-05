import tempfile
import unittest
from pathlib import Path

from guarida_manager.downloader.crypto import (
    BovedaCriptograficaPostcuantica,
    SobreCriptografico,
)


class TestCrypto(unittest.TestCase):
    def test_cifrado_y_descifrado_postcuantico_texto(self):
        clave_maestra = "GuarIdA_Super_Secret_Bunker_Key_2026!"
        mensaje_original = "Configuración ultrasecreta del búnker offline."

        sobre = BovedaCriptograficaPostcuantica.cifrar_datos(mensaje_original, clave_maestra)
        self.assertEqual(sobre.algoritmo, BovedaCriptograficaPostcuantica.ALGORITMO_IDENTIFICADOR)
        self.assertNotEqual(sobre.datos_cifrados_b64, mensaje_original)

        descifrado = BovedaCriptograficaPostcuantica.descifrar_datos(sobre, clave_maestra)
        self.assertEqual(descifrado.decode("utf-8"), mensaje_original)

    def test_compatibilidad_retrospectiva_v1(self):
        clave = "clave_v1_test"
        mensaje = "prueba de compatibilidad v1"
        # Simular sobre V1
        salt = bytes.fromhex("01" * 32)
        nonce = bytes.fromhex("02" * 16)
        material = BovedaCriptograficaPostcuantica.derivar_clave_postcuantica_v1(clave, salt + nonce, len(mensaje.encode("utf-8")) + 32)
        keystream = material[:len(mensaje.encode("utf-8"))]
        mac_key = material[len(mensaje.encode("utf-8")):]
        cifrado = bytes(b ^ k for b, k in zip(mensaje.encode("utf-8"), keystream))
        import base64, hmac, hashlib
        mac = hmac.new(mac_key, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()
        sobre_v1 = SobreCriptografico(
            version="1.0",
            algoritmo="PQC-SHAKE256-SHA3_512-V1",
            salt_hex=salt.hex(),
            nonce_hex=nonce.hex(),
            datos_cifrados_b64=base64.b64encode(cifrado).decode("ascii"),
            mac_autenticacion_hex=mac,
        )
        recuperado = BovedaCriptograficaPostcuantica.descifrar_datos(sobre_v1, clave)
        self.assertEqual(recuperado.decode("utf-8"), mensaje)

    def test_falla_autenticacion_si_clave_es_erronea(self):
        clave_correcta = "clave_bunker_1"
        clave_erronea = "clave_bunker_2"

        sobre = BovedaCriptograficaPostcuantica.cifrar_datos("datos protegidos", clave_correcta)
        with self.assertRaises(ValueError):
            BovedaCriptograficaPostcuantica.descifrar_datos(sobre, clave_erronea)

    def test_falla_autenticacion_si_sobre_esta_alterado(self):
        clave = "clave_test_mac"
        sobre = BovedaCriptograficaPostcuantica.cifrar_datos("datos confidenciales", clave)
        # Alterar mac
        sobre_alterado = SobreCriptografico(
            version=sobre.version,
            algoritmo=sobre.algoritmo,
            salt_hex=sobre.salt_hex,
            nonce_hex=sobre.nonce_hex,
            datos_cifrados_b64=sobre.datos_cifrados_b64,
            mac_autenticacion_hex="00" * 64,
        )
        with self.assertRaises(ValueError):
            BovedaCriptograficaPostcuantica.descifrar_datos(sobre_alterado, clave)

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
