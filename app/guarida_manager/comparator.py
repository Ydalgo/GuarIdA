from dataclasses import dataclass
from typing import Any, Optional

from guarida_manager.hardware import InformacionHardware, obtener_informacion_hardware


@dataclass(frozen=True)
class AnalisisCuantizacion:
    modelo_base: str
    cuantizacion: str
    tamano_pesos_gb: float
    vram_kv_cache_4k_gb: float
    vram_kv_cache_16k_gb: float
    vram_kv_cache_32k_gb: float
    vram_total_16k_gb: float
    vram_total_32k_gb: float
    es_viable_16k_gpu: bool
    es_viable_32k_gpu: bool
    calidad_relativa_pct: float
    recomendacion: str


@dataclass(frozen=True)
class EstimacionRendimientoModelo:
    """Estimación avanzada de memoria VRAM y tokens/segundo inspirada en CanIRun, LLMFit y HF."""
    modelo_id: str
    tamano_pesos_gb: float
    vram_requerida_4k_gb: float
    vram_requerida_16k_gb: float
    tok_s_estimado: float
    es_medido_real: bool
    clasificacion_coding: str       # "ÓPTIMO (>=15 t/s)", "VIABLE (>=8 t/s)", "LENTO (<8 t/s)"
    clasificacion_chat: str         # "INSTANTÁNEO (>=30 t/s)", "ÁGIL (>=15 t/s)", "PAUSADO (<15 t/s)"
    estrategia_vram: str           # "GPU_COMPLETO", "GPU_CON_KV_Q8", "OFFLOAD_PARCIAL", "CPU_PURO"
    nota_tecnica: str


