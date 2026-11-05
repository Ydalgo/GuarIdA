from dataclasses import dataclass
from typing import Optional

from guarida_manager.hardware import obtener_informacion_hardware


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


class ComparadorModelosHardware:
    """Evalúa la viabilidad y compensación (trade-offs) entre cuantizaciones y contextos."""

    # Consumo aproximado de KV Cache en FP16 (GB por cada 1000 tokens en modelos 7B ~0.25 GB)
    FACTOR_KV_CACHE_7B_GB_POR_1K = 0.25

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

