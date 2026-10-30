import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class SobreCriptografico:
    version: str
    algoritmo: str
    salt_hex: str
    nonce_hex: str
    datos_cifrados_b64: str
    mac_autenticacion_hex: str


class BovedaCriptograficaPostcuantica:
    """Bóveda de cifrado y autenticación para el almacenamiento local del Búnker GuarIdA.

    Diseñada con preparación para la era postcuántica (PQC-Ready):
      - Derivación de claves basada en la función esponja SHAKE-256 (FIPS 202) y SHA3-512.
      - 256 bits de seguridad cuántica simétrica (resistente al algoritmo de Grover).
      - Autenticación de integridad con MAC derivado de SHA3-512 para prevenir manipulación.
      - Cifrado simétrico de flujo con keystream derivado de alta entropía.
    """

    ALGORITMO_IDENTIFICADOR = "PQC-SHAKE256-SHA3_512-V1"

    @classmethod
    def derivar_clave_postcuantica(
        cls, clave_maestra: str, salt: bytes, longitud_bytes: int = 64
    ) -> bytes:
        """Deriva una clave de longitud arbitraria usando la función esponja SHAKE-256."""
        semilla = clave_maestra.encode("utf-8") + salt
        # Primera etapa: Absorción en SHA3-512
        h1 = hashlib.sha3_512(semilla).digest()
        # Segunda etapa: Expansión de tasa variable mediante SHAKE-256 (Sponge function)
        esponja = hashlib.shake_256(h1 + salt)
        return esponja.digest(longitud_bytes)

    @classmethod
    def cifrar_datos(cls, texto_plano: str | bytes, clave_maestra: str) -> SobreCriptografico:
        """Cifra datos con clave postcuántica y genera un sobre criptográfico autenticado."""
        if isinstance(texto_plano, str):
            datos_bytes = texto_plano.encode("utf-8")
        else:
            datos_bytes = texto_plano

        salt = secrets.token_bytes(32)   # 256 bits de salt
        nonce = secrets.token_bytes(16)  # 128 bits de nonce

        # Derivar 64 bytes: 32 bytes para keystream de cifrado y 32 bytes para autenticacion MAC
        material_clave = cls.derivar_clave_postcuantica(
            clave_maestra=clave_maestra,
            salt=salt + nonce,
            longitud_bytes=len(datos_bytes) + 32,
        )

        keystream = material_clave[: len(datos_bytes)]
        mac_key = material_clave[len(datos_bytes) :]

        # Cifrado XOR autenticado con keystream criptográfico derivado de SHAKE-256
        cifrado = bytes(b ^ k for b, k in zip(datos_bytes, keystream))

        # Generar código de autenticación de mensaje (MAC) con SHA3-512
        mac = hmac.new(mac_key, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()

        return SobreCriptografico(
            version="1.0",
            algoritmo=cls.ALGORITMO_IDENTIFICADOR,
            salt_hex=salt.hex(),
            nonce_hex=nonce.hex(),
            datos_cifrados_b64=base64.b64encode(cifrado).decode("ascii"),
            mac_autenticacion_hex=mac,
        )

    @classmethod
    def descifrar_datos(cls, sobre: SobreCriptografico, clave_maestra: str) -> bytes:
        """Descifra el sobre y verifica la autenticidad e integridad de los datos."""
        salt = bytes.fromhex(sobre.salt_hex)
        nonce = bytes.fromhex(sobre.nonce_hex)
        cifrado = base64.b64decode(sobre.datos_cifrados_b64.encode("ascii"))

        material_clave = cls.derivar_clave_postcuantica(
            clave_maestra=clave_maestra,
            salt=salt + nonce,
            longitud_bytes=len(cifrado) + 32,
        )

        keystream = material_clave[: len(cifrado)]
        mac_key = material_clave[len(cifrado) :]

        # Verificar integridad antes de descifrar (Encrypt-then-MAC)
        mac_calculado = hmac.new(mac_key, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()
        if not hmac.compare_digest(mac_calculado, sobre.mac_autenticacion_hex):
            raise ValueError("Fallo de autenticación criptográfica: el sobre ha sido alterado o la clave es incorrecta.")

        return bytes(c ^ k for c, k in zip(cifrado, keystream))

    @classmethod
    def cifrar_archivo_json(cls, ruta_origen: Path, ruta_destino: Path, clave_maestra: str) -> None:
        """Guarda un archivo de configuración o datos cifrado en formato JSON sobre."""
        with open(ruta_origen, "r", encoding="utf-8") as f:
            contenido = f.read()

        sobre = cls.cifrar_datos(contenido, clave_maestra)
        with open(ruta_destino, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": sobre.version,
                    "algoritmo": sobre.algoritmo,
                    "salt_hex": sobre.salt_hex,
                    "nonce_hex": sobre.nonce_hex,
                    "datos_cifrados_b64": sobre.datos_cifrados_b64,
                    "mac_autenticacion_hex": sobre.mac_autenticacion_hex,
                },
                f,
                indent=2,
            )

    @classmethod
    def descifrar_archivo_json(cls, ruta_cifrada: Path, clave_maestra: str) -> str:
        """Lee y descifra un archivo JSON cifrado con la bóveda."""
        with open(ruta_cifrada, "r", encoding="utf-8") as f:
            datos = json.load(f)

        sobre = SobreCriptografico(
            version=datos["version"],
            algoritmo=datos["algoritmo"],
            salt_hex=datos["salt_hex"],
            nonce_hex=datos["nonce_hex"],
            datos_cifrados_b64=datos["datos_cifrados_b64"],
            mac_autenticacion_hex=datos["mac_autenticacion_hex"],
        )
        return cls.descifrar_datos(sobre, clave_maestra).decode("utf-8")

    @staticmethod
    def calcular_sha3_512_archivo(ruta_archivo: Path) -> str:
        """Calcula el hash SHA3-512 de un archivo grande en streaming."""
        h = hashlib.sha3_512()
        with open(ruta_archivo, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()
