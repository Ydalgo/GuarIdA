# 02 · Protocolo de benchmark

> **Estado:** borrador de F0. Se aplicará por primera vez en F2 (línea base) y se ajustará si hace falta antes de F4. Cualquier cambio del protocolo después de F2 obliga a repetir la línea base.

## 1. Principios

- Mismo modelo, misma cuantización, mismos prompts, misma longitud de salida y muestreo determinista (`temperature=0`, semilla fija) en todos los motores.
- Los formatos nativos de cada motor (OpenVINO INT4, MLC q4f16, EXL2, ternario, H3G…) se miden en una **tabla aparte** y se acompañan de la puerta de calidad.
- Separar siempre **carga en frío**, **primera petición** y **peticiones en caliente**. Repetir cada prueba ≥5 veces y anotar mediana y dispersión.
- Registrar el backend **realmente usado** (por los logs del motor), no el configurado.
- Equipo en reposo, alimentación conectada, perfil de energía fijo, sin otras cargas pesadas. Anotar la temperatura si hay *throttling*.

## 2. Perfiles de hardware

Los perfiles A y B son el público principal de GuarIdA; C y D sirven para no diseñar algo que solo funcione en una máquina.

| Perfil | Hardware tipo | Modelos | Candidatos típicos |
|---|---|---|---|
| **A · CPU modesta** | ≤32 GB RAM, sin GPU dedicada (Windows 11 y Linux) | Qwen3-0.6B, Qwen3-4B | llama.cpp, ik_llama.cpp, DynaLM, OpenVINO (Intel), mistral.rs, Herbert-rs |
| **B · APU / iGPU** | 32–64 GB RAM compartida, AMD APU o Intel iGPU (Vulkan / GTT) | Qwen3-4B, Qwen3-8B, Qwen3-30B-A3B si cabe | llama.cpp Vulkan, ik_llama.cpp, OpenVINO GPU (Intel), MLC Vulkan, Golem |
| **C · GPU media** | 8–16 GB VRAM (NVIDIA o AMD) + 32–64 GB RAM | Qwen3-8B, Qwen3-30B-A3B | llama.cpp (`-ot`/`--n-cpu-moe`), ik_llama.cpp, Ghost Infer, KTransformers, MLC, FastLLM |
| **D · GPU potente** | ≥16 GB VRAM + ≥64 GB RAM | Qwen3-30B-A3B (y BF16 si cabe) | llama.cpp, KTransformers, SGLang/vLLM (solo para el estudio de técnicas) |

Para cada equipo se guarda la ficha de hardware que ya genera GuarIdA (`hash_hardware`, CPU, núcleos/hilos, extensiones SIMD, RAM y velocidad, GPU, VRAM/GTT, SO, versión del controlador) más la versión o commit exacto de cada motor.

## 3. Modelos y cuantizaciones

| Grupo | Modelo | Qué se estudia |
|---|---|---|
| Denso pequeño | Qwen3-0.6B (también como **modelo borrador**) | Coste fijo del motor, latencia, especulación |
| Denso medio | Qwen3-4B, Qwen3-8B | SIMD, cuantización, memoria, contexto largo |
| MoE | Qwen3-30B-A3B (y Qwen3-Coder-30B-A3B por el caso de uso de código) | Reparto de expertos RAM/VRAM, transferencias |
| Fuera de concurso | Modelos ternarios/propietarios de formato | Solo para OpenSet-LLM / Golem H3G, tabla aparte |

Cuantización de referencia: **Q4_K_M GGUF** (más Q8_0 como referencia de calidad). Mismo archivo para todos los motores que lean GGUF; anotar el SHA-256.

### Memoria de KV-cache por token (FP16, una secuencia)

\[ M_{KV}/\text{token} = 2 \cdot L \cdot H_{kv} \cdot D \cdot B \]

Valores de arquitectura **a confirmar contra el `config.json` oficial en F1**:

| Modelo | Capas \(L\) | Cabezas KV \(H_{kv}\) | \(D\) | KV/token FP16 | 4k ctx | 16k ctx | 32k ctx |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-0.6B | 28 | 8 | 128 | 112 KiB | 448 MiB | 1,75 GiB | 3,5 GiB |
| Qwen3-4B | 36 | 8 | 128 | 144 KiB | 576 MiB | 2,25 GiB | 4,5 GiB |
| Qwen3-8B | 36 | 8 | 128 | 144 KiB | 576 MiB | 2,25 GiB | 4,5 GiB |
| Qwen3-30B-A3B | 48 | 4 | 128 | 96 KiB | 384 MiB | 1,5 GiB | 3 GiB |

Con KV `q8_0` el tamaño baja aproximadamente a la mitad (≈0,53×). En una APU con memoria compartida, esta memoria compite directamente con los pesos.

### Erratas detectadas en la conversación previa

- **Qwen3-30B-A3B tiene 48 capas, no 24** (según la ficha oficial del modelo; confirmar en F1). Por eso la tabla de KV-cache de la conversación previa (96 MiB a 2k tokens, 1,5 GiB a 32k) **se queda en la mitad**: el valor correcto es ≈192 MiB a 2k y ≈3 GiB a 32k.
- La propia conversación rectificó la arquitectura atribuida a DynaLM (DynaCore/DynaIR): no usar esa descripción.
- Nombres de modelo como "Qwen3.6-35B-A3B", "Qwen3.8-27B" o "Qwen3.8-Flash-Next" deben confirmarse antes de usarlos en el laboratorio.

