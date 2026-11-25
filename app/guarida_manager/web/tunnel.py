"""Gestor de túnel HTTPS saliente (cloudflared) para acceso remoto sin router ni dominio."""

import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.downloader.tools import GestorHerramientasBunker

_REGEX_TRYCLOUDFLARE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class GestorTunelRemoto:
    """Administra el ciclo de vida de un túnel cloudflared Quick Tunnel (Apache-2.0)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proceso: Optional[subprocess.Popen[str]] = None
        self._url_publica: Optional[str] = None
        self._token_acceso: Optional[str] = None
        self._puerto_local: Optional[int] = None
        self._error_ultimo: Optional[str] = None

    def esta_activo(self) -> bool:
        with self._lock:
            return self._proceso is not None and self._proceso.poll() is None

    def estado(self) -> dict[str, Any]:
        with self._lock:
            activo = self._proceso is not None and self._proceso.poll() is None
            url = self._url_publica if activo else None
            token = self._token_acceso if activo else None
            return {
                "activo": activo,
                "url_publica": url,
                "token_acceso": token,
                "url_con_token": f"{url}/?token={token}" if (url and token) else None,
                "puerto_local": self._puerto_local if activo else None,
                "pid": self._proceso.pid if (activo and self._proceso) else None,
                "error": self._error_ultimo,
            }

    def iniciar(
        self,
        puerto_local: int,
        timeout_segundos: float = 25.0,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> dict[str, Any]:
        """Descarga cloudflared si falta e inicia un túnel HTTPS apuntando a 127.0.0.1:puerto_local."""
        with self._lock:
            if self._proceso is not None and self._proceso.poll() is None:
                return {
                    "activo": True,
                    "url_publica": self._url_publica,
                    "token_acceso": self._token_acceso,
                    "url_con_token": (
                        f"{self._url_publica}/?token={self._token_acceso}"
                        if (self._url_publica and self._token_acceso)
                        else None
                    ),
                    "puerto_local": self._puerto_local,
                    "pid": self._proceso.pid,
                    "error": None,
                }
            self._error_ultimo = None

        ruta_bin = GestorHerramientasBunker.resolver_ruta_ejecutable("cloudflared")
        if not ruta_bin:
            ruta_bin = GestorHerramientasBunker.descargar_y_desplegar(
                "cloudflared",
                callback_progreso=callback_progreso,
            )

        cmd = [
            str(Path(ruta_bin)),
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{int(puerto_local)}",
        ]
        proceso = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        evento_url = threading.Event()
        url_encontrada: list[str] = []
        ultimas_lineas: list[str] = []

        def _leer_salida() -> None:
            if proceso.stdout is None:
                return
            try:
                for linea in proceso.stdout:
                    texto = linea.strip()
                    if texto:
                        ultimas_lineas.append(texto)
                        if len(ultimas_lineas) > 20:
                            ultimas_lineas.pop(0)
                    match = _REGEX_TRYCLOUDFLARE.search(linea)
                    if match and not url_encontrada:
                        url_encontrada.append(match.group(0))
                        evento_url.set()
            except Exception:
                pass
            finally:
                evento_url.set()

        hilo_lector = threading.Thread(target=_leer_salida, daemon=True)
        hilo_lector.start()

        deadline = time.monotonic() + timeout_segundos
        while time.monotonic() < deadline:
            if url_encontrada:
                break
            if proceso.poll() is not None:
                break
            evento_url.wait(timeout=0.2)

        if not url_encontrada:
            try:
                proceso.terminate()
                proceso.wait(timeout=2)
            except Exception:
                try:
                    proceso.kill()
                except Exception:
                    pass
            detalle = " | ".join(ultimas_lineas[-3:]) if ultimas_lineas else "sin salida"
            with self._lock:
                self._error_ultimo = f"No se obtuvo URL de trycloudflare.com ({detalle})"
            raise RuntimeError(self._error_ultimo)

        token = secrets.token_urlsafe(12)
        with self._lock:
            self._proceso = proceso
            self._url_publica = url_encontrada[0]
            self._token_acceso = token
            self._puerto_local = int(puerto_local)
            self._error_ultimo = None

        return self.estado()

    def detener(self) -> dict[str, Any]:
        """Detiene el proceso de cloudflared si está en ejecución."""
        with self._lock:
            proc = self._proceso
            self._proceso = None
            self._url_publica = None
            self._token_acceso = None
            self._puerto_local = None

        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return self.estado()
