import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    TIENE_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    AESGCM = None  # type: ignore
    TIENE_CRYPTOGRAPHY = False


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

    Arquitectura criptográfica reforzada:
      - Derivación KDF mediante scrypt (RFC 7914, N=131072 / 2^17, r=8, p=1) resistente a GPU/ASIC.
      - Separación de dominios de clave postcuántica mediante función esponja SHAKE-256 (FIPS 202).
      - Cifrado autenticado estándar AES-256-GCM (AEAD) con clave de 256 bits y nonce de 96 bits.
      - Capa adicional de autenticación de cabecera con HMAC-SHA3-512.
    """

    ALGORITMO_IDENTIFICADOR = "PQC-AES256GCM-SCRYPT-SHA3_512-V2"
    ALGORITMO_IDENTIFICADOR_V1 = "PQC-SHAKE256-SHA3_512-V1"

    @classmethod
    def derivar_clave_postcuantica(
        cls, clave_maestra: str, salt: bytes, longitud_bytes: int = 64
    ) -> bytes:
        """Deriva material de clave postcuántica usando scrypt (N=131072) combinado con SHAKE-256."""
        material_base = hashlib.scrypt(
            clave_maestra.encode("utf-8"),
            salt=salt,
            n=131072,
            r=8,
            p=1,
            maxmem=256 * 1024 * 1024,
            dklen=64,
        )
        esponja = hashlib.shake_256(material_base + b"::GuarIdA-PQC-DomainSeparation::" + salt)
        return esponja.digest(longitud_bytes)

    @classmethod
    def derivar_clave_postcuantica_v1(
        cls, clave_maestra: str, salt: bytes, longitud_bytes: int = 64
    ) -> bytes:
        """Derivación heredada V1 para compatibilidad retrospectiva."""
        semilla = clave_maestra.encode("utf-8") + salt
        h1 = hashlib.sha3_512(semilla).digest()
        esponja = hashlib.shake_256(h1 + salt)
        return esponja.digest(longitud_bytes)

    @classmethod
    def cifrar_datos(cls, texto_plano: str | bytes, clave_maestra: str) -> SobreCriptografico:
        """Cifra datos con clave postcuántica y genera un sobre criptográfico autenticado."""
        if isinstance(texto_plano, str):
            datos_bytes = texto_plano.encode("utf-8")
        else:
            datos_bytes = texto_plano

        salt = secrets.token_bytes(32)  # 256 bits de salt

        if not TIENE_CRYPTOGRAPHY or AESGCM is None:
            raise RuntimeError("El cifrado de la Bóveda requiere obligatoriamente el motor AES-GCM ('cryptography').")

        nonce = secrets.token_bytes(12)  # 96 bits nonce para AES-GCM
        material_clave = cls.derivar_clave_postcuantica(
            clave_maestra=clave_maestra,
            salt=salt + nonce,
            longitud_bytes=64,
        )
        k_enc = material_clave[:32]
        k_mac = material_clave[32:64]

        aesgcm = AESGCM(k_enc)
        cifrado = aesgcm.encrypt(nonce, datos_bytes, associated_data=salt)
        mac = hmac.new(k_mac, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()
        algoritmo = cls.ALGORITMO_IDENTIFICADOR

        return SobreCriptografico(
            version="2.0",
            algoritmo=algoritmo,
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

        if sobre.algoritmo == cls.ALGORITMO_IDENTIFICADOR:
            if not TIENE_CRYPTOGRAPHY or AESGCM is None:
                raise RuntimeError("El sobre requiere el motor AES-GCM (paquete cryptography).")
            material_clave = cls.derivar_clave_postcuantica(
                clave_maestra=clave_maestra,
                salt=salt + nonce,
                longitud_bytes=64,
            )
            k_enc = material_clave[:32]
            k_mac = material_clave[32:64]

            mac_calculado = hmac.new(k_mac, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()
            if not hmac.compare_digest(mac_calculado, sobre.mac_autenticacion_hex):
                raise ValueError("Fallo de autenticación criptográfica: el sobre ha sido alterado o la clave es incorrecta.")

            try:
                aesgcm = AESGCM(k_enc)
                return aesgcm.decrypt(nonce, cifrado, associated_data=salt)
            except Exception as e:
                raise ValueError("Fallo de autenticación criptográfica: el sobre ha sido alterado o la clave es incorrecta.") from e

        if sobre.algoritmo == cls.ALGORITMO_IDENTIFICADOR_V1:
            material_clave = cls.derivar_clave_postcuantica_v1(
                clave_maestra=clave_maestra,
                salt=salt + nonce,
                longitud_bytes=len(cifrado) + 32,
            )
            keystream = material_clave[: len(cifrado)]
            mac_key = material_clave[len(cifrado) :]
            mac_calculado = hmac.new(mac_key, salt + nonce + cifrado, hashlib.sha3_512).hexdigest()
            if not hmac.compare_digest(mac_calculado, sobre.mac_autenticacion_hex):
                raise ValueError("Fallo de autenticación criptográfica: el sobre ha sido alterado o la clave es incorrecta.")
            return bytes(c ^ k for c, k in zip(cifrado, keystream))

        raise ValueError(f"Algoritmo criptográfico no soportado o desconocido: '{sobre.algoritmo}'")

    @classmethod
    def cifrar_archivo_json(cls, ruta_origen: Path, ruta_destino: Path, clave_maestra: str) -> None:
        """Guarda un archivo de configuración o datos cifrado en formato JSON sobre."""
        with open(ruta_origen, "r", encoding="utf-8") as f:
            contenido = f.read()

        sobre = cls.cifrar_datos(contenido, clave_maestra)
        payload = json.dumps(
            {
                "version": sobre.version,
                "algoritmo": sobre.algoritmo,
                "salt_hex": sobre.salt_hex,
                "nonce_hex": sobre.nonce_hex,
                "datos_cifrados_b64": sobre.datos_cifrados_b64,
                "mac_autenticacion_hex": sobre.mac_autenticacion_hex,
            },
            indent=2,
        )
        ruta_destino.parent.mkdir(parents=True, exist_ok=True)
        ruta_temp = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=ruta_destino.parent, delete=False, encoding="utf-8") as f_temp:
                f_temp.write(payload)
                f_temp.flush()
                os.fsync(f_temp.fileno())
                ruta_temp = Path(f_temp.name)
            try:
                os.chmod(ruta_temp, 0o600)
            except OSError:
                pass
            os.replace(ruta_temp, ruta_destino)
            ruta_temp = None
        finally:
            if ruta_temp and ruta_temp.exists():
                try:
                    ruta_temp.unlink()
                except OSError:
                    pass

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