## 4. Pruebas

Las pruebas A–E son genéricas; **F y G modelan la carga real de GuarIdA** y pesan más en la decisión.

| Prueba | Entrada | Salida | Qué mide |
|---|---:|---:|---|
| **A** · Latencia | 128 | 128 | TTFT y coste fijo |
| **B** · Mixta | 1.024 | 256 | Prefill y decode |
| **C** · Sostenida | 4.096 | 512 | Rendimiento sostenido |
| **D** · Memoria | 8.192 | 512 | Pico de RAM/VRAM/GTT |
| **E** · Escalado | 16.384 | 256 | Degradación con el contexto |
| **F** · Agente multiturno | Prefijo estable de 8.192 (sistema + contexto RAG) + 5 turnos de +300 tokens | 256 por turno | **TTFT por turno con reutilización de prefijo** (`--cache-reuse`, caché de prefijos, *slots*) |
| **G** · Edición de código | Archivo de ~2.000 tokens + instrucción de cambio | Archivo reescrito (~2.000) | Beneficio de *lookup* / especulación cuando la salida repite la entrada |
| **H** · MoE híbrido (solo MoE) | Pruebas B y F | — | Variantes de reparto: todo RAM, expertos en CPU (`-ot` / `--n-cpu-moe`), mixto, cada estrategia propia de cada motor |

Los prompts concretos se versionarán en `resultados/prompts/` en F2 (texto fijo en español y en código, sin datos personales).

### Barrido de reparto CPU/GPU

En motores que lo permitan, medir varias divisiones (p. ej. 0 %, 25 %, 50 %, 75 % y 100 % de capas en GPU con `-ngl`, o la asignación de operadores/expertos equivalente). Los porcentajes son de capas, no de carga computacional. No asumir que el reparto equitativo es el mejor.

## 5. Métricas

| Métrica | Definición | Prioridad para GuarIdA |
|---|---|---|
| TTFT | Tiempo hasta el primer token (ms) | Alta (sobre todo en F) |
| Prefill | Tokens de entrada / s | **Muy alta** (contexto largo de agente) |
| Decode | Tokens generados / s | Alta |
| ITL p50 / p99 | Intervalo entre tokens | Media |
| Latencia total de la tarea | Petición completa | Alta |
| Pico de RAM / VRAM / GTT | MB | Muy alta (hardware modesto) |
| Energía por token | \(E_{inferencia} / N_{tokens}\) (J/token) | Media (opcional si no hay medidor) |
| Arranque | Tiempo de carga del modelo en frío | Media |
| Calidad | Ver puerta de calidad | Bloqueante |
| Estabilidad | Fallos, OOM o bloqueos en 5 repeticiones | Bloqueante |

Herramientas: `llama-bench`/`llama-perplexity`, `benchmark_app` (OpenVINO), los benchmarks propios de cada motor **solo como apoyo**; la medición principal se hace con un cliente común contra la API HTTP (el mismo para todos los motores), reutilizando `engine/client.py` cuando la API sea compatible. Memoria: contadores del SO (Windows Performance Monitor / `/proc`, `nvidia-smi`, `rocm-smi`, `amdgpu_top`, `intel_gpu_top`). Energía: RAPL en Linux o medidor de enchufe.

## 6. Puerta de calidad

Un motor solo puede ganar si no empeora la calidad de forma apreciable:

1. **Mismo formato de pesos:** perplejidad sobre un texto fijo (`llama-perplexity` o equivalente) dentro de un margen pequeño frente a la línea base, y coincidencia alta de tokens con decodificación determinista.
2. **Formatos distintos:** batería pequeña de tareas de código con tests automáticos (offline, versionada en el repositorio) y comparación de aciertos frente a Q4_K_M y Q8_0 en llama.cpp.
3. **Especulación:** debe producir exactamente la misma salida que sin especulación en modo determinista (si no, es un error).

## 7. Formato de resultados

Un archivo JSON Lines por sesión: `resultados/AAAA-MM-DD_<hash_hw>_<motor>.jsonl`. Una línea por repetición:

```json
{
  "origen": "medido",
  "fecha": "2026-11-28T10:00:00+01:00",
  "hash_hardware": "…",
  "perfil": "B",
  "motor": "llama.cpp",
  "version_motor": "bNNNN / commit",
  "backend_real": "Vulkan",
  "flags": ["-ngl", "99", "-fa", "-ctk", "q8_0"],
  "modelo": "Qwen3-8B",
  "cuantizacion": "Q4_K_M",
  "sha256_modelo": "…",
  "prueba": "F",
  "turno": 3,
  "repeticion": 2,
  "tokens_entrada": 9092,
  "tokens_salida": 256,
  "tokens_reutilizados": 8790,
  "ttft_ms": null,
  "prefill_tps": null,
  "decode_tps": null,
  "itl_p50_ms": null,
  "itl_p99_ms": null,
  "ram_pico_mb": null,
  "vram_pico_mb": null,
  "gtt_pico_mb": null,
  "energia_j": null,
  "calidad": null,
  "error": null,
  "notas": ""
}
```

`null` significa *no medido*; nunca escribir `0` como valor pendiente. Las cifras tomadas de fuentes externas no van aquí, van al registro de afirmaciones del inventario.