class ComparadorModelosHardware:
    """Evalúa la viabilidad y compensación (trade-offs) entre cuantizaciones, contextos y tokens/s."""

    # Umbrales empíricos de fluidez operativa
    TOK_S_MINIMO_CODING = 8.0          # Mínimo para autocompletado y parches sin romper flujo mental
    TOK_S_RECOMENDADO_CODING = 15.0    # Recomendado para generación de métodos y tests
    TOK_S_MINIMO_CHAT = 12.0           # Mínimo para lectura en tiempo real
    TOK_S_AGIL_CHAT = 20.0             # Fluidez conversacional natural
    TOK_S_OPTIMO = 35.0                # Experiencia instantánea y agentes multi-turno

    # Consumo aproximado de KV Cache en FP16 (GB por cada 1000 tokens en modelos 7B ~0.25 GB)
    FACTOR_KV_CACHE_7B_GB_POR_1K = 0.25

    @classmethod
    def estimar_consumo_kv_por_1k(cls, tamano_gb: float) -> float:
        """Calcula el consumo de KV Cache en FP16 según el tamaño del modelo (CanIRun/LLMFit)."""
        if tamano_gb < 1.0:
            return 0.04
        elif tamano_gb < 3.0:
            return 0.10
        elif tamano_gb < 8.0:
            return 0.25
        elif tamano_gb < 16.0:
            return 0.50
        else:
            return 0.85

    @classmethod
    def evaluar_modelo_completo(
        cls,
        modelo_id: str,
        tamano_gb: float,
        hardware: Optional[InformacionHardware] = None,
        gestor_cache: Optional[Any] = None,
    ) -> EstimacionRendimientoModelo:
        """Calcula memoria total requerida y tokens/segundo basándose en SQLite real o fórmula predictiva."""
        hw = hardware or obtener_informacion_hardware()
        vram_disponible = hw.gtt_disponible_gb if hw.tiene_aceleracion_gpu else 0.0
        vram_segura = max(0.0, vram_disponible - 1.2)

        # 1. Cálculo de VRAM / Memoria según fórmulas CanIRun / LLMFit
        factor_kv_1k = cls.estimar_consumo_kv_por_1k(tamano_gb)
        kv_4k = round(4.0 * factor_kv_1k, 2)
        kv_16k = round(16.0 * factor_kv_1k, 2)
        runtime_overhead = 0.60  # Buffer de activaciones y contexto CUDA/Vulkan

        total_4k = round(tamano_gb + kv_4k + runtime_overhead, 2)
        total_16k = round(tamano_gb + kv_16k + runtime_overhead, 2)

        # 2. Estrategia de carga según capacidad del hardware
        if not hw.tiene_aceleracion_gpu or vram_disponible < 1.0:
            estrategia = "CPU_PURO"
        elif total_4k <= vram_segura:
            estrategia = "GPU_COMPLETO"
        elif (tamano_gb + (kv_4k * 0.5) + runtime_overhead) <= vram_segura:
            estrategia = "GPU_CON_KV_Q8"
        elif tamano_gb <= vram_segura:
            estrategia = "GPU_CON_KV_Q8"
        elif total_4k <= hw.memoria_extrema_forzable_gb:
            estrategia = "OFFLOAD_PARCIAL"
        else:
            estrategia = "CPU_PURO"

        # 3. Consulta de ground truth empírico en SQLite
        es_medido_real = False
        tok_s = 0.0
        if gestor_cache:
            try:
                optima = gestor_cache.obtener_configuracion_optima(modelo_id, hw.hash_hardware)
                if optima and optima.get("tok_s_medido", 0) > 0:
                    tok_s = float(optima["tok_s_medido"])
                    es_medido_real = True
                else:
                    bench = gestor_cache.obtener_benchmark(modelo_id, hw.hash_hardware)
                    if bench and bench.get("tok_s", 0) > 0:
                        tok_s = float(bench["tok_s"])
                        es_medido_real = True
            except Exception:
                pass

        # 4. Si no hay medición en SQLite, estimar tokens/s predictivo según ancho de banda
        if not es_medido_real:
            # Factor de ancho de banda según escala de GPU (desde iGPU 60 GB/s hasta Workstations 128GB HBM/GDDR6X 1000-2000 GB/s)
            if vram_disponible >= 80.0:
                factor_ancho_banda = 2.4  # Nivel 128 GB VRAM (Mac Ultra, A100, H100)
            elif vram_disponible >= 40.0:
                factor_ancho_banda = 1.9  # Nivel 48-64 GB VRAM (Dual GPU, RTX 6000 Ada)
            elif vram_disponible >= 20.0:
                factor_ancho_banda = 1.5  # RTX 3090/4090 (1000 GB/s)
            elif vram_disponible >= 10.0:
                factor_ancho_banda = 1.1  # RTX 3060/4070 (300-500 GB/s)
            else:
                factor_ancho_banda = 0.85 # iGPU compartida / APU (50-100 GB/s)

            if estrategia == "GPU_COMPLETO":
                if tamano_gb < 1.0:
                    base_tok = 65.0
                elif tamano_gb < 3.0:
                    base_tok = 42.0
                elif tamano_gb < 7.0:
                    base_tok = 28.0
                elif tamano_gb < 12.0:
                    base_tok = 18.0
                elif tamano_gb < 25.0:
                    base_tok = 14.0
                elif tamano_gb < 50.0:
                    base_tok = 9.5
                else:
                    base_tok = 6.5
                tok_s = round(base_tok * factor_ancho_banda, 1)
            elif estrategia in ("GPU_CON_KV_Q8", "OFFLOAD_PARCIAL"):
                proporcion = max(0.2, min(0.85, vram_segura / max(tamano_gb, 1.0)))
                tok_s = round(max(4.0, 24.0 * proporcion * factor_ancho_banda), 1)
            else:
                # Inferencia en CPU (limitada por ancho de banda de bus DDR)
                hilos = max(1, hw.nucleos_fisicos)
                if tamano_gb < 1.0:
                    tok_s = 35.0
                elif tamano_gb < 3.0:
                    tok_s = 16.0
                elif tamano_gb < 6.0:
                    tok_s = 8.5
                elif tamano_gb < 12.0:
                    tok_s = 4.2
                elif tamano_gb < 30.0:
                    tok_s = 2.0
                else:
                    tok_s = 0.9
                tok_s = round(tok_s * min(1.2, max(0.8, hilos / 4.0)), 1)

        # 5. Clasificaciones de viabilidad operativa
        if tok_s >= cls.TOK_S_RECOMENDADO_CODING:
            clasif_coding = "ÓPTIMO (>=15 t/s)"
        elif tok_s >= cls.TOK_S_MINIMO_CODING:
            clasif_coding = "VIABLE (>=8 t/s)"
        else:
            clasif_coding = "LENTO (<8 t/s)"

        if tok_s >= cls.TOK_S_OPTIMO:
            clasif_chat = "INSTANTÁNEO (>=35 t/s)"
        elif tok_s >= cls.TOK_S_AGIL_CHAT:
            clasif_chat = "ÁGIL (>=20 t/s)"
        elif tok_s >= cls.TOK_S_MINIMO_CHAT:
            clasif_chat = "FLUIDO (>=12 t/s)"
        else:
            clasif_chat = "PAUSADO (<12 t/s)"

        vram_libre = max(0.0, vram_disponible - total_4k) if hw.tiene_aceleracion_gpu else 0.0
        fuente = "[Medido en SQLite]" if es_medido_real else "[Estimación CanIRun/LLMFit]"
        nota = (
            f"{fuente} Ocupa ~{total_4k:.1f} GB ({vram_libre:.1f} GB libres de {vram_disponible:.1f} GB VRAM). "
            f"Estrategia: {estrategia}."
        )

        return EstimacionRendimientoModelo(
            modelo_id=modelo_id,
            tamano_pesos_gb=round(tamano_gb, 2),
            vram_requerida_4k_gb=total_4k,
            vram_requerida_16k_gb=total_16k,
            tok_s_estimado=round(tok_s, 1),
            es_medido_real=es_medido_real,
            clasificacion_coding=clasif_coding,
            clasificacion_chat=clasif_chat,
            estrategia_vram=estrategia,
            nota_tecnica=nota,
        )

    @classmethod
    def analizar_cuantizaciones_7b(cls) -> list[AnalisisCuantizacion]:
        hardware = obtener_informacion_hardware()
        vram_gpu_gb = hardware.gtt_disponible_gb if hardware.tiene_aceleracion_gpu else 0.0

        cuants = [
            ("Q5_K_M", 5.40, 99.2, "Máxima precisión. Adecuado para código con 8k-16k tokens si hay VRAM amplia."),
            ("Q4_K_M", 4.68, 97.5, "Estándar de oro. Excelente equilibrio entre tokens/s y calidad sintáctica."),
            ("Q3_K_M", 3.74, 93.0, "Ahorro de ~1 GB en pesos. Permite estirar el contexto a 32k tokens en hardware de 16 GB."),
            ("Q2_K", 2.68, 82.0, "Cuantización extrema. Pérdida perceptible en razonamiento, usar solo por necesidad crítica de RAM."),
        ]

        resultados = []
        for nombre_q, tamano, calidad, rec in cuants:
            # Cálculo de KV Cache:
            kv_4k = round(4.0 * cls.FACTOR_KV_CACHE_7B_GB_POR_1K, 2)   # ~1.0 GB
            kv_16k = round(16.0 * cls.FACTOR_KV_CACHE_7B_GB_POR_1K, 2) # ~4.0 GB
            kv_32k = round(32.0 * cls.FACTOR_KV_CACHE_7B_GB_POR_1K, 2) # ~8.0 GB

            total_16k = round(tamano + kv_16k, 2)
            total_32k = round(tamano + kv_32k, 2)

            viable_16k = vram_gpu_gb >= total_16k
            viable_32k = vram_gpu_gb >= total_32k

            resultados.append(
                AnalisisCuantizacion(
                    modelo_base="Qwen2.5-Coder-7B",
                    cuantizacion=nombre_q,
                    tamano_pesos_gb=tamano,
                    vram_kv_cache_4k_gb=kv_4k,
                    vram_kv_cache_16k_gb=kv_16k,
                    vram_kv_cache_32k_gb=kv_32k,
                    vram_total_16k_gb=total_16k,
                    vram_total_32k_gb=total_32k,
                    es_viable_16k_gpu=viable_16k,
                    es_viable_32k_gpu=viable_32k,
                    calidad_relativa_pct=calidad,
                    recomendacion=rec,
                )
            )

        return resultados


