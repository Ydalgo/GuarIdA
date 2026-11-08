import datetime
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.cache import ConfiguracionOptimaRegistro, GestorCache
from guarida_manager.engine.server import LlamaServerConfig
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.logger import obtener_logger
from guarida_manager.telemetry import MonitorTelemetriaHardware
from guarida_manager.tuning.bateria import BateriaEstresLlama
from guarida_manager.tuning.capacidades import CapacidadesBinario, DescubridorCapacidades
from guarida_manager.tuning.ejecutor import EjecutorIntentoLlama, ResultadoIntentoConfig
from guarida_manager.tuning.perfiles import (
    GestorPerfilesTuning,
    PerfilBarrido,
    PerfilBateria,
    calcular_hash_canonico_dict,
)
from guarida_manager.tuning.scoring import EvaluadorScoring

logger = obtener_logger("tuning.buscador")


class BuscadorAfinamientoEtapas:
    """Orquesta la búsqueda por etapas, poda temprana y validación end-to-end de configuraciones óptimas."""

    def __init__(
        self,
        modelo_path: Path,
        modelo_id: str,
        capacidades: CapacidadesBinario,
        perfil_barrido: Optional[PerfilBarrido] = None,
        perfil_bateria: Optional[PerfilBateria] = None,
        gestor_cache: Optional[GestorCache] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ):
        self.modelo_path = Path(modelo_path)
        self.modelo_id = modelo_id
        self.capacidades = capacidades
        self.perfil_barrido = perfil_barrido or GestorPerfilesTuning.obtener_perfil_barrido("estandar")
        self.perfil_bateria = perfil_bateria or GestorPerfilesTuning.obtener_perfil_bateria("estandar")
        self.es_modelo_embedding = any(
            k in self.modelo_id.lower() for k in ("embed", "bge", "minilm", "jina", "snowflake")
        )
        if self.es_modelo_embedding:
            self.perfil_bateria.escenarios_activos = ["embedding"]
            self.perfil_barrido.objetivo_scoring = "embedding"
        self.cache = gestor_cache or GestorCache()
        self.callback_progreso = callback_progreso
        self.ejecutor = EjecutorIntentoLlama()
        self.memo_configs: dict[str, ResultadoIntentoConfig] = {}
        self.mejor_score_global = 0.0
        self.mejor_resultado: Optional[ResultadoIntentoConfig] = None
        self.tiempo_inicio = 0.0

    def _notificar(self, mensaje: str, progreso: float = 0.0) -> None:
        hora_actual = datetime.datetime.now().strftime("%H:%M:%S")
        if self.tiempo_inicio > 0:
            transcurrido = int(time.time() - self.tiempo_inicio)
            minutos = transcurrido // 60
            segundos = transcurrido % 60
            transcurrido_str = f"{minutos:02d}:{segundos:02d}"

            if 0.05 < progreso < 0.99:
                eta_total = transcurrido / progreso
                eta_restante = max(0, int(eta_total - transcurrido))
                eta_str = f"{eta_restante // 60:02d}:{eta_restante % 60:02d}"
            else:
                eta_str = "--:--"
            prefijo = f"[{hora_actual} | {transcurrido_str} | ETA: {eta_str}]"
        else:
            prefijo = f"[{hora_actual}]"

        linea = f"{prefijo} [{progreso * 100:4.1f}%] {mensaje}" if progreso > 0 else f"{prefijo} {mensaje}"
        if self.callback_progreso:
            self.callback_progreso(linea, progreso)
        else:
            print(linea)

    def _presupuesto_agotado(self) -> bool:
        if self.perfil_barrido.presupuesto_minutos <= 0:
            return False
        transcurrido_min = (time.time() - self.tiempo_inicio) / 60.0
        return transcurrido_min >= self.perfil_barrido.presupuesto_minutos

    def _crear_hash_config(self, args_dict: dict[str, Any]) -> str:
        claves_relevantes = {
            "n_gpu_layers": args_dict.get("n_gpu_layers", 0),
            "threads": args_dict.get("threads", 4),
            "batch_size": args_dict.get("batch_size", 512),
            "ubatch_size": args_dict.get("ubatch_size", 512),
            "kv_cache_tipo": args_dict.get("kv_cache_tipo", "f16"),
            "flash_attn": bool(args_dict.get("flash_attn", False)),
            "ctx_size": args_dict.get("ctx_size", 4096),
        }
        return calcular_hash_canonico_dict(claves_relevantes)

    def probar_configuracion(
        self,
        etapa: str,
        n_gpu_layers: int,
        threads: int,
        batch_size: int,
        ubatch_size: int,
        kv_cache_tipo: str,
        flash_attn: bool,
        ctx_size: int,
        sesion_id: str,
        progreso_etapa: float = 0.0,
    ) -> ResultadoIntentoConfig:
        """Valida compatibilidad, comprueba memoización/reanudación y ejecuta el intento."""
        args_dict = {
            "n_gpu_layers": n_gpu_layers,
            "threads": threads,
            "batch_size": batch_size,
            "ubatch_size": ubatch_size,
            "kv_cache_tipo": kv_cache_tipo,
            "flash_attn": flash_attn,
            "ctx_size": ctx_size,
        }
        hash_cfg = self._crear_hash_config(args_dict)

        if hash_cfg in self.memo_configs:
            return self.memo_configs[hash_cfg]

        MonitorTelemetriaHardware.comprobar_y_aplicar_proteccion_termica(
            callback_aviso=lambda msg: self._notificar(msg, progreso_etapa)
        )
        telemetria_str = MonitorTelemetriaHardware.formatear_linea_telemetria()

        self._notificar(
            f"-> Probando {etapa}: ngl={n_gpu_layers}, hilos={threads}, batch={batch_size}/{ubatch_size}, "
            f"kv={kv_cache_tipo}, fa={flash_attn}, ctx={ctx_size}",
            progreso_etapa,
        )

        # Validar compatibilidad previa
        valido, motivo_err = DescubridorCapacidades.validar_compatibilidad_config(args_dict, self.capacidades)
        if not valido:
            res_invalido = ResultadoIntentoConfig(
                hash_config=hash_cfg,
                etapa=etapa,
                args=args_dict,
                estado="flag_invalido",
                error_resumen=motivo_err,
            )
            self._guardar_config_en_bd(sesion_id, res_invalido)
            self.memo_configs[hash_cfg] = res_invalido
            self._notificar(f"   [INCOMPATIBLE]: {motivo_err}", progreso_etapa)
            return res_invalido

        cfg_server = LlamaServerConfig(
            modelo_path=self.modelo_path,
            binario_path=Path(self.capacidades.ruta_binario),
            host="127.0.0.1",
            n_gpu_layers=n_gpu_layers,
            ctx_size=ctx_size,
            batch_size=batch_size,
            threads=threads,
            kv_cache_type=kv_cache_tipo,
            embedding=self.es_modelo_embedding,
            ubatch_size=ubatch_size if self.capacidades.soporta_ubatch else None,
            flash_attn=flash_attn if self.capacidades.soporta_flash_attn else False,
        )

        def _bateria(cliente) -> list[dict[str, Any]]:
            bat = BateriaEstresLlama(cliente, self.perfil_bateria, cliente_embedding=cliente)
            return bat.ejecutar_bateria_completa(ctx_size=ctx_size)

        res = self.ejecutor.ejecutar_intento(
            config=cfg_server,
            hash_config=hash_cfg,
            etapa=etapa,
            funcion_bateria=_bateria,
        )

        if res.estado == "ok":
            score = EvaluadorScoring.calcular_score(
                res.ejecuciones_crudo,
                res.metricas_memoria.ram_pico_mb + res.metricas_memoria.vram_pico_mb,
                ctx_size,
                self.perfil_barrido.objetivo_scoring,
            )
            res.score = score
            metricas = EvaluadorScoring.extraer_metricas_resumen(res.ejecuciones_crudo)
            tg = metricas["tg_stats"]["mediana"]
            pp = metricas["pp_stats"]["mediana"]
            ttft = metricas["ttft_stats"]["mediana"]
            emb_st = metricas.get("embedding_stats")
            if self.es_modelo_embedding and emb_st:
                emb_s = emb_st.get("embeddings_por_s", 0.0)
                lat_e = emb_st.get("latencia_media_ms", ttft)
                dim_e = emb_st.get("dimensiones_vector", 0)
                self._notificar(
                    f"   [OK] Vectorización: {emb_s:5.1f} emb/s | Latencia: {lat_e:4.1f} ms | Dim: {dim_e} | Score: {score:5.2f} [Cooperativo CPU: ngl=0] | {telemetria_str}",
                    progreso_etapa,
                )
            else:
                self._notificar(
                    f"   [OK] TG: {tg:4.1f} tok/s | PP: {pp:4.1f} tok/s | TTFT: {ttft:4.0f} ms | Score: {score:5.2f} | {telemetria_str}",
                    progreso_etapa,
                )
            if self.mejor_resultado is None or score >= self.mejor_score_global:
                self.mejor_score_global = score
                self.mejor_resultado = res
                try:
                    hw_now = obtener_informacion_hardware()
                    opt_provisional = ConfiguracionOptimaRegistro(
                        modelo_id=self.modelo_id,
                        hash_hardware=hw_now.hash_hardware,
                        n_gpu_layers=res.args.get("n_gpu_layers", 0),
                        ctx_size=res.args.get("ctx_size", ctx_size),
                        batch_size=res.args.get("batch_size", 512),
                        kv_cache_tipo=res.args.get("kv_cache_tipo", "f16"),
                        tok_s_medido=round(tg or 0.0, 2),
                        gtt_pico_mb=res.metricas_memoria.gtt_pico_mb,
                        fecha_afinamiento=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        motivo_descarte_o_nota=f"Mejor parcial ({res.etapa}, Score: {score:.2f})",
                        es_recomendada=True,
                        threads=res.args.get("threads", 4),
                        ubatch_size=res.args.get("ubatch_size", 512),
                        flash_attn=1 if res.args.get("flash_attn") else 0,
                    )
                    self.cache.guardar_configuracion_optima(opt_provisional)
                except Exception:
                    pass
        else:
            self._notificar(f"   [{res.estado.upper()}]: {res.error_resumen or 'Fallo durante el intento'}", progreso_etapa)

        self._guardar_config_en_bd(sesion_id, res)
        self.memo_configs[hash_cfg] = res
        return res

    def _guardar_config_en_bd(self, sesion_id: str, res: ResultadoIntentoConfig) -> None:
        """Persiste el resultado del intento y sus repeticiones en SQLite."""
        try:
            with self.cache.sesion() as conn:
                config_id = f"{sesion_id[:8]}_{res.hash_config[:12]}"
                conn.execute(
                    """
                    INSERT INTO bench_configs (
                        id, sesion_id, hash_config, args_json, etapa, estado,
                        error_resumen, mem_modelo_mb, mem_kv_mb, mem_compute_mb,
                        ram_pico_mb, vram_pico_mb, gtt_pico_mb, score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        estado = excluded.estado,
                        error_resumen = excluded.error_resumen,
                        score = excluded.score;
                    """,
                    (
                        config_id,
                        sesion_id,
                        res.hash_config,
                        json.dumps(res.args, default=str),
                        res.etapa,
                        res.estado,
                        res.error_resumen,
                        res.metricas_memoria.mem_modelo_mb,
                        res.metricas_memoria.mem_kv_mb,
                        res.metricas_memoria.mem_compute_mb,
                        res.metricas_memoria.ram_pico_mb,
                        res.metricas_memoria.vram_pico_mb,
                        res.metricas_memoria.gtt_pico_mb,
                        res.score,
                    ),
                )

                for ejec in res.ejecuciones_crudo:
                    conn.execute(
                        """
                        INSERT INTO bench_ejecuciones (
                            config_id, escenario, rep, es_calentamiento, prompt_n,
                            predicted_n, pp_tok_s, tg_tok_s, ttft_ms, latencia_total_ms,
                            exito, calidad_pct
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            config_id,
                            ejec.get("escenario", "general"),
                            ejec.get("rep", 1),
                            1 if ejec.get("es_calentamiento") else 0,
                            ejec.get("prompt_n", 0),
                            ejec.get("predicted_n", 0),
                            ejec.get("pp_tok_s", 0.0),
                            ejec.get("tg_tok_s", 0.0),
                            ejec.get("ttft_ms", 0.0),
                            ejec.get("latencia_total_ms", 0.0),
                            ejec.get("exito", 1),
                            ejec.get("calidad_pct", 100.0),
                        ),
                    )
        except Exception as e:
            logger.error(f"Fallo al registrar config en BD SQLite: {e}", exc_info=True)

    def ejecutar_barrido_completo(self) -> Optional[ResultadoIntentoConfig]:
        """Ejecuta las etapas ordenadas: baseline -> ngl -> threads -> batch/ubatch -> flash-attn/kv -> ctx -> refinado top-K."""
        self.tiempo_inicio = time.time()
        hw = obtener_informacion_hardware()
        sha_modelo = hashlib.sha256(self.modelo_path.name.encode("utf-8")).hexdigest()
        sesion_id = hashlib.sha256(
            f"{self.modelo_id}_{hw.hash_hardware}_{self.capacidades.sha256_binario}_{time.time()}".encode("utf-8")
        ).hexdigest()[:16]

        # Registrar sesión en BD
        with self.cache.sesion() as conn:
            conn.execute(
                """
                INSERT INTO bench_sesiones (
                    id, modelo_id, sha256_modelo, hash_hardware, sha256_binario,
                    version_build, hash_perfil_barrido, hash_perfil_bateria,
                    objetivo, estado, inicio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sesion_id,
                    self.modelo_id,
                    sha_modelo,
                    hw.hash_hardware,
                    self.capacidades.sha256_binario,
                    self.capacidades.version_build,
                    self.perfil_barrido.hash_sha256,
                    self.perfil_bateria.hash_sha256,
                    self.perfil_barrido.objetivo_scoring,
                    "en_curso",
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )

        self._notificar("Iniciando afinamiento por etapas...", 0.05)

        # ETAPA 0: Baseline
        hilos_def = hw.nucleos_fisicos if hw.nucleos_fisicos > 0 else 4
        if self.es_modelo_embedding:
            self._notificar(
                "Modo Cooperativo AST activado: ngl=0 fijo (100% GPU reservada al modelo Coder) y poda de hilos CPU.",
                0.08,
            )
            hilos_def = max(1, hilos_def // 2)

        res_base = self.probar_configuracion(
            etapa="etapa_0_baseline",
            n_gpu_layers=0,
            threads=hilos_def,
            batch_size=512,
            ubatch_size=512,
            kv_cache_tipo="f16",
            flash_attn=False,
            ctx_size=2048,
            sesion_id=sesion_id,
            progreso_etapa=0.10,
        )
        if res_base.estado == "ok" and self.mejor_resultado is None:
            self.mejor_resultado = res_base

        # ETAPA 1: Búsqueda binaria de n_gpu_layers (omitida en modelos de embeddings cooperativos)
        ngl_optimo = 0
        if hw.tiene_aceleracion_gpu and not self.es_modelo_embedding:
            self._notificar("Buscando capas en GPU (n_gpu_layers)...", 0.15)
            limite_capas_max = 45  # Límite práctico general para modelos 7B-14B
            bajo, alto = 0, limite_capas_max
            mejor_ngl_res = res_base

            while bajo <= alto:
                medio = (bajo + alto) // 2
                res = self.probar_configuracion(
                    etapa="etapa_1_ngl",
                    n_gpu_layers=medio,
                    threads=hilos_def,
                    batch_size=512,
                    ubatch_size=512,
                    kv_cache_tipo="f16",
                    flash_attn=False,
                    ctx_size=2048,
                    sesion_id=sesion_id,
                    progreso_etapa=0.25,
                )
                if res.estado == "ok":
                    ngl_optimo = medio
                    mejor_ngl_res = res
                    bajo = medio + 1  # Intentar meter más capas
                else:
                    alto = medio - 1  # Desbordó o falló, reducir capas
                if self._presupuesto_agotado():
                    break

            # Probar también un escalón inmediatamente inferior por overhead de GTT
            if ngl_optimo > 4 and not self._presupuesto_agotado():
                self.probar_configuracion(
                    etapa="etapa_1_ngl_refinado",
                    n_gpu_layers=ngl_optimo - 2,
                    threads=hilos_def,
                    batch_size=512,
                    ubatch_size=512,
                    kv_cache_tipo="f16",
                    flash_attn=False,
                    ctx_size=2048,
                    sesion_id=sesion_id,
                    progreso_etapa=0.30,
                )

        # ETAPA 2: Optimización de Hilos
        self._notificar("Afinando hilos de CPU...", 0.35)
        if self.es_modelo_embedding:
            # No superar la mitad de núcleos físicos para no restar CPU al modelo Coder
            max_coop = max(2, (hw.nucleos_fisicos or 4) // 2)
            hilos_candidatos = sorted(list({1, 2, max_coop}))
        else:
            hilos_candidatos = sorted(list({
                max(1, hilos_def // 2),
                hilos_def,
                hilos_def + 2,
                hw.nucleos_logicos,
            }))
        hilos_optimos = hilos_def
        for h in hilos_candidatos:
            if self._presupuesto_agotado():
                break
            r = self.probar_configuracion(
                etapa="etapa_2_threads",
                n_gpu_layers=ngl_optimo,
                threads=h,
                batch_size=512,
                ubatch_size=512,
                kv_cache_tipo="f16",
                flash_attn=False,
                ctx_size=2048,
                sesion_id=sesion_id,
                progreso_etapa=0.45,
            )
            if r.score > self.mejor_score_global:
                hilos_optimos = h

        # ETAPA 3: Batch y UBatch
        self._notificar("Afinando batch y ubatch...", 0.55)
        b_opt = 512
        ub_opt = 512
        for b in self.perfil_barrido.batch_sizes:
            for ub in self.perfil_barrido.ubatch_sizes:
                if ub > b or self._presupuesto_agotado():
                    continue
                r = self.probar_configuracion(
                    etapa="etapa_3_batch",
                    n_gpu_layers=ngl_optimo,
                    threads=hilos_optimos,
                    batch_size=b,
                    ubatch_size=ub,
                    kv_cache_tipo="f16",
                    flash_attn=False,
                    ctx_size=2048,
                    sesion_id=sesion_id,
                    progreso_etapa=0.65,
                )
                if r.score > self.mejor_score_global:
                    b_opt, ub_opt = b, ub

        # ETAPA 4 y 5: Flash Attention, KV Cache y Contexto (solo modelos generativos)
        fa_opt = False
        kv_opt = "f16"
        ctx_opt = 2048
        if not self.es_modelo_embedding:
            self._notificar("Probando Flash Attention y cuantización de KV Cache...", 0.75)
            opciones_fa = [True, False] if self.capacidades.soporta_flash_attn else [False]
            for fa in opciones_fa:
                for kv in self.perfil_barrido.kv_cache_tipos:
                    if self._presupuesto_agotado():
                        break
                    r = self.probar_configuracion(
                        etapa="etapa_4_kv_fa",
                        n_gpu_layers=ngl_optimo,
                        threads=hilos_optimos,
                        batch_size=b_opt,
                        ubatch_size=ub_opt,
                        kv_cache_tipo=kv,
                        flash_attn=fa,
                        ctx_size=2048,
                        sesion_id=sesion_id,
                        progreso_etapa=0.80,
                    )
                    if r.score > self.mejor_score_global:
                        fa_opt, kv_opt = fa, kv

            self._notificar("Determinando contexto máximo estable...", 0.85)
            for c in self.perfil_barrido.ctx_escalones:
                if self._presupuesto_agotado():
                    break
                r = self.probar_configuracion(
                    etapa="etapa_5_ctx",
                    n_gpu_layers=ngl_optimo,
                    threads=hilos_optimos,
                    batch_size=b_opt,
                    ubatch_size=ub_opt,
                    kv_cache_tipo=kv_opt,
                    flash_attn=fa_opt,
                    ctx_size=c,
                    sesion_id=sesion_id,
                    progreso_etapa=0.90,
                )
                if r.estado == "ok":
                    ctx_opt = c
                else:
                    break

        # Finalizar sesión en BD
        with self.cache.sesion() as conn:
            conn.execute(
                """
                UPDATE bench_sesiones
                SET estado = 'completada', fin = ?
                WHERE id = ?;
                """,
                (datetime.datetime.now(datetime.timezone.utc).isoformat(), sesion_id),
            )

        # Si tenemos ganador, persistir en configuraciones_optimas y benchmarks
        if self.mejor_resultado and self.mejor_resultado.estado == "ok":
            args = self.mejor_resultado.args
            metricas = EvaluadorScoring.extraer_metricas_resumen(self.mejor_resultado.ejecuciones_crudo)
            tg_tok_s = metricas["tg_stats"]["mediana"] or 15.0

            opt_reg = ConfiguracionOptimaRegistro(
                modelo_id=self.modelo_id,
                hash_hardware=hw.hash_hardware,
                n_gpu_layers=args.get("n_gpu_layers", 0),
                ctx_size=args.get("ctx_size", ctx_opt),
                batch_size=args.get("batch_size", b_opt),
                kv_cache_tipo=args.get("kv_cache_tipo", kv_opt),
                tok_s_medido=round(tg_tok_s, 2),
                gtt_pico_mb=self.mejor_resultado.metricas_memoria.gtt_pico_mb,
                fecha_afinamiento=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                motivo_descarte_o_nota=f"Ganador afinamiento {self.perfil_barrido.objetivo_scoring} (Score: {self.mejor_resultado.score})",
                es_recomendada=True,
                threads=args.get("threads", hilos_optimos),
                ubatch_size=args.get("ubatch_size", ub_opt),
                flash_attn=1 if args.get("flash_attn") else 0,
            )
            self.cache.guardar_configuracion_optima(opt_reg)

        self._notificar("Afinamiento y benchmarking completado.", 1.0)
        return self.mejor_resultado
