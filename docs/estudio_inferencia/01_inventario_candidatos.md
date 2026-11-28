# 01 · Inventario de candidatos

> **Estado:** **Fase 1 y Mini-F1b cerradas (2026-11-28).** Metadatos, licencias, actividad, SO, backends y soporte verificados contra fuentes primarias (API de GitHub, `README.md`, `releases`, `LICENSE.md` y documentación oficial). Las cifras de rendimiento se mantienen etiquetadas como **afirmaciones del autor** hasta reproducirse en F4. Ver también [01b_agregador_y_manual.md](01b_agregador_y_manual.md) para el agregador `awesome-local-inference-recipes`, los 12 proyectos sin enlace y el índice del `LLM-Inference-Handbook`.

## Leyenda

- **Línea:** `L` = motor ligero (pocos recursos, CPU/iGPU) · `R` = alto rendimiento (CUDA/Vulkan/ROCm) · `X` = experimental o arquitectura especializada · `T` = referencia teórica o recopilatorio.
- **Decisión F1:** `F4` = probar en laboratorio · `F3` = solo estudiar técnicas · `descartar` = fuera de alcance.
- **Nivel GuarIdA:** `N0` exprimir `llama-server` · `N1` binario sustituto compatible · `N2` motor alternativo HTTP · `N3` técnica a reimplementar · `N4` referencia para motor propio.

## Tabla resumen (verificada el 2026-11-28)