if __name__ == "__main__":
    analisis = ComparadorModelosHardware.analizar_cuantizaciones_7b()
    hardware = obtener_informacion_hardware()
    vram = hardware.gtt_disponible_gb if hardware.tiene_aceleracion_gpu else 0.0

    print("=== GUARIDA: COMPARADOR DE CUANTIZACIONES Y MEMORIA DE CONTEXTO ===")
    print(f"Hardware GPU detectado: {hardware.nombre_gpu_principal} | VRAM/GTT: {vram:.2f} GB\n")

    for a in analisis:
        v16k = "SI (Acelera en GPU)" if a.es_viable_16k_gpu else "NO (Desborda a RAM)"
        v32k = "SI (Acelera en GPU)" if a.es_viable_32k_gpu else "NO (Desborda a RAM)"
        print(f"[{a.cuantizacion}] Calidad estimada: ~{a.calidad_relativa_pct:.1f}%")
        print(f"  - Tamaño archivo pesos:    {a.tamano_pesos_gb:.2f} GB")
        print(f"  - Memoria total con 16k:   {a.vram_total_16k_gb:.2f} GB -> Viable GPU: {v16k}")
        print(f"  - Memoria total con 32k:   {a.vram_total_32k_gb:.2f} GB -> Viable GPU: {v32k}")
        print(f"  - Nota técnica:            {a.recomendacion}\n")

