# 01 · Inventario de candidatos

> **Estado:** borrador de F0. **Nada de lo que figura aquí está verificado todavía.** Licencias, soporte y cifras proceden de la conversación previa con ChatGPT o de resúmenes de búsqueda; se confirmarán en F1 leyendo el repositorio (LICENSE, README, releases, issues).

## Leyenda

- **Línea:** `L` = motor ligero (pocos recursos, CPU/iGPU) · `R` = alto rendimiento (CUDA/Vulkan/ROCm) · `X` = experimental o arquitectura especializada · `T` = referencia teórica o recopilatorio.
- **Prioridad para GuarIdA:** `A` = probar/estudiar primero · `B` = segunda ronda · `C` = solo seguimiento o estudio puntual.
- **Origen:** `U` = enlace aportado por el responsable del proyecto · `G` = mencionado solo en la conversación con ChatGPT (sin enlace aportado; **verificar que existe**).
- **Estado F1:** `pendiente` · `verificado` · `descartado` · `no encontrado`.

> Criterio de prioridad: encaje con el hardware objetivo de GuarIdA (APU/iGPU con Vulkan, CPU x86-64, GPU media), Windows + Linux, offline, soporte Qwen3, licencia compatible con GPL-3.0 y coste de integración (lo que habla la API de `llama-server` o lee GGUF cuesta menos).

## Tabla resumen

| # | Proyecto | Enlace | Línea | Prio | Origen | Por qué interesa a GuarIdA | Estado F1 |
|---|---|---|---|---|---|---|---|
| 0 | **llama.cpp** (`llama-server`) | <https://github.com/ggml-org/llama.cpp> | L/R | **Base** | G | Motor actual de GuarIdA. Línea base obligatoria | pendiente (versión distribuida) |
| 1 | **alesha-pro/llm.asm** | <https://github.com/alesha-pro/llm.asm> | X | A (estudio) | U | Inspirador: especialización extrema, mmap sin copias, Q8_0 AVX2, arranque instantáneo | pendiente |
| 2 | **ik_llama.cpp** | <https://github.com/ikawrakow/ik_llama.cpp> | L/R | **A** | U | Fork de llama.cpp: posible sustituto directo (N1) con cuantizaciones IQK/Trellis, mejoras CPU y MoE | pendiente |
| 3 | **Ghost Infer** | <https://github.com/affifuddin-hazam/ghost-infer> | R | **A** | U | Afirma 2,3× sobre llama.cpp en MoE que no cabe en 8 GB VRAM, con el mismo GGUF | pendiente |
| 4 | **DynaLM** | <https://github.com/dynalm-project/dynalm> | L/R | **A** | U | Afirma mejoras frente a llama.cpp en CPU, EAGLE-3, caché paginada; GGUF | pendiente |
| 5 | **OpenVINO** (+ OpenVINO GenAI) | <https://github.com/openvinotoolkit/openvino> · <https://docs.openvino.ai/> | L | **A** si Intel | U | CPU/iGPU/NPU Intel; compilación de grafo, INT4/INT8 | pendiente |
| 6 | **KTransformers** | <https://github.com/kvcache-ai/ktransformers> · <https://ktransformers.net/en/docs> | R | A (estudio) / B (uso) | U | Referencia de inferencia heterogénea CPU+GPU y reparto de expertos MoE. Principalmente Linux | pendiente |
| 7 | **Herbert-rs** | <https://github.com/xigh/herbert-rs> | X | A (estudio) | U | Motor desde cero (Rust) sin GGML; KV INT8 + VNNI; Vulkan/Metal/CUDA; afirma ventaja creciente con el contexto | pendiente |
| 8 | **MLC LLM** | <https://github.com/mlc-ai/mlc-llm> · <https://llm.mlc.ai/docs/> | R | B | U | Compilación TVM por dispositivo; Vulkan para AMD/Intel | pendiente |
| 9 | **Golem** | <https://github.com/ThiraSoft/golem> | R | B | U | Go puro, Vulkan, cuantización propia H3G; interesante para AMD | pendiente |
| 10 | **mistral.rs** | <https://github.com/EricLBuehler/mistral.rs> | L/R | B | U | Arquitectura modular servidor/motor; binarios Windows CPU; API compatible OpenAI | pendiente |
| 11 | **Candle** | <https://github.com/huggingface/candle> | X | B (estudio) | U | Framework Rust minimalista: entender tensores, kernels, cuantización | pendiente |
| 12 | **FastLLM** | <https://github.com/ztxz16/fastllm> | R | B | U | Reparto GPU/CPU/NUMA/disco, MoE híbrido, carga directa de safetensors | pendiente |
| 13 | **OpenSet-LLM** | <https://github.com/opensetlabs/openset-llm> | L/X | B | U | CPU extrema con pesos ternarios y especulación. Sus cifras usan un modelo ternario: **no comparables** con Q4 | pendiente |
| 14 | **SGLang** | <https://github.com/sgl-project/sglang> | R | C (técnica) | U | RadixAttention / caché de prefijos: la *idea* es muy relevante para agentes (N3) | pendiente |
| 15 | **Megakernel Zoo** | <https://github.com/dangxingyu/megakernel-zoo> | X | C (estudio) | U | Megakernel por modelo generado por agentes; CUDA de centro de datos. Interés arquitectónico y de metodología (verificación FP64) | pendiente |
| 16 | **HF Transformers · GPTQ** | <https://huggingface.co/docs/transformers/v4.43.2/quantization/gptq> | T | C | U | Referencia de formato de cuantización GPU (comparar con K-quants/IQ, AWQ, INT4 OpenVINO) | pendiente |
| 17 | **LLM-Inference-Handbook** | <https://github.com/h9-tec/LLM-Inference-Handbook> | T | A (lectura) | U | Base teórica para F3 | pendiente |
| 18 | **Awesome Local Inference Recipes** | <https://raytone-lab.github.io/awesome-local-inference-recipes/explore.html> | T | A (lectura) | U | Recopilatorio comunitario de recetas y cifras; separar las que tienen logs de las que no | pendiente |
| 19 | vLLM | <https://github.com/vllm-project/vllm> | R | C (técnica) | G | PagedAttention, *continuous batching*. Orientado a GPU multiusuario | pendiente |
| 20 | ExLlamaV2 / V3 | <https://github.com/turboderp/exllamav2> | R | C | G | Kernels CUDA + formatos EXL2/EXL3. Solo NVIDIA | pendiente |
| 21 | Strata | (ChatGPT: `github.com/StrataEngine/Strata`) | X | C | G | Supuesta caché de expertos MoE | **verificar existencia** |
| 22 | BeeLLama | (ChatGPT: `github.com/BeeLLM/BeeLLama`) | X | C | G | Supuesta inferencia y cuantización | **verificar existencia** |
| 23 | PrismML | (ChatGPT: `github.com/PrismML`) | X | C | G | Supuestos modelos ternarios para CPU | **verificar existencia** |
| 24 | Kipp | (sin enlace) | X | C | G | Supuesta inferencia Qwen3 en C11 desde cero | **verificar existencia** |
| 25 | Synapse | (sin enlace) | X | C | G | Supuesto motor Rust + Zig SIMD + WASM | **verificar existencia** |
| 26 | Basalt, Hibana, ReVolta, TensorFold, Radiance, Infernix | (citados como presentes en el agregador) | X | C | G | Solo seguimiento | **verificar existencia** |

