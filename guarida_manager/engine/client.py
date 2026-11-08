import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class ErrorInferenciaOffline(Exception):
    """Excepcion base para errores de comunicacion con el motor local de inferencia."""
    pass


class ClienteLlamaOffline:
    """Cliente HTTP offline para interactuar con llama-server usando exclusivamente la libreria estandar."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8083,
        timeout: float = 60.0,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.api_key = api_key
        if base_url:
            self.base_url = base_url.rstrip("/")
        else:
            self.base_url = f"http://{host}:{port}"

    def _solicitud_http(
        self,
        endpoint: str,
        metodo: str = "GET",
        datos: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        tiempo_espera = timeout or self.timeout

        cuerpo_bytes = None
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if datos is not None:
            cuerpo_bytes = json.dumps(datos).encode("utf-8")
            headers["Content-Type"] = "application/json"

        peticion = urllib.request.Request(
            url,
            data=cuerpo_bytes,
            headers=headers,
            method=metodo,
        )

        try:
            with urllib.request.urlopen(peticion, timeout=tiempo_espera) as respuesta:
                codigo = respuesta.getcode()
                cuerpo = respuesta.read().decode("utf-8")
                if not cuerpo.strip():
                    return {"status_code": codigo}
                try:
                    resultado = json.loads(cuerpo)
                    if isinstance(resultado, dict):
                        resultado.setdefault("status_code", codigo)
                    return resultado
                except json.JSONDecodeError:
                    return {"status_code": codigo, "raw_response": cuerpo}
        except urllib.error.HTTPError as e:
            cuerpo_err = ""
            try:
                cuerpo_err = e.read().decode("utf-8")
            except Exception:
                pass
            raise ErrorInferenciaOffline(f"Error HTTP {e.code} en {endpoint}: {cuerpo_err}") from e
        except urllib.error.URLError as e:
            raise ErrorInferenciaOffline(f"No se pudo conectar con el servidor local en {url}: {e.reason}") from e
        except TimeoutError as e:
            raise ErrorInferenciaOffline(f"Tiempo de espera agotado ({tiempo_espera}s) en {endpoint}") from e

    def esta_disponible(self, timeout: float = 2.0) -> bool:
        """Verifica de forma rapida si el servidor esta vivo y responde."""
        try:
            salud = self.obtener_salud(timeout=timeout)
            # En llama-server /health devuelve status: "ok" o "loading model" (HTTP 503)
            return salud.get("status") == "ok" or salud.get("status_code") == 200
        except Exception:
            return False

    def obtener_salud(self, timeout: Optional[float] = None) -> dict[str, Any]:
        """Consulta el endpoint /health del servidor."""
        return self._solicitud_http("/health", metodo="GET", timeout=timeout)

    def obtener_slots(self, timeout: Optional[float] = None) -> list[dict[str, Any]]:
        """Consulta el endpoint /slots para ver el estado de slots de contexto y memoria."""
        respuesta = self._solicitud_http("/slots", metodo="GET", timeout=timeout)
        if isinstance(respuesta, list):
            return respuesta
        # Si devuelve un envoltorio con lista
        return respuesta.get("slots", [])

    def completar_chat(
        self,
        mensajes: list[dict[str, str]],
        temperatura: float = 0.2,
        top_p: float = 0.95,
        max_tokens: int = 2048,
        stream: bool = False,
        json_mode: bool = False,
        stop: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Genera una respuesta de chat usando el endpoint /v1/chat/completions compatible OpenAI."""
        payload: dict[str, Any] = {
            "messages": mensajes,
            "temperature": temperatura,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stop:
            payload["stop"] = stop
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._solicitud_http("/v1/chat/completions", metodo="POST", datos=payload)

    def completar_texto(
        self,
        prompt: str,
        n_predict: int = 512,
        temperatura: float = 0.2,
        top_p: float = 0.95,
        stop: Optional[list[str]] = None,
        cache_prompt: bool = False,
        seed: Optional[int] = None,
        ignore_eos: bool = False,
        stream: bool = False,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Genera completado de texto crudo mediante el endpoint nativo /completion de llama.cpp."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "n_predict": n_predict,
            "temperature": temperatura,
            "top_p": top_p,
            "cache_prompt": cache_prompt,
            "ignore_eos": ignore_eos,
            "stream": stream,
        }
        if seed is not None:
            payload["seed"] = seed
        if stop:
            payload["stop"] = stop
        payload.update(extra_kwargs)

        return self._solicitud_http("/completion", metodo="POST", datos=payload)

    def medir_ttft_streaming(
        self,
        prompt: str,
        seed: int = 42,
        timeout: float = 60.0,
    ) -> float:
        """Mide en milisegundos el tiempo hasta el primer token emitido (TTFT) mediante streaming."""
        import time

        url = f"{self.base_url}/completion"
        payload = {
            "prompt": prompt,
            "n_predict": 16,
            "temperature": 0.0,
            "cache_prompt": False,
            "seed": seed,
            "stream": True,
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        peticion = urllib.request.Request(url, data=cuerpo, headers=headers, method="POST")
        inicio = time.perf_counter()
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            for linea in resp:
                linea_str = linea.decode("utf-8", errors="replace").strip()
                if linea_str.startswith("data:"):
                    contenido_json = linea_str[5:].strip()
                    if contenido_json and contenido_json != "[DONE]":
                        ttft_ms = (time.perf_counter() - inicio) * 1000.0
                        return ttft_ms
        return (time.perf_counter() - inicio) * 1000.0

    def tokenizar(self, contenido: str) -> list[int]:
        """Convierte una cadena de texto a su lista exacta de IDs de tokens mediante /tokenize."""
        payload = {"content": contenido}
        res = self._solicitud_http("/tokenize", metodo="POST", datos=payload)
        tokens = res.get("tokens", [])
        return tokens

    def detokenizar(self, tokens: list[int]) -> str:
        """Reconstruye el texto original a partir de una lista de IDs de tokens mediante /detokenize."""
        payload = {"tokens": tokens}
        res = self._solicitud_http("/detokenize", metodo="POST", datos=payload)
        return res.get("content", "")

    def calcular_embedding(self, contenido: str) -> list[float]:
        """Genera el vector de embedding para una cadena de texto mediante /embedding."""
        def _aplanar(v: Any) -> list[float]:
            while isinstance(v, list) and v and isinstance(v[0], list):
                v = v[0]
            if isinstance(v, list):
                return [float(x) for x in v if isinstance(x, (int, float))]
            return []

        payload = {"content": contenido}
        res = self._solicitud_http("/embedding", metodo="POST", datos=payload)
        if isinstance(res, list):
            if not res:
                return []
            primer = res[0]
            if isinstance(primer, (int, float)):
                return _aplanar(res)
            if isinstance(primer, dict):
                return _aplanar(primer.get("embedding", []))
            if isinstance(primer, list):
                return _aplanar(primer)
            return []
        if isinstance(res, dict):
            if "embedding" in res:
                return _aplanar(res.get("embedding"))
            datos = res.get("data")
            if isinstance(datos, list) and datos and isinstance(datos[0], dict):
                return _aplanar(datos[0].get("embedding", []))
        return []