| # | Proyecto | Repositorio verificado | Licencia | Win / Lin | Vulkan | GGUF | Nivel | Decisión F1 |
|---|---|---|---|---|---|---|---|---|
| 0 | **llama.cpp** (`llama-server`) | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | Sí / Sí | **Sí** | **Sí** | **N0** | **F4 (Base)** |
| 1 | **llm.asm** | [alesha-pro/llm.asm](https://github.com/alesha-pro/llm.asm) | MIT | No / Sí | No | No (`.asmbin`) | N4 | Descartar (F3 menor) |
| 2 | **ik_llama.cpp** | [ikawrakow/ik_llama.cpp](https://github.com/ikawrakow/ik_llama.cpp) | MIT | Compilar / Sí | **No** | **Sí** (+IQK/Trellis) | N1 parcial + N3 | **F4 (CPU/CUDA)** + F3 |
| 3 | **Ghost Infer** | [affifuddin-hazam/ghost-infer](https://github.com/affifuddin-hazam/ghost-infer) | Apache-2.0 / MIT* | Sí* / Compilar | No (CUDA) | Sí | N2 NVIDIA + N3 | **F3** *(NVRTC EULA)* |
| 4 | **DynaLM** | [dynalm-project/dynalm](https://github.com/dynalm-project/dynalm) | Apache-2.0 | Bin CI / Bin CI | Exp. | **Sí** | N2 exp. + N3 | **F4 (exploratorio)** |
| 5 | **OpenVINO** | [openvinotoolkit/openvino](https://github.com/openvinotoolkit/openvino) | Apache-2.0 | Sí / Sí | No (Intel GPU/NPU) | No (IR) | Base de #5b | Descartar directo |
| 5b | **OpenVINO GenAI** (+ OVMS) | [openvinotoolkit/openvino.genai](https://github.com/openvinotoolkit/openvino.genai) | Apache-2.0 | Sí / Sí | No (Intel GPU/NPU) | Preview (+IR) | N2 Intel + N3 | **F4 (Intel)** + F3 |
| 6 | **KTransformers** | [kvcache-ai/ktransformers](https://github.com/kvcache-ai/ktransformers) | Apache-2.0 | No (WSL2) / Sí | No (CUDA) | Parcial (CPU) | N3 | **F3** |
| 7 | **Herbert-rs** | [xigh/herbert-rs](https://github.com/xigh/herbert-rs) | MIT | No / Compilar | Sí (Lin) | No (HF) | N3 / N4 | **F3** *(sin mant.)* |
| 8 | **MLC LLM** | [mlc-ai/mlc-llm](https://github.com/mlc-ai/mlc-llm) | Apache-2.0 | Nightly / Nightly | **Sí** | No (`q4f16`) | N2 | **F4 (acotado Vulkan)** |
| 9 | **Golem** | [ThiraSoft/golem](https://github.com/ThiraSoft/golem) | MIT | No / Sí | Sí (Lin) | Sí (+H3G) | N3 / N4 | **F3** |
| 10 | **mistral.rs** | [EricLBuehler/mistral.rs](https://github.com/EricLBuehler/mistral.rs) | MIT | CPU / CPU+CUDA | **No** | **Sí** | N2 (CPU/CUDA) | **F4 (CPU/CUDA)** + F3 |
| 11 | **Candle** | [huggingface/candle](https://github.com/huggingface/candle) | MIT / Apache-2.0 | Compilar / Compilar | No | Sí | N4 | Descartar (cubierto por #10) |
| 12 | **FastLLM** | [ztxz16/fastllm](https://github.com/ztxz16/fastllm) | Apache-2.0 | Frágil / Sí | No (CUDA/ROCm) | Parcial | N3 | **F3** (KVMem / MoE) |
| 13 | **OpenSet-LLM** | [opensetlabs/openset-llm](https://github.com/opensetlabs/openset-llm) | MIT | No (WSL2) / Sí | No (CPU) | Solo Bonsai 1-bit | N3 | **F3** |
| 14 | **SGLang** | [sgl-project/sglang](https://github.com/sgl-project/sglang) | Apache-2.0 | No (WSL2) / Sí | No | Sec. CUDA | N3 | **F3** (RadixAttention) |
| 15 | **Megakernel Zoo** | [dangxingyu/megakernel-zoo](https://github.com/dangxingyu/megakernel-zoo) | Apache-2.0 | No / Sí | No (H100/B200) | No | N4 | Descartar |
| 16 | **HF GPTQ** | [HF Transformers GPTQ](https://huggingface.co/docs/transformers/v4.43.2/quantization/gptq) | Ref. | — | — | — | T | Referencia T3 (F3) |
| 17 | **LLM-Inference-Handbook** | [h9-tec/LLM-Inference-Handbook](https://github.com/h9-tec/LLM-Inference-Handbook) | **Sin licencia** | — | — | — | T | Lectura F3 *(no copiar)* |
| 18 | **Awesome Local Inference Recipes** | [raytone-lab.github.io](https://raytone-lab.github.io/awesome-local-inference-recipes/explore.html) | Recopilatorio | — | — | — | T | Verificado ([01b](01b_agregador_y_manual.md)) |
| 19 | **vLLM** | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Apache-2.0 | No (WSL2) / Sí | No | Plugin exp. | N3 | **F3** (PagedAttention) |
| 20 | **ExLlamaV2** | [turboderp-org/exllamav2](https://github.com/turboderp-org/exllamav2) | MIT | Sí / Sí | No | No (EXL2) | — | Descartar *(archivado)* |
| 20b | **ExLlamaV3** | [turboderp-org/exllamav3](https://github.com/turboderp-org/exllamav3) | MIT | Sí / Sí | No (CUDA/ROCm) | No (EXL3) | N3 | **F3** (KV 2–8b, MoE) |
| 21a | **Strata** | [Niko1221/Strata](https://github.com/Niko1221/Strata) | MIT | Sí / Sí | No (CUDA/HIP/SYCL) | Parcial (catálogo) | N2 (GPU ded.) + N3 | **F4 (GPU CUDA/HIP)** + F3 |
| 21b | **RustingStrata** | [RustingStudio/RustingStrata](https://github.com/RustingStudio/RustingStrata) | **No-OSI** (`RustingStrata 1.0`)* | Sí / Sí | **Sí** *(no Arc)* | **Sí** | N2 externo + N3 | **F4 (Vulkan/CUDA)** + F3 |
| 22 | **BeeLLama** | [Anbeeld/beellama.cpp](https://github.com/Anbeeld/beellama.cpp) | `?` | `?` | No (CUDA) | Sí | N3 | Seguimiento ([01b](01b_agregador_y_manual.md)) |
| 23 | **PrismML** (`llama.cpp` fork) | [PrismML-Eng/llama.cpp](https://github.com/PrismML-Eng/llama.cpp) | `?` | Sí / Sí | `?` | Ternario | N3 | Seguimiento ([01b](01b_agregador_y_manual.md)) |
| 24 | **DFlash2** | [z-lab/dflash](https://github.com/z-lab/dflash) | MIT | — | — | Drafter | N0 / N3 | **F3 + F2/F4 vía `llama.cpp`** |
| 25 | Kipp, Synapse, TensorFold, Basalt, Hibana, ReVolta, Radiance, Infernix | Todos verificados existentes (ver [01b](01b_agregador_y_manual.md)) | Varios | Varios | Solo algunos forks | Varios | C | Seguimiento ([01b](01b_agregador_y_manual.md)) |

> \* **Licencias no redistribuibles dentro del paquete GPL-3.0:** **Ghost Infer** tiene código Apache-2.0/MIT pero su instalador Windows empaqueta NVIDIA NVRTC bajo licencia privativa CUDA Toolkit EULA; **RustingStrata** usa la licencia *source-available* **RustingStrata License 1.0** (prohíbe revender/cobrar por el motor como servicio sustituto), incompatible con distribución combinada GPL-3.0 (solo uso externo no empaquetado).  
> **Hallazgo transversal clave de F1 + Mini-F1b:** fuera de `llama.cpp`, casi ningún motor maduro soporta **Windows + Linux + Vulkan (APU/iGPU AMD e Intel) + GGUF + API OpenAI con tool calling**. `RustingStrata` sí cubre Windows + Linux + Vulkan + GGUF + OpenAI, pero exige `shaderFloat64` en Vulkan (**deja fuera Intel Arc**), su CPU-only es solo referencia lenta y su licencia prohíbe empaquetado comercial/GPL-3.0; `Strata` cubre Windows+Linux en GPU dedicada CUDA/HIP (incl. Strix Halo) pero sin Vulkan ni CPU-only. Por eso **N0 (exprimir y actualizar `llama-server`, incluyendo DFlash2/MTP)** y **N3 (importar técnicas)** siguen siendo la prioridad principal.

---

## Fichas verificadas (2026-11-28)

### 0. llama.cpp (`llama-server`) — *Línea base*
- **Repositorio / docs:** `https://github.com/ggml-org/llama.cpp` · `https://llama.app` · `docs/build.md`, `tools/server/README.md`.
- **Licencia:** `MIT` (deps embebidas MIT / dominio público) · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** C/C++ (`ggml`). Binarios oficiales autocontenidos; solo driver del backend (Vulkan/CUDA/etc.).
- **Actividad:** último push `2026-11-28`, **136.470** estrellas; hito estable **`v1.0.0`** publicado el `2026-11-13` + builds nightly `b*`. GuarIdA distribuye actualmente **`b12017`** (`binaries.py`, SHA-256 verificados el 2026-11-15).
- **SO / distribución:** Windows, Linux, macOS, Android, Docker. Binarios oficiales en Releases (`win-vulkan-x64`, `win-cpu-x64`, `ubuntu-vulkan-x64`, `ubuntu-cpu-x64`, CUDA, etc.).
- **Backends:** CPU (SIMD), **Vulkan** (binarios oficiales), CUDA, ROCm/HIP, SYCL, Metal, y **OpenVINO** (`-DGGML_OPENVINO=ON` para Intel CPU/GPU/NPU).
- **Formato de pesos:** GGUF nativo (K-quants, IQ-quants, MXFP4, etc.) sin conversión.
- **Soporte Qwen3:** Sí — Qwen3 denso, Qwen3 MoE, Qwen3.5, Qwen3.6 y sucesores (con soporte reciente de MTP y DFlash2).
- **API de servidor:** Compatible OpenAI (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, tool calling, gramáticas GBNF), `/completion`, `/tokenize`, `/detokenize`, `/embeddings`, `/slots`, caché de prompts/prefijos.
- **Técnicas clave:** Flash Attention (`-fa`), KV cuantizada (`-ctk/-ctv`), reutilización de caché (`--cache-reuse`), slots guardables (`--slot-save-path`), lookup (`--lookup-cache`), modelo borrador (`-md`), reparto MoE (`-ot`, `--n-cpu-moe`).
- **Encaje y riesgos:** **Nivel N0** (línea base obligatoria). Al actualizar de `b12017` a `v1.0.0`+ revisar flags deprecados eliminados (p. ej. `--defrag-thold`).
- **Decisión F1:** **Probar en F2/F4** (línea base + exprimir flags N0 y valorar actualización a `v1.0.0`+ con soporte MTP/DFlash2).

### 1. alesha-pro/llm.asm
- **Repositorio / docs:** `https://github.com/alesha-pro/llm.asm` (`01-qwen3-inference`, `02-baremetal-os`, `03-minigpt-train`, `04-ring1-kernel-surgeon`).
- **Licencia:** `MIT` · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** 100 % ensamblador x86-64 NASM (17.252 líneas en Fases 1–3); cero dependencias en ejecución (ELF sin `libc`). Exportación de pesos requiere Python+NumPy.
- **Actividad:** creado `2026-11-25`, último push `2026-11-27`, sin releases publicadas, **2.346** estrellas.
- **SO / distribución:** **Solo Linux x86-64** (Fase 1) y bare-metal/QEMU/ISO (Fase 2). Sin Windows; solo compilar desde fuente.
- **Backends:** Solo CPU x86-64 **AVX2 + FMA + F16C**. Sin Vulkan, CUDA, ROCm, Metal ni ARM.
- **Formato de pesos:** Formato propietario `.asmbin` v2 (613,66 MiB, alineado a 64 B para `mmap` zero-copy); exige conversión desde safetensors BF16. Sin GGUF en Fases 1–2.
- **Soporte Qwen3:** **Únicamente `Qwen3-0.6B` denso** con dimensiones fijas (`ctx=2048` por defecto). Sin otros tamaños ni MoE.
- **API de servidor:** **Ninguna** (CLI/REPL o VGA/PS2/COM1).
- **Técnicas clave:** Cuantización de activaciones Q8_0 por matmul (`FAST_Q8=1`) + micro-kernel INT8×INT8 AVX2 con escalas FP16 y prefetch; matrices fusionadas QKV y gate+up; hilos lock-free `clone/futex`; páginas gigantes de 2 MiB en bare-metal. **Limitación crítica:** prefill **GEMV token a token** (sin GEMM por lotes).
- **Benchmarks publicados:** *Afirmaciones del autor* (EPYC 7642 47C, `Qwen3-0.6B Q8_0`, `pp34/tg64`): decode 20,70–125,86 t/s (`+18%` a `+35,6%` vs `llama.cpp -ngl 0`), **pero en prefill `pp34` es ~7× más lento** (`26,7–160,8` vs `56–1113 t/s` de `llama-bench`); bare-metal arranca en 73–94 ms. Sin script/logs de la comparativa contra `llama.cpp`.
- **Encaje y riesgos:** **Nivel N4** (curiosidad / lectura puntual N3 del micro-kernel GEMV Q8_0 AVX2). Bloqueado por falta de Windows, Vulkan, HTTP, GGUF, modelos útiles y prefill lento.
- **Decisión F1:** **Descartar para F4** (referencia menor en F3).

### 2. ikawrakow/ik_llama.cpp
- **Repositorio / docs:** `https://github.com/ikawrakow/ik_llama.cpp` · Wiki: `https://github.com/ikawrakow/ik_llama.cpp/wiki`.
- **Licencia:** `MIT` · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** C/C++ (fork de `llama.cpp` divergido desde ago-2024).
- **Actividad:** último push `2026-11-27`, **3.428** estrellas; **sin releases con binarios** (solo pre-release vacía `t0002` de jul-2025).
- **SO / distribución:** Linux, Windows y Android (Termux). **Sin binarios oficiales** (solo compilar desde fuente o Docker Linux en `ghcr.io`).
- **Backends:** **Solo CPU** (AVX2, AVX-VNNI, AVX-512 exigiendo flags `HAVE_FANCY_SIMD`, ARM NEON) y **CUDA**. **Aviso explícito del autor: sin soporte ni mantenimiento para Vulkan, ROCm ni Metal.**
- **Formato de pesos:** GGUF estándar (`Q4_K_M`, etc., aviso de fallos en GGUFs Unsloth `_XL` con `f16`) + cuantizaciones propias **IQK**, **Trellis** (`IQ1_KT..IQ4_KT`, Gyro) y ternarias Prism (exigen re-cuantizar o descargar GGUFs específicos).
- **Soporte Qwen3:** Muy amplio — Qwen3 denso/MoE/VL, Qwen3-Next, Qwen3.5/3.6/3.8 (con MTP), Qwen3.8-Flash-Next y `qwen4exp`.
- **API de servidor:** `llama-server` con API OpenAI (`/v1/chat/completions`, `/v1/embeddings`, `/v1/responses`), `/completion`, `/tokenize`, `/memory`, `/metrics`. **No es drop-in transparente** de `b12017` por >2 años de divergencia en flags y ausencia de Vulkan.
- **Técnicas clave:** Cuantizaciones IQK/Trellis, repacking (`-rtr`, cuidado: en híbrido CPU/CUDA degrada prefill con K-quants), GEMM CPU optimizado, caché dinámica de expertos MoE (`--moe-cache-mib`, ClassLRU), combine CPU de expertos, especulación **MTP / DFlash2 / DSpark / ngram / suffix**, FlashMLA, **Hadamard KV** y `Q8_KV`/`Q4_0` KV.
- **Benchmarks publicados:** Sin tablas completas en README (solo mejoras relativas en PRs y comparativas en Wiki: p. ej. ~2,8–3,3× CPU `pp` vs mainline en ene-2025). Incluye `llama-bench` y `sweep-bench`.
- **Encaje y riesgos:** **Nivel N1 parcial (solo CPU-only / CUDA)** + **N3** (muchísimas técnicas de alto valor). No cubre Vulkan/APU ni tiene binarios Windows oficiales.
- **Decisión F1:** **Probar en F4 (perfiles CPU-only / CUDA)** y **estudiar a fondo en F3** (caché MoE, Hadamard KV, suffix/ngram, MTP/DFlash2).

### 3. Ghost Infer (`affifuddin-hazam/ghost-infer`)
- **Repositorio / docs:** `https://github.com/affifuddin-hazam/ghost-infer`.
- **Licencia:** Dual `Apache-2.0 OR MIT` en código fuente · **Compatible GPL-3.0:** Código sí; **el instalador Windows empaqueta NVIDIA NVRTC bajo CUDA Toolkit EULA (no redistribuible con GPL-3.0)**.
- **Lenguaje / dependencias:** Rust (binario único ~3,8 MB) + NVIDIA NVRTC (compila kernels JIT al primer arranque) + CPU AVX2.
- **Actividad:** creado `2026-10-27`, último push `2026-11-24`, release `v0.5.0` (`2026-11-24`, solo `GhostSetup-0.5.0.exe`), **273** estrellas.
- **SO / distribución:** Windows 10/11 (instalador no firmado o compilar) y Linux (desde v0.5.0, solo compilar + CUDA Toolkit).
- **Backends:** **Exclusivo NVIDIA CUDA (GTX 10+)** + CPU AVX2 para expertos MoE no cacheados. Sin Vulkan, ROCm, Metal ni modo solo-CPU.
- **Formato de pesos:** GGUF nativo (`Q3_K..Q8_0`, `IQ2`, `Q2_0`/`PTQ1_0` Bonsai; `Q4_0` en roadmap).
- **Soporte Qwen3:** Sí — Qwen3 denso (4B, 8B), Qwen3 MoE (30B-A3B, Coder-30B-A3B), Qwen3-Coder-Next 80B, Qwen3.5 y Qwen3.6-35B-A3B.
- **API de servidor:** OpenAI `POST /v1/chat/completions` (streaming y tool calls, aún sin *constrained decoding*) + `GET /api/speed`. `/completion`, `/tokenize`, `/embeddings`: `?`.
- **Técnicas clave:** Offloading MoE GPU+CPU (atención + expertos calientes en VRAM, resto en hilos CPU fijados a núcleo); 1 **CUDA Graph** por capa con enrutado en GPU; Tensor Cores en atención larga; KV 4-bit (`--kv q4`); retención de hasta 5 conversaciones en RAM; **speculative decoding exacto por *lookup*** (activo por defecto en GPU) o `--draft`.
- **Benchmarks publicados:** *Afirmaciones del autor* (RTX 2060 SUPER 8 GB + Ryzen 5 3600 + 24 GB RAM vs `llama.cpp b11747`): Qwen3-30B-A3B **`i1-Q3_K_M`** 68,7 vs 29,5 t/s; Qwen3.6-35B-A3B `i1-Q3_K_M` 80,5 vs 39,5 t/s (49,1 t/s tras 64K ctx); Qwen3-8B 75,3 vs 64,7 t/s. Sin logs descargados.
- **Encaje y riesgos:** **Nivel N3** (lookup exacto para edición de código, caché MoE GPU+CPU, retención de sesiones en RAM) / N2 solo NVIDIA. Excluye Vulkan/CPU-only y tiene fricción legal con NVRTC.
- **Decisión F1:** **Solo estudiar en F3**.

### 4. DynaLM (`dynalm-project/dynalm`)
- **Repositorio / docs:** `https://github.com/dynalm-project/dynalm` · `https://dynalm.in`.
- **Licencia:** `Apache-2.0` (incluye kernels CPU de `ggml`; revisar `THIRD_PARTY_LICENSES.md`) · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** C++20, binario único sin Python/PyTorch.
- **Actividad:** creado `2026-10-03`, último push `2026-11-05`, release `v0.6.0` (`2026-11-05`), **4** estrellas.
- **SO / distribución:** **Binarios precompilados** para Windows x64 (CPU y Vulkan), Windows ARM64, Linux x64 (CPU y Vulkan), Linux ARM64, macOS Metal y Docker (con `SHA256SUMS` y SBOM). **Matiz crítico:** solo Apple M4 Pro está *Verified* con modelos reales; Windows/Linux solo *CI-tested* sin modelos; Vulkan probado en CI solo con `lavapipe`.
- **Backends:** CPU (AVX2/AVX-512/VNNI/AMX/NEON/SME; en `--mode auto` usa `ggml` en x86-64 y kernels propios en M4 SME), Metal (Verified), **Vulkan (Experimental)**, CUDA (Experimental).
- **Formato de pesos:** GGUF (recomendado `Q4_K_M`, sin `IQ1..IQ3` ni `MXFP4`), SafeTensors, GPTQ, AWQ. EAGLE-3 requiere cabeza en `safetensors`.
- **Soporte Qwen3:** Qwen3 denso y MoE (CPU, Metal, Vulkan). Posteriores: `?`.
- **API de servidor:** OpenAI `/v1/chat/completions` (con `response_format` JSON Schema), `/v1/completions`, `/v1/models`, `/health`, `/metrics`. **Sin tool calling todavía** (en roadmap), sin motor Jinja, sin `/tokenize` ni `/embeddings` listados.
- **Técnicas clave:** Continuous batching, KV paginada, *prefix sharing*, **`--prompt-cache DIR` persistente en disco**, **EAGLE-3** exacto, **`--experts-from-disk`** para MoE con prefetch, `dynalm autotune`.
- **Benchmarks publicados:** *Afirmaciones del autor*: M4 Pro CPU (SME) 1,53× media geométrica vs llama.cpp y 2,7–2,9× menos RAM; EPYC Zen 2 AVX2 (*uncontrolled*, `Q4_K_M`, 512→128 vs `llama.cpp b11695`): 1,07–1,17× sin draft y **1,34–1,41× con EAGLE-3** en Qwen3-4B/8B; **sin datos en Windows ni Vulkan real**.
- **Encaje y riesgos:** **Nivel N2 exploratorio** + **N3**. Bloqueante hoy para producción: falta de tool calling y madurez mínima (4 estrellas, Windows/Vulkan sin validar con modelos reales).
- **Decisión F1:** **Probar en F4 (exploratorio)** en CPU Windows/Linux y Vulkan real para validar `--prompt-cache`, consumo de RAM y EAGLE-3.

### 5 / 5b. OpenVINO (`openvinotoolkit/openvino`) y OpenVINO GenAI (`openvino.genai` + OVMS)
- **Repositorio / docs:** `https://github.com/openvinotoolkit/openvino` · `https://github.com/openvinotoolkit/openvino.genai` · `https://github.com/openvinotoolkit/model_server` (OVMS) · `https://docs.openvino.ai/2026/`.
- **Licencia:** `Apache-2.0` · **Compatible GPL-3.0:** Sí. **Advertencia offline/privacidad:** OpenVINO tiene **telemetría GA4 activa por defecto** (requiere `opt_in_out --opt_out`).
- **Lenguaje / dependencias:** C++ con bindings Python (`>=3.11`), C y Node.js; sin PyTorch en ejecución (exportar IR sí usa `optimum-cli`).
- **Actividad:** muy alta — `openvino` último push `2026-11-28`, `2026.4.1`, **12.975** estrellas; `openvino.genai` último push `2026-11-27`, `2026.4.1.0`, **631** estrellas.
- **SO / distribución:** Windows, Linux, macOS (`pip install openvino-genai`, C++ archives; OVMS ofrece binario `ovms.exe` en Windows y paquete Linux).
- **Backends:** CPU x86-64 (Intel y AMD: AVX2/AVX-512/AMX) y ARM64; **GPU Intel** (iGPU y Arc vía OpenCL/Level Zero); **NPU Intel** (Core Ultra vía NPUW). **Sin Vulkan, sin GPU AMD, sin NVIDIA CUDA.**
- **Formato de pesos:** Principal **OpenVINO IR** INT4/INT8 (exige conversión o modelos `-int4-ov` de HF). **GGUF directo en preview** (`Q4_0`, `Q4_K_M`, `Q6_K`, `Q8_0` en CPU/GPU Intel).
- **Soporte Qwen3:** Muy completo — Qwen3 denso (0.6B–32B), Qwen3 MoE (`30B-A3B`), Qwen3-Omni, Qwen3-Next, Qwen3.5 (con MTP) y Qwen3.6 (con DFlash).
- **API de servidor:** `openvino.genai` es librería; el servidor HTTP es **OVMS**, compatible OpenAI (`/v1/chat/completions`, `/v3/completions`, `/v3/embeddings`, `/v3/tokenize`).
- **Técnicas clave:** Compilación/optimización de grafos, PagedAttention + **prefix caching**, **sparse attention en prefill (`Tri-shape` / `XAttention`)**, **KV cache token eviction**, especulación (EAGLE-3, MTP, DFlash), `xgrammar`.
- **Benchmarks publicados:** Sin cifras en README; incluye scripts reproducibles (`tools/llm_bench` con métricas GPU Windows y `tools/who_what_benchmark` vs `llama.cpp`).
- **Encaje y riesgos:** **Nivel N2 (solo perfil Intel: CPU/iGPU/NPU)** + **N3** (XAttention/Tri-shape, KV eviction). Nótese que `llama.cpp` también ofrece `-DGGML_OPENVINO=ON`. Riesgo: cero aceleración en GPUs AMD/NVIDIA y telemetría por defecto.
- **Decisión F1:** **Probar en F4 en hardware Intel** (GGUF directo vs IR INT4 y OVMS con prefix caching) + **estudiar en F3** sparse prefill y KV eviction. Descartar `openvino` core como motor autónomo.

### 6. KTransformers (`kvcache-ai/ktransformers`)
- **Repositorio / docs:** `https://github.com/kvcache-ai/ktransformers` · `https://kvcache-ai.github.io/ktransformers/`.
- **Licencia:** `Apache-2.0` · **Compatible GPL-3.0:** Código sí; en la práctica atado a CUDA/PyTorch/`sglang-kt`.
- **Lenguaje / dependencias:** Python 3.11/3.12 + C++/CUDA (`kt-kernel`), CUDA 12.8, PyTorch 2.9.1, `sglang-kt`, `transformers-kt` (incompatible con `transformers` estándar en el mismo entorno).
- **Actividad:** último push `2026-11-26`, release `v0.7.2` (`2026-10-15`), **19.709** estrellas.
- **SO / distribución:** **Solo Linux x86-64** (`manylinux_2_35`, `glibc 2.35+`). El soporte Windows antiguo fue archivado en `archive/`; en Windows requiere WSL2.
- **Backends:** CUDA SM 80+ (principal) + CPU (AMX, AVX-512 incl. AMD, y AVX2 vía Llamafile). Sin Vulkan ni CPU-only doméstico.
- **Formato de pesos:** Safetensors (BF16, FP8, MXFP4, INT4) y GGUF en CPU vía Llamafile.
- **Soporte Qwen3:** Qwen3 MoE (`30B-A3B`, `Coder-Next`, `VL-30B-A3B`), Qwen3-Next, Qwen3.5 MoE.
- **API de servidor:** Delegada en **SGLang** (`sglang-kt`, compatible OpenAI).
- **Técnicas clave:** Reparto dinámico CPU–GPU de expertos MoE calientes/fríos NUMA-aware; **prefix cache de 3 niveles (GPU–CPU–Disco)**.
- **Benchmarks publicados:** *Afirmaciones del autor* solo en GPUs grandes (8×L20, RTX 4090 24 GB + 382 GB RAM) sin logs reproducibles en README.
- **Encaje y riesgos:** **Nivel N3** (scheduling MoE y caché de prefijos en 3 niveles). Inviable como motor de GuarIdA (sin Windows nativo, sin Vulkan, stack pesado).
- **Decisión F1:** **Solo estudiar en F3**.

### 7. Herbert-rs (`xigh/herbert-rs`)
- **Repositorio / docs:** `https://github.com/xigh/herbert-rs` · **Aviso en README: ya no está mantenido** (reescritura en repos separados por backend, hoy solo Qwen3.5 en BF16/F16 sin Q4/INT8).
- **Licencia:** `MIT` · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** Rust + ensamblador x86-64 (`.S`) + shaders GLSL/Metal, sin GGML.
- **Actividad:** último push `2026-11-01`, sin releases, **47** estrellas (sin mantenimiento).
- **SO / distribución:** Linux x86-64 y macOS Apple Silicon (solo compilar). **Sin Windows.**
- **Backends:** CPU (AVX-512 VNNI/BF16/Q4, AVX2), Vulkan (Linux, 31 shaders GLSL con *cooperative matrix*), Metal. **Sin CUDA en este repo** (solo en la reescritura).
- **Formato de pesos:** Snapshots safetensors de Hugging Face (**sin GGUF**).
- **Soporte Qwen3:** Qwen3 denso (0.6B–32B), Qwen3 MoE (30B-A3B) y Qwen3-VL.
- **API de servidor:** **Solo Anthropic Messages API** (`POST /v1/messages`), `POST /v1/tokenize`, `/v1/metrics`. **Sin API OpenAI** ni embeddings.
- **Técnicas clave:** Diseño *decode-first*, **KV cache INT8 + kernels AVX-512 VNNI** en ensamblador, nibbles Q4 pre-intercalados con huge pages, *batched expert dispatch* MoE, Vulkan *cooperative matrix*. Sin prefix caching declarado.
- **Benchmarks publicados:** *Afirmaciones del autor* (Ryzen 9 7900 AVX-512, sin logs descargados): Qwen3-0.6B Q4 decode supera a `llama.cpp` de 1k a 16k ctx (`29 vs 17 t/s` a 16k), **pero en prefill denso es 1,5–2× más lento** (`751 vs 1057 t/s`).
- **Encaje y riesgos:** **Nivel N3 / N4**. Sin mantenimiento, sin Windows, sin GGUF, sin OpenAI y prefill lento.
- **Decisión F1:** **Solo estudiar en F3** (KV INT8+VNNI, layout Q4 y Vulkan *cooperative matrix*).

### 8. MLC LLM (`mlc-ai/mlc-llm`)
- **Repositorio / docs:** `https://github.com/mlc-ai/mlc-llm` · `https://llm.mlc.ai/docs/`.
- **Licencia:** `Apache-2.0` · **Compatible GPL-3.0:** Sí (con Vulkan usa driver del sistema).
- **Lenguaje / dependencias:** Python + motor C++ (`MLCEngine`) compilado con Apache TVM (`tvm.dll`), FastAPI/uvicorn, `git-lfs`.
- **Actividad:** último push `2026-11-21`, **23.414** estrellas, pero **sin releases estables desde `v0.1.dev0` (2023-04-29)** — todo se distribuye por *nightlies* en `mlc.ai/wheels`.
- **SO / distribución:** Windows, Linux, macOS, móvil, Web vía pip wheels nightly (incidencias recurrentes en Windows con `tvm.dll` / `WinError 1114`).
- **Backends:** **Vulkan** (AMD, Intel, NVIDIA en Win/Lin), CUDA, ROCm, Metal, OpenCL/WebGPU. **NO soporta inferencia en CPU** (el sufijo `-cpu` de las wheels significa "sin CUDA/ROCm", ejecuta en Vulkan/Metal).
- **Formato de pesos:** Formato propio MLC (`q4f16_1`, etc.); **sin GGUF**. Exige conversión + compilación de librería `.dll`/`.so` por dispositivo (o JIT local).
- **Soporte Qwen3:** Sí — Qwen3 denso y `qwen3_moe`. Posteriores: `?`.
- **API de servidor:** `mlc_llm serve` compatible OpenAI (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`). `/tokenize`: `?`.
- **Técnicas clave:** Compilación end-to-end TVM (shaders SPIR-V nativos para Vulkan), PagedKVCache, **prefix caching**, continuous batching, especulación, **XGrammar**.
- **Benchmarks publicados:** Sin cifras en README ni benchmarks Vulkan domésticos (solo H100 en blog).
- **Encaje y riesgos:** **Nivel N2** (solo para medir si TVM+Vulkan supera a `llama-server` Vulkan). Riesgos altos: sin CPU, sin GGUF, exige compilar por hardware y solo hay nightlies.
- **Decisión F1:** **Probar en F4 (acotado a Vulkan AMD/Intel)** con un Qwen3 preconvertido `q4f16_1`.

### 9. Golem (`ThiraSoft/golem`)
- **Repositorio / docs:** `https://github.com/ThiraSoft/golem`.
- **Licencia:** `MIT` · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** Go puro sin CGO (`CGO_ENABLED=0`), binario estático ~12 MB; Vulkan compute cargado dinámicamente vía `purego`.
- **Actividad:** creado `2026-08-20`, último push `2026-11-22`, release `v0.46.0` (`2026-10-21`, 1 mes detrás de `main`), **3** estrellas (código escrito por agentes IA bajo revisión humana).
- **SO / distribución:** Binarios estáticos solo para **Linux y macOS**. **Sin soporte ni binarios Windows.**
- **Backends:** CPU (AVX2 / NEON en ensamblador Go) y **Vulkan** (Linux). Sin CUDA, ROCm, Metal ni NPU.
- **Formato de pesos:** GGUF nativo (K-quants, `Q4_0`, Bonsai `PQ2_0`/`PTQ1_0`) + formato propio `.golem` (**H3G/H4G** trellis, exige conversión + calibración desde BF16).
- **Soporte Qwen3:** Qwen3 denso (0.6B, 4B) y Qwen3.8-27B (con MTP). **Qwen3 MoE no documentado** (MoE solo en Gemma 4 26B A4B y nomic-embed).
- **API de servidor:** `golem-server` compatible OpenAI (tool calls, JSON Schema, GBNF, embeddings, continuous batching).
- **Técnicas clave:** **Offloading MoE en memoria host direccionable por GPU con caché selectiva en VRAM** (`GOLEM_MOE_EXPERTS_HOST=1`), MTP self-drafting, cuantización trellis H3G/H4G, enlace Vulkan sin CGO.
- **Benchmarks publicados:** *Afirmaciones del autor* en RX 9070 XT Vulkan vs `llama.cpp b9603` en `Q4_0` (sin logs): Qwen3-4B gana ligeramente en decode (`180,5 vs 172,0`) **pero pierde en prefill `pp512` (`5977 vs 7117`)**, y pierde en Qwen3-0.6B.
- **Encaje y riesgos:** **Nivel N3 / N4** (offloading MoE en memoria host/GTT, trellis H3G, Vulkan sin CGO). Sin Windows, sin Qwen3 MoE, prefill más lento y 3 estrellas.
- **Decisión F1:** **Solo estudiar en F3**.

### 10. mistral.rs (`EricLBuehler/mistral.rs`)
- **Repositorio / docs:** `https://github.com/EricLBuehler/mistral.rs` · `https://docs.mistralrs.dev/`.
- **Licencia:** `MIT` · **Compatible GPL-3.0:** Sí (evitando redistribuir runtimes CUDA privativos en el paquete GPL-3.0).
- **Lenguaje / dependencias:** Rust (sobre `candle`), binarios standalone y SDK Python (`pip install mistralrs`).
- **Actividad:** muy activo — último push `2026-11-20`, release `v0.9.5` (`2026-10-19`), **7.872** estrellas.
- **SO / distribución:** **Windows x64 binario oficial solo CPU**; Linux binarios oficiales CPU y CUDA (`sm80+`, excluye RTX 20xx/GTX 16xx) + Docker; macOS binario Metal.
- **Backends:** CPU (Candle + MKL/Accelerate), CUDA (`sm80+` en releases Linux), Metal. **Sin Vulkan, sin ROCm, sin SYCL.**
- **Formato de pesos:** **GGUF directo**, safetensors (con cuantización al vuelo ISQ / formato UQFF), GPTQ, AWQ, HQQ, FP8, NVFP4.
- **Soporte Qwen3:** Completo — Qwen3 denso, MoE, VL, Coder-Next y Qwen3.8-Flash-Next.
- **API de servidor:** Compatible OpenAI (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, Responses API, tool calling con gramática) + Anthropic Messages API (`count_tokens`), `/metrics`, Web UI, reporte de `cached prompt tokens`.
- **Técnicas clave:** Continuous batching, PagedAttention (CUDA/Metal, no CPU), **prefix caching**, *chunked prefill*, ISQ / UQFF / *per-layer topology*, DFlash especulativo, arquitectura modular servidor/motor.
- **Benchmarks publicados:** *Afirmaciones del autor* solo en GPUs datacenter NVIDIA (GB10, B200, H100) con Gemma 4. **Sin benchmarks en CPU ni GPU doméstica.**
- **Encaje y riesgos:** **Nivel N2 (CPU / Linux CUDA `sm80+`)** + **N3** (arquitectura modular, prefix caching, topología por capa). Sin Vulkan ni CUDA Windows.
- **Decisión F1:** **Probar en F4 (acotado a CPU y, si aplica, Linux CUDA)** + **estudiar en F3** su arquitectura modular.

### 11. Candle (`huggingface/candle`)
- **Repositorio / docs:** `https://github.com/huggingface/candle` · `https://huggingface.github.io/candle/`.
- **Licencia:** Dual `MIT / Apache-2.0` · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** Rust (framework ML tipo PyTorch, solo crates `cargo`, sin servidor ni binarios).
- **Actividad:** último push `2026-11-27`, `v0.11.1` en crates.io, **21.438** estrellas.
- **Backends:** CPU (+MKL/Accelerate), CUDA, Metal, WASM. **Sin Vulkan** (ROCm solo en PRs).
- **Formato / Qwen3 / API:** Lee GGUF y safetensors; soporta Qwen3 denso y MoE; **sin servidor HTTP**.
- **Encaje y decisión F1:** **Nivel N4 — Descartar para F4** (su uso práctico como motor LLM en Rust ya se evalúa a través de `mistral.rs`).

### 12. FastLLM (`ztxz16/fastllm`)
- **Repositorio / docs:** `https://github.com/ztxz16/fastllm`.
- **Licencia:** `Apache-2.0` (paquetes portables/wheels incluyen CUDA/cuBLAS/NCCL y `ftllmdepend` en ModelScope) · **Compatible GPL-3.0:** Código sí; no redistribuir binarios con CUDA/ModelScope.
- **Lenguaje / dependencias:** Núcleo C++ sin PyTorch obligatorio + CLI/servidor Python (`ftllm`, Python ≥3.10).
- **Actividad:** último push `2026-11-27`, release `v1.9.2` (`2026-11-15`), **5.135** estrellas.
- **SO / distribución:** Linux x64 (wheel `manylinux_2_31` y portable con Electron+CUDA; CPU-only y ROCm exigen compilar). **Windows frágil:** sin assets en Releases, exige `ftllmdepend` desde ModelScope y `--auto` es solo Linux CUDA.
- **Backends:** CUDA (principal, `SM60..SM120`), ROCm (rama separada, compilar), CPU (compilar). **Sin Vulkan.**
- **Formato / Qwen3 / API:** Safetensors directo, AWQ, EXL3 y **GGUF solo parcial** ("GGUF adaptados"). Soporta Qwen3/3.5/3.6/3.8/3.8-Flash-Next. API OpenAI (`/v1/chat/completions`, Responses) y Anthropic.
- **Técnicas clave:** Híbrido GPU/CPU/NUMA/disco; caché LRU de expertos en VRAM y en disco; **KVMem** (KV cache jerárquico con conjunto de trabajo en GPU, respaldo en RAM y recuperación *pre-RoPE mean-K*).
- **Benchmarks publicados:** Sin cifras en README (remite a `docs/benchmark.md`; validación CUDA física en NVIDIA H20).
- **Encaje y decisión F1:** **Nivel N3 — Solo estudiar en F3** (especialmente **KVMem** y caché multinivel de expertos).

### 13. OpenSet-LLM (`opensetlabs/openset-llm`)
- **Repositorio / docs:** `https://github.com/opensetlabs/openset-llm`.
- **Licencia:** `MIT` (pesos Bonsai Apache-2.0) · **Compatible GPL-3.0:** Sí.
- **Lenguaje / dependencias:** Parches C/C++ sobre el **fork PrismML de `llama.cpp`** (`e3de715`) + tooling Python.
- **Actividad:** creado `2026-11-13`, último push `2026-11-27`, release `v0.3.4` (`2026-11-27`), **2.237** estrellas.
- **SO / distribución:** **Solo Linux x86-64** (binario `.tar.gz`, Docker, compilar). **Sin Windows nativo** (solo WSL2).
- **Backends:** **Solo CPU x86-64** (ruta rápida **AVX-512 VNNI + VBMI**; ruta AVX2 más lenta). Sin GPU/Vulkan.
- **Formato / Qwen3 / API:** **Únicamente un modelo**: `Ternary-Bonsai-2-27B` (Qwen3.8-27B ternario `PTQ1_0` + injerto de cabeza MTP; ~6,2 GB). API OpenAI (`/v1/chat/completions`, `/health`).
- **Técnicas clave:** Kernels ternarios AVX-512/AVX2 con reempaquetado en arranque; especulación MTP; **atención fusionada CPU**; ***agent-loop resume*** (guarda hasta 8 estados de prefijo en disco para reanudar desde la divergencia); KV cuantizada opt-in `--kv8`/`--kv6`/`--kv5` (`kv5/6` solo AVX-512).
- **Benchmarks publicados:** *Afirmaciones del autor* (Bonsai-2-27B `PTQ1_0` + MTP): 17–20 t/s en Xeon Ice Lake 8 cores / 8 GB a **4k ctx** con **AVX-512**; **en AVX2 baja a 5,8–7,2 t/s** (7,2–8,7 con `--spec`, sin medir en CPUs domésticas reales) y **a 16k ctx en 8 GB baja a 7,98 t/s**. Parcialmente reproducible (`bench/`, pero sesión de agente no publicada).
- **Encaje y decisión F1:** **Nivel N3 — Solo estudiar en F3** (*agent-loop resume* en disco, atención fusionada CPU y KV 5/6/8-bit sobre `llama-server`).

### 14. SGLang (`sgl-project/sglang`) y 19. vLLM (`vllm-project/vllm`) — *Referencia técnica*
- **Licencia:** Ambos `Apache-2.0` · **Actividad:** altísima (último push `2026-11-28`; 39.145 y 97.729 estrellas; vLLM `v0.34.0`).
- **Limitaciones para GuarIdA:** **Ninguno soporta Windows nativo** (solo Linux/WSL2 y macOS), **ninguno soporta Vulkan**, ambos dependen de un stack pesado Python+PyTorch, sus backends CPU apuntan a servidores (Xeon AMX/AVX-512 en SGLang), y el soporte GGUF es secundario/experimental (`vllm-gguf-plugin` en vLLM, CUDA en SGLang).
- **Valor para F3 (Nivel N3):** **RadixAttention** (árbol radix de prefijos KV en SGLang) y **PagedAttention + chunked prefill** (vLLM).
- **Decisión F1:** **Solo estudiar en F3**.

### 15. Megakernel Zoo (`dangxingyu/megakernel-zoo`)
- **Licencia:** `Apache-2.0` · **Actividad:** creado `2026-11-16`, último push `2026-11-23`, 66 estrellas, sin releases.
- **Alcance:** **Solo Linux + CUDA 13.x en NVIDIA H100 (`sm_90a`) y B200 (`sm_100a`)**, sin GGUF, un megakernel compilado por cada par *(checkpoint, GPU)* generado por agentes con puerta de verificación contra referencia **FP64**. La cifra `3,83 ms/tok` en Qwen3-8B H100 es Track B (almacenamiento propio lossless, batch 1, `ctx <= 2048`; Track A es `5,13 ms` vs `6,09 ms` SGLang).
- **Decisión F1:** **Descartar** (solo conservar la metodología de verificación numérica como referencia).

### 20 / 20b. ExLlamaV2 (`turboderp-org/exllamav2`) y ExLlamaV3 (`turboderp-org/exllamav3`)
- **Licencia:** `MIT` · **Estado:** **ExLlamaV2 está archivado por el autor** (último push `2026-03-04`, `v0.3.2`) → **Descartar**. **ExLlamaV3** es el sucesor muy activo (último push `2026-11-24`, `v1.6.7`, 1.874 estrellas).
- **ExLlamaV3 técnico:** Windows (exige PyTorch + `triton-windows`) y Linux; backends NVIDIA CUDA ≥12.4, **AMD ROCm/HIP (RDNA3+ `gfx1100+` `wave32`)** y offloading CPU AVX2/AVX-512 para MoE (**no CPU-only, no Vulkan**); formato propio **EXL3** (QTIP, sin GGUF); soporta Qwen3/3.5/3.8-Flash-Next; sin servidor HTTP propio (delega en TabbyAPI).
- **Decisión F1:** ExLlamaV2 **descartar**; ExLlamaV3 **solo estudiar en F3** (caché KV 2–8 bits, QTIP/EXL3 y offloading MoE).

### 21a. Strata (`Niko1221/Strata`) — *Mini-F1b*
- **Repositorio / docs:** `https://github.com/Niko1221/Strata` · `docs/HOW_IT_WORKS.md`, `docs/MODELS.md`, `docs/AMD_HIP.md`, `docs/STRIX_HALO.md`.
- **Licencia:** `MIT` (código base y app; los paquetes de motor `strata-engine`/`strata-inkling` incluyen avisos en `licenses/` y runtimes GPU específicos) · **Compatible GPL-3.0:** Código sí; para redistribución de motores binarios revisar `licenses/` de cada backend.
- **Lenguaje / dependencias:** C++ + app desktop/terminal (`strata-control`). Descarga bajo demanda el paquete de motor para la GPU detectada (`strata-engine`, `strata-inkling`, `strata-hy4`).
- **Actividad:** último push `2026-11-27`, release `v0.2.23` (`2026-11-27`), **48.788** estrellas.
- **SO / distribución:** **Windows x64** (`setup.exe`, `.zip`, `install.ps1`), **Linux x64/aarch64** (`AppImage`, `.tar.gz`, `install.sh`, Docker) y macOS arm64.
- **Backends:** NVIDIA CUDA 12/13 (RTX 20/30/40/50, DGX Spark), **AMD HIP/ROCm** (RDNA2/3/4, RX 9070, R9700, **Strix Halo**), Intel Arc SYCL (Linux) / opt-in Alchemist, Apple Metal. **Sin backend Vulkan ni modo CPU-only** (la CPU participa solo en expertos MoE híbridos y lectura de imagen).
- **Formato de pesos:** Packs `.strata` (`SQ-10`/`SQ-15`/`SQ-20`), `GSQ-RCO IQ3_S` y **GGUF personalizado** (`--model-path`) para `Qwen3.8-Flash-Next`, `Qwen3.6-35B-A3B` e `Inkling-2-Mini`.
- **Soporte Qwen3:** `Qwen3.8-Flash-Next`, `Qwen3.6-35B-A3B`, `Ornith-1.5-35B-A3B` (misma ruta de motor). Soporte de `Qwen3-4B`/`8B`/`30B-A3B` denso estándar en el catálogo: no destacado en portada (ver `docs/MODELS.md`).
- **API de servidor:** Compatible OpenAI (`/v1/chat/completions`, `/v1/responses`, tool calls) y Anthropic (`/v1/messages`). `/tokenize`, `/embeddings`: existen issues/discusiones sobre paridad parcial (`?`).
- **Técnicas clave:** **DFlash 2 drafter** integrado (0,55 GB extra, activo por defecto en RDNA2/3/4, Strix Halo, NVIDIA), caché dinámica de expertos MoE (VRAM/RAM/SSD), caché de conversación escalada a RAM (40 % de RAM libre hasta 128 GiB), `--turbo`/`--turbo-max` (saltar expertos débiles en capas tardías, cambia ligeramente la salida), `--tail-role-token`.
- **Benchmarks publicados:** *Afirmaciones del autor* en release `v0.2.23` (Inkling 2 Mini SQ-20 v2, sin logs en README): RTX 5060 Ti 16 GB código `80,4 -> 260,7 t/s`; RTX 5060 8 GB `32,5–41,2 t/s`; R9700 código `140,3 t/s`; Strix Halo prefill 4K `1.528 t/s`.
- **Encaje y riesgos:** **Nivel N2 (solo GPU dedicada CUDA/HIP)** + **N3** (DFlash 2 por defecto, caché de conversación escalada a RAM, `--turbo`). Riesgos: sin Vulkan ni CPU-only, catálogo centrado en MoE muy grandes y modos rápidos que alteran ligeramente los tokens.
- **Decisión F1:** **Probar en F4 (perfil C/D NVIDIA CUDA o AMD HIP)** + **estudiar en F3**.

### 21b. RustingStrata (`RustingStudio/RustingStrata`) — *Mini-F1b*
- **Repositorio / docs:** `https://github.com/RustingStudio/RustingStrata` · `docs/MODELS.md`, `docs/BENCHMARKS.md`, `docs/USAGE.md`, `docs/CALIBRATION.md`.
- **Licencia:** **RustingStrata License 1.0** (`LICENSE.md`, no-OSI, *source-available* de Vasyl Trefilov). Permite uso personal, investigación y uso comercial en aplicaciones/servicios con atribución (*"Uses RustingStrata by Vasyl Trefilov"*), pero **prohíbe vender, licenciar por pago o cobrar por el propio RustingStrata como motor sustituto**. · **Compatible GPL-3.0:** **No** para enlazar o redistribuir integrado dentro del paquete GPL-3.0 de GuarIdA (la Sección 2 añade una restricción incompatible con GPL-3.0); solo usable como herramienta externa descargada aparte por el usuario.
- **Lenguaje / dependencias:** **Rust puro** (edición 2024, sin C++ ni `ggml`). CUDA usa `nvrtc` en runtime (sin él cae a Vulkan); Vulkan requiere driver 1.3; HIP usa `hiprtc` en runtime.
- **Actividad:** último push `2026-11-27`, release `v1.4.2` (`2026-11-27`), **529** estrellas (muy activo).
- **SO / distribución:** **Binarios oficiales** `rustingstrata-windows-x86_64.exe` y `rustingstrata-linux-x86_64` (instaladores `install.ps1`/`install.sh`, AUR `rustingstrata-bin`, o `cargo build --release`).
- **Backends:** **CUDA** (Volta `sm_70`+; compilación JIT con NVRTC ~15 s la 1.ª vez), **Vulkan 1.3** (exige **`shaderFloat64`, `int8/16/64` y subgroup 32/64** — **el README advierte explícitamente que Intel Arc carece de `shaderFloat64`**), **HIP** (experimental), y **CPU** (referencia lenta para verificación; en modo híbrido MoE sí ejecuta expertos en paralelo en CPU).
- **Formato de pesos:** **GGUF nativo** sin conversión (`Q4_K_M`, `UD-Q2_K_XL`, `UD-Q5_K_M`, etc.).
- **Soporte Qwen3:** **Sí** — `Qwen3` (4B, etc.), `Qwen3-Next`, `Qwen3.5/3.6` (`35B-A3B`), `Qwen3.8-Flash-Next` (con soporte `--ple` para tabla n-gram).
- **API de servidor:** Muy alineada con GuarIdA — OpenAI `/v1/chat/completions` (tool calls en streaming, `response_format` `json_object`/`json_schema`, **gramáticas GBNF**), Anthropic, **`POST /tokenize`**, `POST /detokenize`, `GET /props` y **`timings` estilo `llama-server`**.
- **Técnicas clave:** **`rustingstrata calibrate`** (búsqueda con presupuesto de tiempo `--minutes M` para chunk, MTP drafts y umbrales), **TurboQuant KV cache** (`--kv turbo4`/`turbo3`/`turbo2` en CUDA y Vulkan), `STRATA_KV_HOST` (KV en RAM + atención en CPU), caché adaptativa de expertos MoE GPU+CPU+PCIe, prefetch desde disco en prompts largos, **DFlash2**, `--parallel N` batched serving con KV dinámica por slot.
- **Benchmarks publicados:** *Afirmaciones del autor* (RTX 3060 12 GB + R5 7600X + 32 GB RAM, CUDA greedy tras 4K prompt vs `llama.cpp`): `Qwen3.6-35B-A3B UD-Q5_K_M` **80,5 vs 64,4 t/s** decode (`1530 vs 1120` prefill); `UD-Q2_K_XL` **113,4 vs 66,5 t/s** decode (`2216 vs ~2236` prefill); `Qwen3-4B Q4_K_M` `--parallel 64` **1694–1699 t/s** CUDA / **824–960 t/s** Vulkan. Incluye `tools/loadtest.py` y `tools/parity.py` contra `llama-server`.
- **Encaje y riesgos:** **Nivel N2 externo (no empaquetable)** + **N3 altísimo** (`calibrate`, TurboQuant KV, colocación adaptativa de expertos en Vulkan/CUDA). Riesgos: licencia incompatible con redistribución GPL-3.0, **sin soporte Intel Arc en Vulkan** (`shaderFloat64`) y CPU-only lento.
- **Decisión F1:** **Probar en F4 (exploratorio como binario externo en Vulkan AMD/NVIDIA y CUDA)** + **estudiar a fondo en F3**.

### 24. DFlash2 (`z-lab/dflash`) — *Mini-F1b*
- **Repositorio / docs:** `https://github.com/z-lab/dflash` · Paper DFlash (`arXiv:2602.06036`) · Blog DFlash 2 (`https://inco.ai/blog/dflash2/`).
- **Licencia:** `MIT` (`z-lab/dflash`; verificar licencia de cada checkpoint drafter en HF `z-lab/dflash-2` / `z-lab/dflash`) · **Compatible GPL-3.0:** Sí (código MIT).
- **Lenguaje / dependencias:** Python (`pip install dflash`, backends `transformers`, `mlx` o cliente `openai`). No es un motor standalone para GuarIdA; es el paquete de evaluación y colección de pesos *drafter* por difusión en bloques.
- **Actividad:** último push `2026-08-18`, release `v0.1.0`, **6.268** estrellas.
- **Soporte Qwen3 y motores compatibles:** Checkpoints **DFlash 2** para `Qwen3.8-27B`, `Muse-Glimmer-30B`; **DFlash** para `Qwen3` (`4B`/`8B` non-thinking, `Coder-Next`, `Coder-30B-A3B`), `Qwen3.5`, `Qwen3.6` (`27B`, `35B-A3B`), `Gemma 4`, etc. Integrado en **`llama.cpp` (PR #27342)**, `SGLang` (PR #35371), `vLLM` (PR #52816), `ik_llama.cpp`, `Strata`, `RustingStrata`, `OpenVINO GenAI` y `oMLX`.
- **Técnicas clave:** Decodificación especulativa **sin pérdida** mediante modelo ligero de **difusión en bloques** (*parallel drafting*, verificando bloques en un solo paso del modelo objetivo; en MLX cuantizado recomienda `block_size <= 5`).
- **Encaje y riesgos:** **Nivel N0 (vía `llama.cpp` actualizado) + N3**. Riesgo: exige un archivo drafter adicional (~0,55 GB según `Strata`) por modelo, y en GPUs rápidas o código/chat concreto puede no siempre acelerar (ver límites documentados en `Strata v0.2.23`).
- **Decisión F1:** **Estudiar en F3** y **probar en F2/F4 integrado dentro de `llama.cpp` (`v1.0.0`+)**.

---

## Registro de afirmaciones verificadas (sin reproducir en GuarIdA)

> Todas estas cifras se han localizado en su fuente primaria el 2026-11-28, pero siguen siendo **afirmaciones del autor** hasta probarlas en F4.

| Proyecto | Afirmación (cifra, hardware, modelo, cuantización) | Fuente exacta | ¿Reproducible? |
|---|---|---|---|
| `llm.asm` | Decode `20,70–125,86 t/s` (`+18%` a `+35,6%` vs `llama.cpp -ngl 0`), pero **prefill `pp34` `26,7–160,8` vs `56–1113 t/s`**, EPYC 7642, `Qwen3-0.6B Q8_0` (`.asmbin` v2); bare-metal arranque `73,5–94,3 ms` | `alesha-pro/llm.asm` README + `01-qwen3-inference/README.md` + `02-baremetal-os/README.md` | Parcial (paridad sí; comparativa vs `llama.cpp` no) |
| `ik_llama.cpp` | Aceleración CPU `pp` media geométrica `~2,8–3,3×` vs mainline (ene-2025, Zen4/AVX2/NEON); PR 2926 hasta `~5× tg` CPU en decode MoE vacío/sin warmup; PR 2901 reduce copias CPU→GPU `~9×` | `ikawrakow/ik_llama.cpp` README y Wiki | Parcial (`llama-bench`/`sweep-bench`, tablas en Wiki/PRs) |
| `ik_llama.cpp` *(ChatGPT)* | "Decode MoE Qwen `~13 -> ~22,7 t/s` frente a mainline" | **No encontrada** en README ni Wiki oficial | **No (sin fuente)** |
| `Ghost Infer` | RTX 2060 SUPER 8 GB + 24 GB RAM vs `llama.cpp b11747`: Qwen3-30B-A3B **`i1-Q3_K_M`** `68,7 vs 29,5 t/s`; Qwen3.6-35B-A3B `i1-Q3_K_M` `80,5 vs 39,5 t/s` (`49,1` tras 64K); Qwen3-8B `75,3 vs 64,7 t/s`; lookup `3,2×` en edición | `affifuddin-hazam/ghost-infer` README (`## Speed`, `## Long chats`) y release `v0.4.0` | Parcial (cita `bench-all.ps1`, sin logs descargados) |
| `DynaLM` | M4 Pro CPU (SME) `1,53×` media geométrica y `2,7–2,9×` menos RAM vs `llama.cpp` (`Q4_K_M`); EPYC Zen 2 AVX2 (*uncontrolled*, vs `b11695`): `1,07–1,17×` sin draft y `1,34–1,41×` con EAGLE-3 en Qwen3-4B/8B | `dynalm-project/dynalm` README (`v0.6.0`) | Parcial (`dynalm cpu-report`; x86 marcado *uncontrolled*) |
| `Golem` | RX 9070 XT Vulkan `Q4_0` vs `llama.cpp b9603`: Qwen3-4B `180,5` gen / `5977` pp512 vs `172,0` / `7117`; Gemma 4 26B A4B `153,4` vs `125,1` (`56,2` con 51/128 expertos en 5,1 GB); Qwen3.8-27B H3G `38,8 vs 34,1` `Q4_0` | `ThiraSoft/golem` README (`## Speed`) | No (sin logs/scripts en fuentes descargadas) |
| `Herbert-rs` | Ryzen 9 7900 AVX-512, `Qwen3-0.6B` Q4: decode `101/70/52/29` vs `llama.cpp` `97/56/35/17 t/s` (1k/5k/10k/16k ctx), **prefill 1k `751 vs 1057 t/s`** | `xigh/herbert-rs` README (`Benchmarks`) | No (sin comandos ni config KV de `llama.cpp`) |
| `mistral.rs` | CUDA Q8 `UQFF q8` vs `llama.cpp GGUF Q8_0` en GB10/B200/H100 (Gemma 4 E4B y 26B-A4B): ventaja en prefill y moderada en decode; **sin cifras CPU ni GPU 8–16 GB** | `EricLBuehler/mistral.rs` README (`v0.8.2 CUDA benchmarks`) | No verificado (`report.md` no descargado) |
| `OpenSet-LLM` | `Bonsai-2-27B` ternario `PTQ1_0` + MTP: Ice Lake 8 cores / 8 GB (AVX-512, 4k ctx) `16,99–19,67 t/s`; Zen 5 `35–36 t/s`; **AVX2 sin AVX-512 `5,8–7,2 t/s`** (`7,2–8,7` `--spec`); **16k ctx 8 GB `7,98 t/s`** | `opensetlabs/openset-llm` README (`Numbers`, `CPUs without AVX-512`) | Parcial (`bench/quick.sh`; sesión de agente no publicada) |
| `KTransformers` | DeepSeek-R1 FP8 en 8×L20: `227,85` total / `87,58 t/s` output; SFT Qwen3-30B-A3B 1×4090 `8+ it/s` | `kvcache-ai/ktransformers` README | No |
| `Megakernel Zoo` | Qwen3-8B en 1×H100 (`ctx <= 2048`, batch 1): Track A `5,13 ms/tok`, Track B `3,83 ms/tok` vs SGLang `6,09 ms/tok` | `dangxingyu/megakernel-zoo` README (`Benchmarks`) | Sí (infraestructura + `runs/` en repo; exige H100/B200) |
| `Strata` | `v0.2.23`, Inkling 2 Mini SQ-20 v2: RTX 5060 Ti 16 GB código `80,4 -> 260,7 t/s`; RTX 5060 8 GB `32,5–41,2 t/s`; R9700 código `140,3 t/s`; Strix Halo prefill 4K `1.528 t/s` | `Niko1221/Strata` release `v0.2.23` (`Speed`) | No (sin logs en releases/README) |
| `RustingStrata` | RTX 3060 12 GB + R5 7600X + 32 GB RAM, CUDA greedy tras 4K prompt vs `llama.cpp`: `Qwen3.6-35B-A3B` `UD-Q5_K_M` `80,5 vs 64,4 t/s` (`1530 vs 1120` pp); `UD-Q2_K_XL` `113,4 vs 66,5 t/s`; `Qwen3-4B Q4_K_M` `--parallel 64` `824–960 t/s` en Vulkan | `RustingStudio/RustingStrata` README (`Numbers`) y release `v1.4.0` | Parcial (incluye `tools/parity.py` y `tools/loadtest.py`; `docs/BENCHMARKS.md` no descargado) |

---

## Principales correcciones a la conversación previa con ChatGPT

1. **`llm.asm`:** es ~7× más lento que `llama.cpp` en prefill (`pp34`, GEMV token a token), solo corre en Linux x86-64 AVX2, usa formato propietario `.asmbin` y está atado a `Qwen3-0.6B`.
2. **`ik_llama.cpp`:** no soporta Vulkan (ni ROCm/Metal), no publica binarios Windows y la cifra `"~13 -> ~22,7 t/s"` no aparece en sus fuentes oficiales.
3. **`Ghost Infer`:** los 68,7 t/s de Qwen3-30B-A3B fueron en **`i1-Q3_K_M`** (no `Q4_K_M`), es exclusivo NVIDIA CUDA y su instalador Windows empaqueta NVRTC privativo.
4. **`DynaLM`:** sí publica binarios Windows Vulkan (aunque solo *CI-tested* en `lavapipe`); su 1,53× es solo en Apple M4 SME (en x86-64 AVX2 usa `ggml` por defecto y declara 1,07–1,17× sin draft / 1,34–1,41× con EAGLE-3); **no tiene tool calling aún** y tiene 4 estrellas.
5. **`Golem`:** en Qwen3-4B `Q4_0` pierde en prefill `pp512` (`5977 vs 7117`) contra un `llama.cpp` antiguo (`b9603`), no tiene soporte Windows ni Qwen3 MoE documentado, y tiene 3 estrellas.
6. **`OpenVINO`:** la GPU es estrictamente Intel (nada de AMD/Vulkan), son tres piezas (`openvino` + `openvino.genai` + `OVMS`), ya tiene lector GGUF preview y trae **telemetría GA4 activa por defecto**.
7. **`KTransformers`:** el soporte Windows está archivado; el flujo activo (`kt-kernel` + `sglang-kt`) es **solo Linux + CUDA SM 80+**, aunque añadió AVX2-Llamafile en CPU.
8. **`MLC LLM`:** **no soporta inferencia en CPU** (la wheel `-cpu` ejecuta en Vulkan/Metal), no lee GGUF y no tiene releases estables desde 2023.
9. **`Herbert-rs`:** **ya no está mantenido**, no soporta Windows ni CUDA, no lee GGUF, no tiene API OpenAI (solo Anthropic) y su prefill denso es 1,5–2× más lento que `llama.cpp`.
10. **`mistral.rs`:** no soporta Vulkan/ROCm, no tiene binario CUDA para Windows (los binarios CUDA son Linux `sm80+`) y no publica benchmarks CPU/GPU doméstica.
11. **`OpenSet-LLM`:** son parches sobre el fork PrismML de `llama.cpp`, solo Linux/WSL2, un único modelo (`Bonsai-2-27B`) y en AVX2 sin AVX-512 baja a 5,8–7,2 t/s.
12. **`ExLlama`:** ExLlamaV2 está archivado en favor de `ExLlamaV3`, que ahora soporta AMD ROCm RDNA3+ y CPU offloading MoE, pero sigue sin GGUF ni Vulkan ni modo CPU-only.
13. **Los 12 proyectos citados sin enlace y los 4 modelos nuevos existen todos** (ChatGPT solo inventó algunos slugs de GitHub como `StrataEngine/Strata` en lugar de `Niko1221/Strata`, o `PrismML` en lugar de `PrismML-Eng`). Ver [01b_agregador_y_manual.md](01b_agregador_y_manual.md).