## Fichas (se completan en F1)

Plantilla para cada candidato de prioridad A y B. Copiar y rellenar; no borrar los campos que queden sin dato, marcarlos `?`.

```markdown
### <Proyecto>
- Repositorio / docs:
- Licencia (según fichero LICENSE):            · ¿Compatible con distribución junto a GuarIdA (GPL-3.0)?:
- Lenguaje / dependencias de ejecución:
- Actividad (último commit/release, fecha de consulta):
- SO soportados (Windows / Linux) y cómo se distribuye (binario, pip, compilar):
- Backends: CPU (SIMD) / Vulkan / CUDA / ROCm / SYCL / Metal / NPU:
- Formato de pesos (GGUF, safetensors, propio) y si exige conversión:
- Soporte Qwen3 denso / Qwen3 MoE (y versiones posteriores):
- API de servidor (¿compatible OpenAI? ¿/completion? ¿/tokenize? ¿embeddings?):
- Técnicas clave que declara:
- Benchmarks publicados: hardware, modelo, cuantización, ¿hay logs/script reproducible?:
- Encaje con GuarIdA (nivel N0–N4) y riesgos:
- Decisión F1: probar en F4 / solo estudiar en F3 / descartar (motivo):
```

## Afirmaciones a verificar (registro)

Cifras que circulan y que **no se deben citar como hechos** hasta verificarlas o reproducirlas:

| Proyecto | Afirmación | Fuente declarada | Estado |
|---|---|---|---|
| llm.asm | Supera a llama.cpp CPU (`-ngl 0`) en Qwen3-0.6B Q8_0; arranque del OS en ~74–94 ms; imagen de ~24 KB | Resúmenes de búsqueda (level1techs, impress.co.jp) | pendiente |
| Ghost Infer | Qwen3-30B-A3B: 68,7 t/s frente a 29,5 (llama.cpp) en RTX 2060 SUPER 8 GB + 24 GB RAM, v0.4.0 | README del autor según ChatGPT | pendiente |
| DynaLM | 1,53× sobre llama.cpp en Apple M4 Pro; 1,34–1,41× con EAGLE-3 en EPYC con Qwen3-4B | Web del proyecto según ChatGPT | pendiente |
| Herbert-rs | Qwen3-0.6B Q4, Ryzen 9 7900: 29 frente a 17 t/s con 16k de contexto | README del autor según ChatGPT | pendiente |
| OpenSet-LLM | 17–20 t/s con un modelo ternario de 27B en 8 núcleos / 8 GB RAM | README del autor según ChatGPT | pendiente (y no comparable) |
| Golem | Qwen3-4B Q4_0 Vulkan RX 9070 XT: 180,5 frente a 172 t/s (y peor en 0.6B) | README del autor según ChatGPT | pendiente |
| Megakernel Zoo | Qwen3-8B en H100: 3,83 ms/token frente a 6,09 (SGLang) | README del autor según ChatGPT | pendiente (hardware fuera del alcance de GuarIdA) |
| ik_llama.cpp | Decode en MoE Qwen de ~13 a ~22,7 t/s frente a mainline | Issue comunitaria según ChatGPT | pendiente |
