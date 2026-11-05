import csv
import json
from pathlib import Path
from typing import Any, Optional

from guarida_manager import DIRECTORIO_RAIZ_GUARIDA
from guarida_manager.cache import GestorCache
from guarida_manager.tuning.scoring import EvaluadorScoring

DIR_INFORMES = DIRECTORIO_RAIZ_GUARIDA / "informes"


class GeneradorInformesTuning:
    """Genera tablas visuales en consola, exporta informes en CSV/JSON y compara modelos."""

    def __init__(self, gestor_cache: Optional[GestorCache] = None, dir_salida: Optional[Path] = None):
        self.cache = gestor_cache or GestorCache()
        self.dir_salida = dir_salida or DIR_INFORMES
        self.dir_salida.mkdir(parents=True, exist_ok=True)

    def obtener_resumen_sesion(self, sesion_id: str) -> dict[str, Any]:
        with self.cache.sesion() as conn:
            sesion_row = conn.execute(
                "SELECT * FROM bench_sesiones WHERE id = ?;", (sesion_id,)
            ).fetchone()
            if not sesion_row:
                return {}

            configs = conn.execute(
                "SELECT * FROM bench_configs WHERE sesion_id = ? ORDER BY score DESC;", (sesion_id,)
            ).fetchall()

            resumen_configs = []
            for c in configs:
                c_dict = dict(c)
                c_dict["args"] = json.loads(c_dict["args_json"]) if c_dict.get("args_json") else {}
                ejecs = conn.execute(
                    "SELECT * FROM bench_ejecuciones WHERE config_id = ?;", (c["id"],)
                ).fetchall()
                ejecs_lista = [dict(e) for e in ejecs]
                c_dict["stats"] = EvaluadorScoring.extraer_metricas_resumen(ejecs_lista)
                resumen_configs.append(c_dict)

            return {
                "sesion": dict(sesion_row),
                "configs": resumen_configs,
            }

    def imprimir_tabla_consola(self, sesion_id: str, top_n: int = 5) -> None:
        datos = self.obtener_resumen_sesion(sesion_id)
        if not datos:
            print(f"[!] No se encontró información para la sesión '{sesion_id}'.")
            return

        sesion = datos["sesion"]
        configs = datos["configs"]

        print("\n" + "=" * 90)
        print(f"  INFORME DE AFINAMIENTO Y BENCHMARKING — SESIÓN {sesion_id}")
        print("=" * 90)
        print(f"Modelo:       {sesion['modelo_id']} (Build: {sesion['version_build']})")
        print(f"Hardware:     {sesion['hash_hardware'][:16]}... | Objetivo: {sesion['objetivo']}")
        print(f"Estado:       {sesion['estado'].upper()} (Inicio: {sesion['inicio']})")
        print("-" * 90)

        # Agrupar fallos
        fallos = [c for c in configs if c["estado"] != "ok"]
        if fallos:
            causas: dict[str, int] = {}
            for f in fallos:
                motivo = f.get("error_resumen") or f.get("estado")
                causas[motivo] = causas.get(motivo, 0) + 1
            print(f"Intentos fallidos/podados ({len(fallos)}):")
            for mot, cnt in causas.items():
                print(f"  - [{cnt}x] {mot}")
            print("-" * 90)

        exitosas = [c for c in configs if c["estado"] == "ok"]
        print(f"RANKING TOP-{min(top_n, len(exitosas))} DE CONFIGURACIONES ÓPTIMAS:")
        print(f"{'#':<3} {'NGL':<5} {'Ctx':<6} {'Batch/UB':<10} {'KV':<6} {'FA':<4} {'TG (tok/s)':<16} {'TTFT (ms)':<12} {'Mem(MB)':<9} {'Score':<7}")
        print("-" * 90)

        for idx, c in enumerate(exitosas[:top_n], start=1):
            args = c["args"]
            stats = c["stats"]
            tg = stats["tg_stats"]["mediana"]
            tg_ic = f"±{stats['tg_stats']['desv']}" if stats['tg_stats']['desv'] > 0 else ""
            tg_str = f"{tg:.1f} {tg_ic}"
            ttft = stats["ttft_stats"]["mediana"]
            mem_tot = c["ram_pico_mb"] + c["vram_pico_mb"]
            fa_str = "SÍ" if args.get("flash_attn") else "NO"

            print(
                f"{idx:<3} {args.get('n_gpu_layers', 0):<5} {args.get('ctx_size', 4096):<6} "
                f"{args.get('batch_size', 512)}/{args.get('ubatch_size', 512):<5} "
                f"{args.get('kv_cache_tipo', 'f16'):<6} {fa_str:<4} "
                f"{tg_str:<16} {ttft:<12.1f} {mem_tot:<9.1f} {c['score']:<7.2f}"
            )
        print("=" * 90 + "\n")

    def exportar_csv_y_json(self, sesion_id: str) -> tuple[Path, Path]:
        datos = self.obtener_resumen_sesion(sesion_id)
        if not datos:
            raise ValueError(f"Sesión no encontrada: {sesion_id}")

        ruta_json = self.dir_salida / f"informe_{sesion_id}.json"
        ruta_csv = self.dir_salida / f"informe_{sesion_id}.csv"

        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)

        with open(ruta_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "sesion_id", "modelo_id", "hash_hardware", "config_id", "etapa", "estado",
                "n_gpu_layers", "threads", "ctx_size", "batch_size", "ubatch_size", "kv_cache_tipo",
                "flash_attn", "tg_tok_s_mediana", "tg_tok_s_ic_inf", "tg_tok_s_ic_sup",
                "pp_tok_s_mediana", "ttft_ms_mediana", "ram_pico_mb", "vram_pico_mb", "score",
            ])
            for c in datos["configs"]:
                args = c["args"]
                stats = c["stats"]
                writer.writerow([
                    sesion_id,
                    datos["sesion"]["modelo_id"],
                    datos["sesion"]["hash_hardware"],
                    c["id"],
                    c["etapa"],
                    c["estado"],
                    args.get("n_gpu_layers", 0),
                    args.get("threads", 4),
                    args.get("ctx_size", 4096),
                    args.get("batch_size", 512),
                    args.get("ubatch_size", 512),
                    args.get("kv_cache_tipo", "f16"),
                    1 if args.get("flash_attn") else 0,
                    stats["tg_stats"]["mediana"],
                    stats["tg_stats"]["ic_inf"],
                    stats["tg_stats"]["ic_sup"],
                    stats["pp_stats"]["mediana"],
                    stats["ttft_stats"]["mediana"],
                    c["ram_pico_mb"],
                    c["vram_pico_mb"],
                    c["score"],
                ])

        return ruta_csv, ruta_json

    def comparar_sesiones(self, sesion_id_a: str, sesion_id_b: str) -> None:
        """Compara el desempeño entre dos sesiones (mismo o distinto modelo) en el mismo hardware."""
        datos_a = self.obtener_resumen_sesion(sesion_id_a)
        datos_b = self.obtener_resumen_sesion(sesion_id_b)

        if not datos_a or not datos_b:
            print("[!] Una o ambas sesiones no existen.")
            return

        s_a = datos_a["sesion"]
        s_b = datos_b["sesion"]

        if s_a["hash_hardware"] != s_b["hash_hardware"]:
            print("[ADVERTENCIA]: Las sesiones se ejecutaron en hardware diferente. La comparación de rendimiento no es equivalente.")

        if s_a["hash_perfil_bateria"] != s_b["hash_perfil_bateria"]:
            print("[ADVERTENCIA]: Los perfiles de batería son diferentes. Las métricas no son directamente comparables.")

        ganador_a = next((c for c in datos_a["configs"] if c["estado"] == "ok"), None)
        ganador_b = next((c for c in datos_b["configs"] if c["estado"] == "ok"), None)

        if not ganador_a or not ganador_b:
            print("[!] No se encontró configuración válida en alguna de las sesiones.")
            return

        tg_a = ganador_a["stats"]["tg_stats"]["mediana"]
        tg_b = ganador_b["stats"]["tg_stats"]["mediana"]
        delta_tg_pct = ((tg_b - tg_a) / tg_a * 100.0) if tg_a > 0 else 0.0

        ttft_a = ganador_a["stats"]["ttft_stats"]["mediana"]
        ttft_b = ganador_b["stats"]["ttft_stats"]["mediana"]
        delta_ttft_pct = ((ttft_b - ttft_a) / ttft_a * 100.0) if ttft_a > 0 else 0.0

        print("\n" + "=" * 70)
        print("  COMPARATIVA EMPÍRICA ENTRE MODELOS / SESIONES")
        print("=" * 70)
        print(f"Modelo A [{sesion_id_a[:8]}]: {s_a['modelo_id']}")
        print(f"Modelo B [{sesion_id_b[:8]}]: {s_b['modelo_id']}")
        print("-" * 70)
        print(f"Velocidad Generación (TG):  A = {tg_a:.1f} tok/s  vs  B = {tg_b:.1f} tok/s  (Delta: {delta_tg_pct:+.1f}%)")
        print(f"Latencia Primer Token (TTFT): A = {ttft_a:.1f} ms     vs  B = {ttft_b:.1f} ms     (Delta: {delta_ttft_pct:+.1f}%)")
        print(f"Score Global Evaluado:       A = {ganador_a['score']}        vs  B = {ganador_b['score']}")
        print("=" * 70 + "\n")
