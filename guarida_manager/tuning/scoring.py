from typing import Any, Optional

from guarida_manager.tuning.bateria import calcular_estadisticas_serie


class EvaluadorScoring:
    """Evalúa, puntúa y selecciona la configuración óptima según restricciones y objetivo."""

    PESOS_OBJETIVOS = {
        "chat": {"peso_tg": 0.55, "peso_ttft": 0.30, "peso_pp": 0.15, "penalizacion_mem": 0.05},
        "batch": {"peso_tg": 0.35, "peso_ttft": 0.05, "peso_pp": 0.60, "penalizacion_mem": 0.02},
        "agente_contexto_largo": {"peso_tg": 0.40, "peso_ttft": 0.20, "peso_pp": 0.25, "bonus_ctx": 0.15},
        "equilibrado": {"peso_tg": 0.45, "peso_ttft": 0.25, "peso_pp": 0.25, "penalizacion_mem": 0.05},
    }

    @classmethod
    def extraer_metricas_resumen(cls, ejecuciones: list[dict[str, Any]]) -> dict[str, Any]:
        """Agrupa y calcula estadísticas agregadas para PP, TG y TTFT a partir de ejecuciones crudas."""
        validas = [e for e in ejecuciones if not e.get("es_calentamiento") and e.get("exito", 0) == 1]
        if not validas:
            return {
                "tg_stats": calcular_estadisticas_serie([]),
                "pp_stats": calcular_estadisticas_serie([]),
                "ttft_stats": calcular_estadisticas_serie([]),
                "exito_ratio": 0.0,
                "calidad_media": 0.0,
            }

        tg_vals = [e["tg_tok_s"] for e in validas if e.get("tg_tok_s", 0) > 0]
        pp_vals = [e["pp_tok_s"] for e in validas if e.get("pp_tok_s", 0) > 0]
        ttft_vals = [e["ttft_ms"] for e in validas if e.get("ttft_ms", 0) > 0]
        calidades = [e.get("calidad_pct", 100.0) for e in validas]

        total_no_calentamiento = [e for e in ejecuciones if not e.get("es_calentamiento")]
        exito_ratio = len(validas) / len(total_no_calentamiento) if total_no_calentamiento else 0.0
        calidad_media = sum(calidades) / len(calidades) if calidades else 100.0

        return {
            "tg_stats": calcular_estadisticas_serie(tg_vals),
            "pp_stats": calcular_estadisticas_serie(pp_vals),
            "ttft_stats": calcular_estadisticas_serie(ttft_vals),
            "exito_ratio": round(exito_ratio, 2),
            "calidad_media": round(calidad_media, 2),
        }

    @classmethod
    def calcular_score(
        cls,
        ejecuciones: list[dict[str, Any]],
        memoria_mb: float,
        ctx_size: int,
        objetivo: str = "equilibrado",
    ) -> float:
        """Calcula el score numérico normalizado según los pesos del objetivo."""
        metricas = cls.extraer_metricas_resumen(ejecuciones)
        if metricas["exito_ratio"] < 1.0 or metricas["calidad_media"] < 80.0:
            return 0.0

        tg = metricas["tg_stats"]["mediana"]
        pp = metricas["pp_stats"]["mediana"]
        ttft = metricas["ttft_stats"]["mediana"]

        pesos = cls.PESOS_OBJETIVOS.get(objetivo.lower(), cls.PESOS_OBJETIVOS["equilibrado"])

        # Puntuaciones componentes
        componente_tg = tg
        componente_pp = pp * 0.1
        componente_ttft = (1000.0 / max(50.0, ttft)) * 20.0 if ttft > 0 else 0.0
        factor_memoria = 1.0 - min(0.3, (memoria_mb / 32768.0) * pesos.get("penalizacion_mem", 0.05))
        factor_ctx = (ctx_size / 4096.0) if "bonus_ctx" in pesos else 1.0

        score_base = (
            componente_tg * pesos.get("peso_tg", 0.45)
            + componente_pp * pesos.get("peso_pp", 0.25)
            + componente_ttft * pesos.get("peso_ttft", 0.25)
        ) * factor_memoria * factor_ctx

        return round(max(0.0, score_base), 2)

    @classmethod
    def comparar_significancia(
        cls,
        res_a: dict[str, Any],
        res_b: dict[str, Any],
    ) -> int:
        """Determina si la config A es significativamente mejor (1), peor (-1) o equivalente (0) a B usando IC 95%."""
        stats_a = cls.extraer_metricas_resumen(res_a.get("ejecuciones", []))["tg_stats"]
        stats_b = cls.extraer_metricas_resumen(res_b.get("ejecuciones", []))["tg_stats"]

        # Solapamiento de intervalos de confianza
        inf_a, sup_a = stats_a["ic_inf"], stats_a["ic_sup"]
        inf_b, sup_b = stats_b["ic_inf"], stats_b["ic_sup"]

        if inf_a > sup_b:
            return 1
        if inf_b > sup_a:
            return -1

        # En caso de solapamiento (empate estadístico en velocidad), desempata por menor memoria
        mem_a = res_a.get("metricas_memoria", {}).get("ram_pico_mb", 0) + res_a.get("metricas_memoria", {}).get("vram_pico_mb", 0)
        mem_b = res_b.get("metricas_memoria", {}).get("ram_pico_mb", 0) + res_b.get("metricas_memoria", {}).get("vram_pico_mb", 0)
        if mem_a < mem_b:
            return 1
        if mem_b < mem_a:
            return -1
        return 0

    @classmethod
    def calcular_frente_pareto(cls, lista_resultados: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Calcula el frente de Pareto multiobjetivo (maximizar velocidad TG, minimizar memoria)."""
        frente: list[dict[str, Any]] = []
        for candidato in lista_resultados:
            if candidato.get("estado") != "ok":
                continue
            dominado = False
            for otro in lista_resultados:
                if otro.get("estado") != "ok" or otro is candidato:
                    continue
                # Si 'otro' es estrictamente mejor o igual en velocidad y menor en memoria
                tg_cand = candidato.get("metricas", {}).get("tg_mediana", 0)
                tg_otro = otro.get("metricas", {}).get("tg_mediana", 0)
                mem_cand = candidato.get("mem_total_mb", 999999)
                mem_otro = otro.get("mem_total_mb", 999999)

                if (tg_otro >= tg_cand and mem_otro <= mem_cand) and (tg_otro > tg_cand or mem_otro < mem_cand):
                    dominado = True
                    break
            if not dominado:
                frente.append(candidato)
        return frente
