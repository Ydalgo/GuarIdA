"""Módulo de sanitización de privacidad (<private>) y anonimización RGPD con auditoría HMAC."""

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MODOS_PRIVACIDAD = ("estandar", "rgpd_estricto")

_RE_BLOQUE_PRIVATE = re.compile(r"<private\b[^>]*>.*?</private>", re.IGNORECASE | re.DOTALL)
_RE_CLAVE_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_RE_TOKEN_API = re.compile(r"\b(?:sk-[a-zA-Z0-9]{16,}|ghp_[a-zA-Z0-9]{16,}|AKIA[0-9A-Z]{16})\b")

_RE_RGPD_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_RE_RGPD_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[\s-]?\d{4}){3,7}(?:[\s-]?\d{1,4})?\b")
_RE_RGPD_DNI_NIE = re.compile(r"\b(?:[XYZ]\d{7}[A-Z]|\d{8}[A-Z])\b")
_RE_RGPD_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_RE_RGPD_TELEFONO = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s-]?)?\b(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{3}[\s-]\d{2}[\s-]\d{2}[\s-]\d{2}|\d{9,12})\b"
)


@dataclass(frozen=True)
class RegistroAuditoriaPrivacidad:
    """Evento criptográfico verificable de redacción sin retención del dato original."""

    timestamp_utc: str
    regla: str
    etiqueta: str
    origen: str
    hmac_sha256: str


@dataclass
class ResultadoSanitizacion:
    """Resultado de aplicar las reglas de privacidad sobre un texto."""

    texto_sanitizado: str
    total_redacciones: int
    modo: str
    eventos_auditoria: list[RegistroAuditoriaPrivacidad]


class SanitizadorPrivacidad:
    """Filtra bloques <private>, secretos y PII (modo RGPD estricto) con registro HMAC-SHA256."""

    def __init__(
        self,
        modo: str = "estandar",
        clave_hmac: Optional[bytes] = None,
        ruta_log_auditoria: Optional[Path | str] = None,
    ) -> None:
        self.modo = ""
        self.configurar_modo(modo)
        self._clave_hmac = clave_hmac if clave_hmac is not None else os.urandom(32)
        self.ruta_log_auditoria = Path(ruta_log_auditoria) if ruta_log_auditoria else None
        self.historial_auditoria: list[RegistroAuditoriaPrivacidad] = []

    def configurar_modo(self, modo: str) -> None:
        """Establece el modo de privacidad ('estandar' o 'rgpd_estricto')."""
        modo_norm = modo.strip().lower()
        if modo_norm not in MODOS_PRIVACIDAD:
            raise ValueError(f"Modo de privacidad inválido: '{modo}'. Válidos: {MODOS_PRIVACIDAD}")
        self.modo = modo_norm

    def _generar_hmac(self, regla: str, valor_original: str) -> str:
        mensaje = f"{regla}:{valor_original}".encode("utf-8", errors="replace")
        return hmac.new(self._clave_hmac, mensaje, hashlib.sha256).hexdigest()

    def _aplicar_regla(
        self,
        texto: str,
        regla: str,
        patron: re.Pattern[str],
        plantilla_etiqueta: str,
        origen: str,
        contadores: dict[str, int],
        eventos_turno: list[RegistroAuditoriaPrivacidad],
    ) -> str:
        def _reemplazar(match: re.Match[str]) -> str:
            valor = match.group(0)
            contadores[regla] = contadores.get(regla, 0) + 1
            idx = contadores[regla]
            etiqueta = plantilla_etiqueta.format(n=idx)
            evento = RegistroAuditoriaPrivacidad(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                regla=regla,
                etiqueta=etiqueta,
                origen=origen,
                hmac_sha256=self._generar_hmac(regla, valor),
            )
            eventos_turno.append(evento)
            return etiqueta

        return patron.sub(_reemplazar, texto)

    def necesita_sanitizacion(self, texto: str) -> bool:
        """Indica si el texto requiere pasar por el sanitizador según el modo y contenido."""
        if not texto:
            return False
        if self.modo == "rgpd_estricto":
            return True
        return bool(
            _RE_BLOQUE_PRIVATE.search(texto)
            or _RE_CLAVE_PEM.search(texto)
            or _RE_TOKEN_API.search(texto)
        )

    def sanitizar_texto(self, texto: str, origen: str = "desconocido") -> ResultadoSanitizacion:
        """Redacta contenido sensible sin alterar fuera de alcance y genera registro HMAC."""
        if not texto:
            return ResultadoSanitizacion(
                texto_sanitizado=texto,
                total_redacciones=0,
                modo=self.modo,
                eventos_auditoria=[],
            )

        contadores: dict[str, int] = {}
        eventos_turno: list[RegistroAuditoriaPrivacidad] = []
        actual = texto

        reglas_base: list[tuple[str, re.Pattern[str], str]] = [
            ("bloque_private", _RE_BLOQUE_PRIVATE, "[BLOQUE_PRIVADO_OMITIDO]"),
            ("clave_privada_pem", _RE_CLAVE_PEM, "[SECRETO_REDACTADO_{n}]"),
            ("token_api", _RE_TOKEN_API, "[SECRETO_REDACTADO_{n}]"),
        ]
        for regla, patron, plantilla in reglas_base:
            actual = self._aplicar_regla(
                actual, regla, patron, plantilla, origen, contadores, eventos_turno
            )

        if self.modo == "rgpd_estricto":
            reglas_rgpd: list[tuple[str, re.Pattern[str], str]] = [
                ("rgpd_email", _RE_RGPD_EMAIL, "[EMAIL_REDACTADO_{n}]"),
                ("rgpd_iban", _RE_RGPD_IBAN, "[IBAN_REDACTADO_{n}]"),
                ("rgpd_dni_nie", _RE_RGPD_DNI_NIE, "[ID_DOC_REDACTADO_{n}]"),
                ("rgpd_ip_v4", _RE_RGPD_IPV4, "[IP_REDACTADA_{n}]"),
                ("rgpd_telefono", _RE_RGPD_TELEFONO, "[TEL_REDACTADO_{n}]"),
            ]
            for regla, patron, plantilla in reglas_rgpd:
                actual = self._aplicar_regla(
                    actual, regla, patron, plantilla, origen, contadores, eventos_turno
                )

        if eventos_turno:
            self.historial_auditoria.extend(eventos_turno)
            if self.ruta_log_auditoria is not None:
                self.ruta_log_auditoria.parent.mkdir(parents=True, exist_ok=True)
                with open(self.ruta_log_auditoria, "a", encoding="utf-8") as f_log:
                    for ev in eventos_turno:
                        f_log.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")

        return ResultadoSanitizacion(
            texto_sanitizado=actual,
            total_redacciones=len(eventos_turno),
            modo=self.modo,
            eventos_auditoria=eventos_turno,
        )
