# 01b · Fuentes complementarias: agregador comunitario, proyectos emergentes y manual teórico

> **Fecha de consulta:** 2026-11-28. Complemento de [01_inventario_candidatos.md](01_inventario_candidatos.md) con tres bloques verificados en Fase 1: (1) el agregador `awesome-local-inference-recipes`, (2) la existencia y URL real de los 12 proyectos sin enlace y 4 modelos recientes citados en la conversación previa, y (3) el mapa de capítulos y aviso legal de `LLM-Inference-Handbook`.

---

## 1. `awesome-local-inference-recipes`

- **Fuente:** <https://raytone-lab.github.io/awesome-local-inference-recipes/explore.html> (snapshot 2026-11-28: **1.328 filas**, 11 columnas: `Compare | Model | Quant / opt. | Engine | Hardware | tok/s | Metric | Cost $ | $/tok/s | Context | Source`).
- **Fiabilidad:** cada entrada marca su origen en 4 niveles (`Official`, `Measured`, `Relayed`, `Claimed`) con fecha y enlace.
- **Motores con más filas:** `Strata` (271), `llama.cpp` (188), `TensorFold` (109), `Unspecified` (99), `vLLM` (84), `oMLX` (58), `MLX` (41), `Project Maya` (40), `SGLang` (35), `TensorRT Edge-LLM` (23), `Basalt` (22), `llama.cpp (PrismML fork)` (18), `Splash` (18), `Radiance` (13), `DFlash` (7), `llama.cpp (tandem.cpp)` (7), `RustingStrata` (6).

### Recetas destacadas para el hardware objetivo de GuarIdA *(afirmaciones de cada fuente)*

