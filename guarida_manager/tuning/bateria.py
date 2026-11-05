import math
import random
import time
from typing import Any, Optional

from guarida_manager.engine.client import ClienteLlamaOffline
from guarida_manager.tuning.perfiles import PerfilBateria

# Semilla determinista de texto estructurado para construir prompts
TEXTO_BASE_PROMPT = (
    "El análisis de sistemas distribuidos y modelos de lenguaje locales requiere "
    "un control estricto de concurrencia, memoria compartida y latencias deterministas. "
    "En arquitecturas aisladas tipo búnker, la inferencia sin red debe garantizar "
    "reproducibilidad estadística, resistencia térmica y coherencia semántica. "
    "Las operaciones de prefill y decoding saturan diferentes componentes del silicio, "
    "donde el ancho de banda de memoria define el cuello de botella principal. "
)


def generar_prompt_tokens_exactos(
    cliente: ClienteLlamaOffline,
    n_tokens_objetivo: int,
) -> str:
    """Genera un texto determinista con la cantidad exacta o muy aproximada de tokens mediante /tokenize."""
    repeticiones = max(1, (n_tokens_objetivo // 40) + 1)
    texto = (TEXTO_BASE_PROMPT * repeticiones)[: n_tokens_objetivo * 6]

    try:
        tokens = cliente.tokenizar(texto)
        if len(tokens) >= n_tokens_objetivo:
            tokens_cortados = tokens[:n_tokens_objetivo]
            texto_ajustado = cliente.detokenizar(tokens_cortados)
            return texto_ajustado
    except Exception:
        pass

    palabras = (TEXTO_BASE_PROMPT * repeticiones).split()
    return " ".join(palabras[: max(1, int(n_tokens_objetivo * 0.75))])


def calcular_intervalo_confianza_bootstrap(
    valores: list[float],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float]:
    """Calcula el intervalo de confianza empírico del 95% usando remuestreo bootstrap no paramétrico."""
    n = len(valores)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return valores[0], valores[0]

    rng = random.Random(seed)
    medias_remuestreadas: list[float] = []

    for _ in range(n_bootstrap):
        muestra = [rng.choice(valores) for _ in range(n)]
        medias_remuestreadas.append(sum(muestra) / n)

    medias_remuestreadas.sort()
    idx_inf = int(math.floor(n_bootstrap * (alpha / 2.0)))
    idx_sup = int(math.ceil(n_bootstrap * (1.0 - alpha / 2.0))) - 1

    return (
        round(medias_remuestreadas[max(0, idx_inf)], 2),
        round(medias_remuestreadas[min(n_bootstrap - 1, idx_sup)], 2),
    )


def calcular_estadisticas_serie(valores: list[float]) -> dict[str, float]:
    """Calcula media, mediana, p95, desviación típica y coeficiente de variación (CV%)."""
    if not valores:
        return {
            "media": 0.0, "mediana": 0.0, "p95": 0.0,
            "desv": 0.0, "cv_pct": 0.0, "ic_inf": 0.0, "ic_sup": 0.0,
        }

    n = len(valores)
    media = sum(valores) / n
    ordenados = sorted(valores)

    if n % 2 == 1:
        mediana = ordenados[n // 2]
    else:
        mediana = (ordenados[(n // 2) - 1] + ordenados[n // 2]) / 2.0

    idx_p95 = min(n - 1, max(0, int(math.ceil(0.95 * n)) - 1))
    p95 = ordenados[idx_p95]

    varianza = sum((x - media) ** 2 for x in valores) / (n - 1) if n > 1 else 0.0
    desv = math.sqrt(varianza)
    cv = (desv / media * 100.0) if media > 0 else 0.0

    ic_inf, ic_sup = calcular_intervalo_confianza_bootstrap(valores)

    return {
        "media": round(media, 2),
        "mediana": round(mediana, 2),
        "p95": round(p95, 2),
        "desv": round(desv, 2),
        "cv_pct": round(cv, 2),
        "ic_inf": ic_inf,
        "ic_sup": ic_sup,
    }


class BateriaEstresLlama:
    """Ejecutor de pruebas de estrés estadísticas, prefill/decode y calidad sobre llama-server."""

    def __init__(self, cliente: ClienteLlamaOffline, perfil: Optional[PerfilBateria] = None):
        self.cliente = cliente
        self.perfil = perfil or PerfilBateria(nombre="defecto", descripcion="Batería por defecto")

    def _ejecutar_repeticiones_adaptativas(
        self,
        escenario: str,
        funcion_ejecutar_una_rep: Any,
    ) -> list[dict[str, Any]]:
        """Aplica calentamientos descartados y repeticiones adaptativas hasta que CV < umbral o max reps."""
        resultados: list[dict[str, Any]] = []

        # 1. Calentamientos descartados
        for c in range(self.perfil.calentamientos_descartados):
            try:
                res = funcion_ejecutar_una_rep(rep_idx=c, es_calentamiento=True)
                res["es_calentamiento"] = True
                resultados.append(res)
            except Exception:
                pass
            time.sleep(self.perfil.enfriamiento_segundos)

        # 2. Repeticiones válidas
        metricas_clave: list[float] = []
        for r in range(self.perfil.repeticiones_max):
            try:
                res = funcion_ejecutar_una_rep(rep_idx=r + 1, es_calentamiento=False)
                res["es_calentamiento"] = False
                resultados.append(res)

                metrica_referencia = res.get("tg_tok_s") or res.get("pp_tok_s") or 0.0
                metricas_clave.append(metrica_referencia)

                # Si ya alcanzamos las repeticiones mínimas, chequear si CV < umbral
                if len(metricas_clave) >= self.perfil.repeticiones_min:
                    stats = calcular_estadisticas_serie(metricas_clave)
                    if stats["cv_pct"] <= self.perfil.umbral_cv_pct:
                        break
            except Exception as e:
                resultados.append({
                    "escenario": escenario,
                    "rep": r + 1,
                    "es_calentamiento": False,
                    "exito": 0,
                    "error": str(e),
                })

            time.sleep(self.perfil.enfriamiento_segundos)

        return resultados

    def ejecutar_escenario_pp(self, tokens_prompt: int) -> list[dict[str, Any]]:
        """Mide velocidad de prefill (procesamiento de prompt) con n_predict=1."""
        prompt = generar_prompt_tokens_exactos(self.cliente, tokens_prompt)

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            t0 = time.perf_counter()
            resp = self.cliente.completar_texto(
                prompt=prompt,
                n_predict=1,
                temperatura=0.0,
                cache_prompt=False,
                seed=self.perfil.seed,
            )
            latencia_ms = (time.perf_counter() - t0) * 1000.0

            timings = resp.get("timings", {})
            pp_tok_s = float(timings.get("prompt_per_second", 0.0))
            p_n = int(timings.get("prompt_n", tokens_prompt))

            if pp_tok_s == 0.0 and latencia_ms > 0:
                pp_tok_s = (p_n / (latencia_ms / 1000.0))

            return {
                "escenario": f"pp_{tokens_prompt}",
                "rep": rep_idx,
                "prompt_n": p_n,
                "predicted_n": 1,
                "pp_tok_s": round(pp_tok_s, 2),
                "tg_tok_s": 0.0,
                "ttft_ms": round(latencia_ms, 2),
                "latencia_total_ms": round(latencia_ms, 2),
                "exito": 1,
                "calidad_pct": 100.0,
            }

        return self._ejecutar_repeticiones_adaptativas(f"pp_{tokens_prompt}", _run)

    def ejecutar_escenario_tg(self, predict_n: int) -> list[dict[str, Any]]:
        """Mide velocidad de decoding (generación sostenida de tokens) con prompt corto."""
        prompt_corto = "Explica los fundamentos de la computación cuántica de forma concisa:"

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            t0 = time.perf_counter()
            resp = self.cliente.completar_texto(
                prompt=prompt_corto,
                n_predict=predict_n,
                temperatura=0.0,
                cache_prompt=False,
                ignore_eos=True,
                seed=self.perfil.seed,
            )
            latencia_ms = (time.perf_counter() - t0) * 1000.0

            timings = resp.get("timings", {})
            tg_tok_s = float(timings.get("predicted_per_second", 0.0))
            pred_n = int(timings.get("predicted_n", predict_n))

            if tg_tok_s == 0.0 and latencia_ms > 0:
                tg_tok_s = (pred_n / (latencia_ms / 1000.0))

            return {
                "escenario": f"tg_{predict_n}",
                "rep": rep_idx,
                "prompt_n": int(timings.get("prompt_n", 16)),
                "predicted_n": pred_n,
                "pp_tok_s": float(timings.get("prompt_per_second", 0.0)),
                "tg_tok_s": round(tg_tok_s, 2),
                "ttft_ms": round(float(timings.get("prompt_ms", latencia_ms)), 2),
                "latencia_total_ms": round(latencia_ms, 2),
                "exito": 1,
                "calidad_pct": 100.0,
            }

        return self._ejecutar_repeticiones_adaptativas(f"tg_{predict_n}", _run)

    def ejecutar_escenario_ttft(self, tokens_prompt: int = 2048) -> list[dict[str, Any]]:
        """Mide el tiempo transcurrido hasta emitir el primer token en streaming."""
        prompt = generar_prompt_tokens_exactos(self.cliente, tokens_prompt)

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            ttft_ms = self.cliente.medir_ttft_streaming(
                prompt=prompt,
                seed=self.perfil.seed,
                timeout=self.perfil.timeout_por_peticion_s,
            )
            return {
                "escenario": "ttft_2048",
                "rep": rep_idx,
                "prompt_n": tokens_prompt,
                "predicted_n": 1,
                "pp_tok_s": 0.0,
                "tg_tok_s": 0.0,
                "ttft_ms": round(ttft_ms, 2),
                "latencia_total_ms": round(ttft_ms, 2),
                "exito": 1,
                "calidad_pct": 100.0,
            }

        return self._ejecutar_repeticiones_adaptativas("ttft_2048", _run)

    def ejecutar_escenario_calidad(self) -> list[dict[str, Any]]:
        """Verifica la coherencia del modelo y formato JSON determinista."""
        prompt_json = (
            "Responde estrictamente con un JSON con formato: "
            '{"estado": "ok", "operacion": "suma", "resultado": 42}'
        )

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            t0 = time.perf_counter()
            resp = self.cliente.completar_texto(
                prompt=prompt_json,
                n_predict=64,
                temperatura=0.0,
                cache_prompt=False,
                seed=self.perfil.seed,
            )
            latencia_ms = (time.perf_counter() - t0) * 1000.0
            texto = resp.get("content", "").strip()

            es_json_valido = False
            calidad = 50.0
            if "{" in texto and "}" in texto:
                try:
                    import json
                    json_str = texto[texto.find("{") : texto.rfind("}") + 1]
                    data = json.loads(json_str)
                    if data.get("estado") == "ok":
                        es_json_valido = True
                        calidad = 100.0
                except Exception:
                    pass

            return {
                "escenario": "calidad_json",
                "rep": rep_idx,
                "prompt_n": 30,
                "predicted_n": 30,
                "pp_tok_s": 0.0,
                "tg_tok_s": 0.0,
                "ttft_ms": round(latencia_ms, 2),
                "latencia_total_ms": round(latencia_ms, 2),
                "exito": 1 if es_json_valido else 0,
                "calidad_pct": calidad,
            }

        return self._ejecutar_repeticiones_adaptativas("calidad_json", _run)

    def ejecutar_bateria_completa(self, ctx_size: int = 4096) -> list[dict[str, Any]]:
        """Ejecuta los escenarios parametrizados en el perfil de batería."""
        todas_ejecuciones: list[dict[str, Any]] = []

        if "pp" in self.perfil.escenarios_activos:
            for n_tokens in self.perfil.pp_tokens_lista:
                if n_tokens < ctx_size:
                    todas_ejecuciones.extend(self.ejecutar_escenario_pp(n_tokens))

        if "tg" in self.perfil.escenarios_activos:
            for n_pred in self.perfil.tg_predict_lista:
                todas_ejecuciones.extend(self.ejecutar_escenario_tg(n_pred))

        if "ttft" in self.perfil.escenarios_activos and ctx_size >= 2048:
            todas_ejecuciones.extend(self.ejecutar_escenario_ttft(2048))

        if "calidad" in self.perfil.escenarios_activos:
            todas_ejecuciones.extend(self.ejecutar_escenario_calidad())

        return todas_ejecuciones
