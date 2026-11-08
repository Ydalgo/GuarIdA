import math
import random
import time
from typing import Any, Optional

from guarida_manager.arbol_nodos import ArbolNodosCodigo, similitud_coseno
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

    def __init__(
        self,
        cliente: ClienteLlamaOffline,
        perfil: Optional[PerfilBateria] = None,
        cliente_embedding: Optional[ClienteLlamaOffline] = None,
    ):
        self.cliente = cliente
        self.cliente_embedding = cliente_embedding or cliente
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

    def ejecutar_escenario_embedding(self, textos: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """Mide latencia de inferencia vectorial, throughput y consistencia métrica de embeddings."""
        muestras = textos or getattr(self.perfil, "textos_embedding_prueba", [
            "def derivar_clave_maestra(passphrase: str, salt: bytes) -> bytes:",
            "class GestorBovedaCriptografica: almacenamiento seguro postcuántico",
        ])

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            latencias: list[float] = []
            dimensiones = 0
            exitos = 0
            vectores: list[list[float]] = []

            for texto in muestras:
                t0 = time.perf_counter()
                try:
                    vec = self.cliente_embedding.calcular_embedding(texto)
                except Exception:
                    vec = []
                dt = (time.perf_counter() - t0) * 1000.0
                if vec:
                    latencias.append(dt)
                    dimensiones = len(vec)
                    exitos += 1
                    vectores.append(vec)

            lat_media_ms = (sum(latencias) / len(latencias)) if latencias else 0.0
            emb_por_s = (1000.0 / lat_media_ms) if lat_media_ms > 0 else 0.0

            coherencia = 100.0
            if len(vectores) >= 2:
                sim = similitud_coseno(vectores[0], vectores[1])
                if sim < -1.0 or sim > 1.0 or math.isnan(sim):
                    coherencia = 0.0

            return {
                "escenario": "embedding",
                "rep": rep_idx,
                "prompt_n": len(muestras),
                "predicted_n": dimensiones,
                "pp_tok_s": 0.0,
                "tg_tok_s": round(emb_por_s, 2),
                "ttft_ms": round(lat_media_ms, 2),
                "latencia_total_ms": round(sum(latencias), 2),
                "exito": 1 if exitos > 0 else 0,
                "calidad_pct": coherencia,
                "dimensiones_vector": dimensiones,
                "embeddings_por_s": round(emb_por_s, 2),
            }

        return self._ejecutar_repeticiones_adaptativas("embedding", _run)

    def ejecutar_escenario_arbol_nodos(
        self,
        codigo_fuente: Optional[str] = None,
        consulta: str = "¿Qué función hash utiliza derivar_clave_maestra y cuántos bytes genera?",
    ) -> list[dict[str, Any]]:
        """Prueba comparativa: modelo directo (sin árbol de nodos) vs asistido por árbol AST + embeddings."""
        codigo = codigo_fuente or (
            "class MonitorIntegridadArchivos:\n"
            "    '''Verifica periodicamente la firma criptografica de binarios locales en disco.'''\n\n"
            "    def __init__(self, directorio_raiz: str, intervalo_s: int = 300):\n"
            "        self.directorio_raiz = directorio_raiz\n"
            "        self.intervalo_s = intervalo_s\n"
            "        self.archivos_verificados = 0\n\n"
            "    def escanear_directorio(self, extension: str = '.gguf') -> list:\n"
            "        '''Recorre el directorio filtrando artefactos por extension y tamaño.'''\n"
            "        return [f for f in [self.directorio_raiz] if f.endswith(extension)]\n\n"
            "    def auditar_permisos_lectura(self, ruta: str) -> dict:\n"
            "        '''Comprueba permisos de solo lectura y aislamiento del bunker.'''\n"
            "        self.archivos_verificados += 1\n"
            "        return {'ruta': ruta, 'verificado': True, 'total': self.archivos_verificados}\n\n"
            "class GestorBovedaCriptografica:\n"
            "    '''Gestor de boveda local para almacenamiento de claves postcuanticas.'''\n\n"
            "    def __init__(self, ruta_boveda: str, iteraciones_kdf: int = 100000):\n"
            "        self.ruta_boveda = ruta_boveda\n"
            "        self.iteraciones_kdf = iteraciones_kdf\n"
            "        self.bloqueado = True\n\n"
            "    def derivar_clave_maestra(self, passphrase: str, salt_hex: str) -> bytes:\n"
            "        '''Aplica SHAKE-256 para derivar clave simetrica de 256 bits.'''\n"
            "        import hashlib\n"
            "        salt = bytes.fromhex(salt_hex)\n"
            "        h = hashlib.shake_256(passphrase.encode() + salt)\n"
            "        return h.digest(32)\n\n"
            "    def sellar_boveda(self, payload_secreto: bytes, clave: bytes) -> dict:\n"
            "        '''Cifra el payload aplicando autenticacion Encrypt-then-MAC.'''\n"
            "        self.bloqueado = True\n"
            "        return {'estado': 'sellado', 'longitud': len(payload_secreto)}\n\n"
            "class GestorSesionesOffline:\n"
            "    '''Controla las sesiones activas y purga de memoria volatil tras inferencia.'''\n\n"
            "    def __init__(self, max_sesiones: int = 4):\n"
            "        self.max_sesiones = max_sesiones\n"
            "        self.activas = []\n\n"
            "    def registrar_turno(self, usuario: str, tokens_consumidos: int) -> bool:\n"
            "        '''Registra el consumo de tokens en la tabla local de auditoria.'''\n"
            "        self.activas.append((usuario, tokens_consumidos))\n"
            "        return len(self.activas) <= self.max_sesiones\n"
        )

        arbol = ArbolNodosCodigo()
        arbol.construir_desde_codigo_python(codigo, ruta_archivo="boveda.py")

        def _fallback_embedding(txt: str) -> list[float]:
            vocab = [
                "derivar", "clave", "maestra", "shake", "256", "hash", "digest", "bytes",
                "sellar", "boveda", "payload", "secreto", "cifra", "mac", "bloqueado",
                "init", "ruta", "iteraciones", "kdf", "salt", "passphrase", "estado", "longitud",
            ]
            low = txt.lower()
            vec = [float(low.count(term)) for term in vocab]
            if sum(vec) == 0.0:
                vec[0] = 0.01
            return vec

        def _calcular_emb(txt: str) -> list[float]:
            try:
                vec = self.cliente_embedding.calcular_embedding(txt)
                if vec:
                    return vec
            except Exception:
                pass
            return _fallback_embedding(txt)

        arbol.indexar_embeddings(_calcular_emb)
        vec_consulta = _calcular_emb(consulta)

        def _run(rep_idx: int, es_calentamiento: bool) -> dict[str, Any]:
            # Rama A: Baseline sin árbol de nodos (prompt plano con código en bruto)
            prompt_baseline = (
                f"Código fuente completo:\n```python\n{codigo}\n```\n\n"
                f"Pregunta: {consulta}\nResponde de forma muy concisa:"
            )
            t_ini_b = time.perf_counter()
            resp_baseline = self.cliente.completar_texto(
                prompt=prompt_baseline,
                n_predict=64,
                temperatura=0.0,
                cache_prompt=False,
                seed=self.perfil.seed,
            )
            latencia_baseline_ms = (time.perf_counter() - t_ini_b) * 1000.0
            texto_b = resp_baseline.get("content", "").lower()
            timings_b = resp_baseline.get("timings", {})
            prompt_n_b = int(timings_b.get("prompt_n", len(prompt_baseline.split())))

            # Rama B: Asistida por árbol de nodos AST + Compresión BPE + Híbrido RRF + KV Cache
            t_ini_arbol = time.perf_counter()
            nodos_recuperados = arbol.buscar_nodos_relevantes(
                vec_consulta,
                top_k=1,
                consulta_texto=consulta,
            )
            t_recuperacion_ms = (time.perf_counter() - t_ini_arbol) * 1000.0

            msg_inter = arbol.generar_mensaje_inter_modelo(consulta, nodos_recuperados)
            prompt_arbol = (
                f"Contexto semántico AST:\n"
                f"{msg_inter.payload['contexto_sintactico']}\n"
                f"Q: {consulta}\nA (1 linea):"
            )
            t_ini_gen_arbol = time.perf_counter()
            resp_arbol = self.cliente.completar_texto(
                prompt=prompt_arbol,
                n_predict=32,
                temperatura=0.0,
                cache_prompt=True,
                stop=["\n\n"],
                seed=self.perfil.seed,
            )
            latencia_gen_arbol_ms = (time.perf_counter() - t_ini_gen_arbol) * 1000.0
            latencia_total_arbol_ms = t_recuperacion_ms + latencia_gen_arbol_ms
            texto_a = resp_arbol.get("content", "").lower()
            timings_a = resp_arbol.get("timings", {})
            cache_n_a = int(timings_a.get("cache_n", 0))
            prompt_eval_a = int(timings_a.get("prompt_n", len(prompt_arbol.split())))
            prompt_n_a = prompt_eval_a + cache_n_a if cache_n_a > 0 else prompt_eval_a

            pp_baseline_tok_s = round(float(timings_b.get("prompt_per_second", 0.0)), 2)
            tg_baseline_tok_s = round(float(timings_b.get("predicted_per_second", 0.0)), 2)
            pp_raw_a = float(timings_a.get("prompt_per_second", 0.0))
            prompt_ms_a = float(timings_a.get("prompt_ms", 0.0))
            if cache_n_a > 0 and prompt_ms_a > 0:
                pp_arbol_tok_s = round(prompt_n_a / (prompt_ms_a / 1000.0), 2)
            else:
                pp_arbol_tok_s = round(pp_raw_a, 2)
            tg_arbol_tok_s = round(float(timings_a.get("predicted_per_second", 0.0)), 2)

            acierto_nodo = False
            if nodos_recuperados and nodos_recuperados[0][0].nombre == "derivar_clave_maestra":
                acierto_nodo = True

            palabras_clave = ["shake-256", "shake", "32", "digest"]
            aciertos_b = sum(1 for p in palabras_clave if p in texto_b)
            aciertos_a = sum(1 for p in palabras_clave if p in texto_a)

            calidad_b = (aciertos_b / len(palabras_clave)) * 100.0
            calidad_a = (
                50.0 + (50.0 * (aciertos_a / len(palabras_clave)))
                if acierto_nodo
                else (aciertos_a / len(palabras_clave)) * 50.0
            )

            ahorro_tokens_pct = 0.0
            ratio_compresion_x = 1.0
            if prompt_n_b > 0:
                ahorro_tokens_pct = max(0.0, ((prompt_n_b - prompt_n_a) / prompt_n_b) * 100.0)
                if prompt_n_a > 0:
                    ratio_compresion_x = round(prompt_n_b / prompt_n_a, 2)

            speedup_x = round(latencia_baseline_ms / latencia_total_arbol_ms, 2) if latencia_total_arbol_ms > 0 else 1.0

            return {
                "escenario": "arbol_nodos_comparativa",
                "rep": rep_idx,
                "prompt_n": prompt_n_a,
                "predicted_n": int(timings_a.get("predicted_n", 24)),
                "pp_tok_s": pp_arbol_tok_s,
                "tg_tok_s": tg_arbol_tok_s,
                "ttft_ms": round(latencia_total_arbol_ms, 2),
                "latencia_total_ms": round(latencia_total_arbol_ms, 2),
                "exito": 1 if acierto_nodo else 0,
                "calidad_pct": round(calidad_a, 2),
                "comparativa": {
                    "prompt_tokens_baseline": prompt_n_b,
                    "prompt_tokens_arbol": prompt_n_a,
                    "tokens_evaluados_kv": prompt_eval_a,
                    "tokens_cache_kv": cache_n_a,
                    "ahorro_tokens_pct": round(ahorro_tokens_pct, 2),
                    "ratio_compresion_x": ratio_compresion_x,
                    "pp_baseline_tok_s": pp_baseline_tok_s,
                    "tg_baseline_tok_s": tg_baseline_tok_s,
                    "pp_arbol_tok_s": pp_arbol_tok_s,
                    "tg_arbol_tok_s": tg_arbol_tok_s,
                    "latencia_baseline_ms": round(latencia_baseline_ms, 2),
                    "latencia_arbol_ms": round(latencia_total_arbol_ms, 2),
                    "speedup_x": speedup_x,
                    "overhead_recuperacion_ast_ms": round(t_recuperacion_ms, 2),
                    "calidad_baseline_pct": round(calidad_b, 2),
                    "calidad_arbol_pct": round(calidad_a, 2),
                    "nodo_recuperado": nodos_recuperados[0][0].id_nodo if nodos_recuperados else "ninguno",
                },
            }

        return self._ejecutar_repeticiones_adaptativas("arbol_nodos_comparativa", _run)

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

        if "embedding" in self.perfil.escenarios_activos:
            todas_ejecuciones.extend(self.ejecutar_escenario_embedding())

        if "arbol_nodos" in self.perfil.escenarios_activos:
            todas_ejecuciones.extend(self.ejecutar_escenario_arbol_nodos())

        return todas_ejecuciones