| Perfil | Motor | Hardware | Modelo | Cuant. / Opt. | Decode (t/s) | Origen y reproducibilidad |
|---|---|---|---|---:|---|---|
| GPU 16 GB Vulkan | **RustingStrata** (Vulkan) | RX 7800 XT 16 GB | Qwen3.6-35B-A3B | Q4_K_M (22 GB), 8K | 132 | `Claimed` (X, sin log completo) |
| GPU 12 GB | **RustingStrata** (CUDA/Vulkan) | RTX 3060 12 GB + 32 GB RAM | Qwen3.6-35B-A3B | Q2_K_XL | 118 (vs 68 `llama.cpp`) | `Claimed` (Reddit) |
| GPU 12 GB | **RustingStrata** (Vulkan/CUDA) | RTX 3060 12 GB + 32 GB RAM | Qwen3.8-Flash-Next | IQ2_XS | 33 Vulkan / ~36 CUDA | `Claimed` (Reddit; Strata 19–22) |
| GPU 8 GB | **Strata** v0.2.14 | RTX 3060 Ti 8 GB | Qwen3.6 | UD-Q4_K_XL | 50,8 | `Official` (release notes Strata) |
| GPU 12–16 GB | **Strata** v0.2.10/21 | RTX 5070 12 GB / 5070 Ti 16 GB + 64 GB RAM | Qwen3.8-Flash-Next | IQ3_XXS, int8 KV + MTP/DFlash2 | 121–141,3 | `Measured` (**issues GitHub con logs**: Strata#5166/5435/7185) |
| GPU 12–16 GB | **llama.cpp** (PrismML) | RTX 5070 12 GB (Win 11) | Ternary Bonsai 2.5 27B | PTQ1_0 (6,2 GB) + MTP | 133,5 (@32K) | `Claimed` (Reddit/X, `prism-b12178`) |
| GPU 8–16 GB Vulkan | **llama.cpp** (Vulkan) | 2× RX 9060 XT 16 GB | Qwen3.6-35B-A3B | UD-Q4_K_XL + MTP + KV q8_0, 131K | 17,5 | **Reproducible** (`local-ai-registry#551`) |
| APU AMD | **WHIRL** v0.2.5.1 (HIP Win) | Ryzen AI Max+ 395 / 8060S (64 GB UMA) | Ornith-1.5-35B-A3B | MXFP4 GGUF | 106,6 coding (vs 71 `llama.cpp`) | `Measured` (Reddit) |
| APU AMD | **llama.cpp** (vahpetr Vulkan) | Strix Halo 128 GB | Qwen3.8-Flash-Next | `?` | 61 (vs 24–27 stock) | `Measured` (`llama.cpp#30282`) |
| APU AMD | **llama.cpp** b12648 Vulkan | Ryzen 7 255 / Radeon 780M | Inkling 2 Mini (MoE) | Q4 GGUF (16,5 GB) | 14,7 (10,8 @32K) | `Claimed` (X) |
| Intel iGPU | **llama.cpp** Vulkan | Core Ultra X7 358H / Arc B390 iGPU | Inkling 2 Mini (MoE) | Q4_0 (15,1 GB), F16 KV | 16,3 | **Reproducible** (`omarchy-local-ai#126`) |
| Intel Arc | **llama.cpp** Vulkan + FA | Intel Arc Pro B60 24 GB (Win 11) | Qwen3.8-27B | UD-Q4_K_M + **DFlash2** (64K KV) | 53,3 (stock ~16) | **Reproducible** (`edagher92-coder/arc-llm-lab`) |

**Conclusiones del agregador para GuarIdA:**
1. En hardware doméstico heterogéneo (AMD Radeon 780M/890M/8060S, Intel Arc iGPU/dGPU, GPUs 8–16 GB en Windows y Linux), **`llama.cpp` con Vulkan** sigue siendo la base más portátil, y sus mayores aceleraciones provienen de **MTP / DFlash2** y **KV cuantizada `q8_0`**.
2. Para **MoE que exceden la VRAM**, las fichas verificadas en Mini-F1b muestran dos rutas distintas: **`Strata`** ([ficha](01_inventario_candidatos.md#21a-strata-niko1221strata--mini-f1b), MIT, Windows+Linux, CUDA/HIP sin Vulkan) y **`RustingStrata`** ([ficha](01_inventario_candidatos.md#21b-rustingstrata-rustingstudiorustingstrata--mini-f1b), Rust + **Vulkan** + CUDA + GGUF, aunque sin soporte Intel Arc por `shaderFloat64` y bajo licencia *source-available* incompatible con redistribución GPL-3.0).

---

## 2. Verificación de proyectos sin enlace y modelos recientes

### A. Proyectos citados sin enlace (12 de 12 existen; ChatGPT erró algunos slugs)

| Proyecto | URL real verificada | Descripción y encaje para GuarIdA |
|---|---|---|
| **Strata** *(404 en `StrataEngine/Strata`)* | <https://github.com/Niko1221/Strata> + variante Vulkan <https://github.com/RustingStudio/RustingStrata> | Motor Windows+Linux con caché dinámica de expertos MoE (`MIT`, CUDA/HIP sin Vulkan); `RustingStrata` añade Vulkan+CUDA+GGUF en Rust (`RustingStrata 1.0`, sin Intel Arc). **Verificados en Mini-F1b** ([fichas](01_inventario_candidatos.md#21a-strata-niko1221strata--mini-f1b)). |
| **DFlash2** | <https://github.com/z-lab/dflash> · pesos en <https://huggingface.co/z-lab> | Decodificación especulativa **sin pérdida** por difusión en bloques (`MIT`), integrado en `llama.cpp` (PR #27342), `ik_llama.cpp`, `OpenVINO GenAI`, `Strata`, `RustingStrata`, `vLLM` y `SGLang`. **Verificado en Mini-F1b** ([ficha](01_inventario_candidatos.md#24-dflash2-z-labdflash--mini-f1b)). |
| **PrismML** *(0 repos en `github.com/PrismML`)* | <https://github.com/PrismML-Eng/llama.cpp> · <https://huggingface.co/prism-ml> | Fork `llama.cpp` y modelos ternarios (`PTQ1_0`/`PQ2_0`, familia Bonsai). Seguimiento F3. |
| **BeeLLama** *(404 en `BeeLLM/BeeLLama`)* | <https://github.com/Anbeeld/beellama.cpp> | Fork de `llama.cpp` (principalmente CUDA) con KV `KVarN` y DFlash (`BeeLLama-Low`). Seguimiento. |
| **Kipp** | <https://github.com/Polished-Snow/Kipp> | Motor Qwen/Qwen3 en C11 sin dependencias externas (HTTP/JSON propios). Solo curiosidad/estudio. |
| **Synapse** | <https://github.com/eren23/synapse> | Motor modular Rust + kernels SIMD en Zig, Metal, WASM y edge. Seguimiento. |
| **TensorFold** | <https://github.com/ashhart/TensorFold> | Motor nativo en Zig (Metal/CUDA; forks Vulkan/XPU), API OpenAI, especulación exacta. Seguimiento. |
| **Basalt** | <https://github.com/jesdga95/basalt> | Fork de Strata optimizado para NVIDIA Blackwell (formato `.basalt`). Fuera de hardware modesto. |
| **Hibana** | <https://github.com/sharar-project/hibana> | Motor para NVIDIA DGX/RTX Spark (memoria unificada, agentes multiturno). Fuera de hardware modesto. |
| **ReVolta** | <https://github.com/Leonccaa/ReVolta> | Derivado de vLLM para multi-GPU NVIDIA V100 (Volta). Fuera de alcance. |
| **Radiance** | <https://codeberg.org/StillDeadcode/radiance> | Motor C++/HIP para AMD RDNA4 y CPU x86. Seguimiento AMD. |
| **Infernix** | <https://github.com/Wallawalla47/Infernix> | Motor C++/CUDA mono-GPU para RTX 5090 / Blackwell (MoE offload). Fuera de hardware modesto. |

### B. Modelos recientes verificados (4 de 4 existen oficialmente)

| Modelo | URL oficial | Datos verificados |
|---|---|---|
| **Qwen3.6-35B-A3B** | <https://huggingface.co/Qwen/Qwen3.6-35B-A3B> | MoE (~35B totales / ~3B activos), atención híbrida (Gated DeltaNet + Gated Attention), MTP, ctx 262K, foco código agéntico. |
| **Qwen3.8-27B** | <https://huggingface.co/Qwen/Qwen3.8-27B> | Denso ~27B, atención híbrida, control de razonamiento, drafters DFlash2 disponibles. |
| **Qwen3.8-Flash-Next** | <https://huggingface.co/Qwen/Qwen3.8-Flash-Next> | MoE *preview* (125B totales / ~6B activos), Qwen Sparse Attention (QSA), embeddings N-gram, MTP, ctx 256K. |
| **Ternary-Bonsai-2-27B** *(y 2.5)* | <https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf> | Base Qwen3.8-27B, pesos Apache-2.0, cuantización ternaria rotada con Hadamard (~1,72–1,76 bpw, ~6 GB). |

---

## 3. `h9-tec/LLM-Inference-Handbook` — Mapa teórico para F3

> **AVISO LEGAL:** según la API de GitHub, [h9-tec/LLM-Inference-Handbook](https://github.com/h9-tec/LLM-Inference-Handbook) **no declara licencia** (*All Rights Reserved*). **Prohibido copiar, traducir literalmente o reutilizar fragmentos, tablas o código** en GuarIdA; usar exclusivamente como referencia teórica redactando explicaciones propias.

Obra de 32 capítulos. Mapa de consulta para las técnicas de [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md):

- **Fundamentos y *roofline* (Caps. 3–4):** anatomía prefill vs decode y cuello de botella por ancho de banda de memoria.
- **Dimensionado de KV cache (Cap. 5):** fórmula exacta y comparación MHA/MQA/GQA/MLA.
- **FlashAttention y atención dispersa (Caps. 6–7):** *tiling* y *online softmax* (6.1–6.2); atención dispersa NSA/MoBA (Cap. 7).
- **PagedAttention y KV en niveles (Caps. 8 y 10):** KV virtual por bloques (Cap. 8) y *break-even* de offload a RAM/disco (10.2).
- **Caché de prefijos y RadixAttention (Cap. 9 + 21.3 + 28.3):** tráfico agéntico con prefijos repetidos, árboles radix, *cache-aware prompting* (9.3) y precalentamiento.
- **Compresión y cuantización de KV (Cap. 11):** cuantización (11.1), expulsión de tokens (11.2), compartición entre capas (11.3) y criterio de elección (11.4).
- **Cuantización de pesos y trampa de razonamiento (Caps. 13–14):** *outliers* y formatos (Cap. 13) + **Cap. 14 (*The Token Inflation Trap*)**, clave para nuestra puerta de calidad porque las cuantizaciones agresivas pueden alargar el razonamiento y anular la ganancia de velocidad.
- **Decodificación especulativa (Cap. 15 + 20.3):** verificación sin pérdida (15.1), 4 generaciones de drafters —draft, EAGLE, MTP— (15.2) y longitud aceptada media *AL* (15.3).
- **MoE y ejecución local (Caps. 19 y 30):** **19.4 (*MoE off the datacenter: offloading works here*)** y **Cap. 30 (*Edge and Local Inference*)**.
- **Referencia práctica de agente y benchmarks (Caps. 22.4, 23–24, 32.4):** `llama.cpp` como estándar no-datacenter (22.4), benchmarking honesto sin sesgo de caché (Cap. 24) y **caso de estudio de agente interno de código (32.4)**.
