# 03b · Fichas técnicas de apoyo (T1, T2, T3, T5, T11–T15, T17)

> **Estado:** **Fase 3 cerrada (2026-11-28).** Complemento de [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md) con las 10 técnicas restantes de las 20 estudiadas.

---

### T1 · Mapeo de pesos (`mmap`), `mlock` y carga rápida
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce latencia de arranque/carga y evita paginación involuntaria o *thrashing* de pesos entre RAM, archivo de paginación y memoria compartida GTT en GPU integrada/APU durante `carga`, `prefill` y `decode`.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Por defecto `llama.cpp` mapea el GGUF con `mmap`. En `llama-server` (`llamacpp_server_README.md:74`), `-lm/--load-mode` (`auto|none|mmap|mlock|mmap+mlock|dio`) unifica `--no-mmap` y `--mlock`. En Windows con iGPU/UMA y GTT compartida, `mmap` puede hacer que WDDM/Vulkan pagine o mueva bloques respaldados por disco hacia *Shared GPU Memory*, penalizando `prefill`; `--no-mmap` (`-lm none`) fuerza lectura secuencial directa a búferes de RAM. `--mlock` fija los pesos en RAM física (exige `SeLockMemoryPrivilege` en Windows y RAM libre suficiente). Como referencia extrema, `llm.asm` usa `.asmbin` con páginas de 2 MiB y syscalls directas sin `libc`.
- **Proyectos / archivos de referencia:** `llama.cpp` (`llamacpp_server_README.md:74`), `alesha-pro/llm.asm`, GuarIdA `engine/server.py` y `tuning/buscador.py:_obtener_extra_args_gtt()`.
- **Requisitos (modelo, hardware, formato, backend):** Cualquier GGUF en `llama-server`. `--mlock` exige RAM física libre superior a modelo + KV + SO (riesgoso en 16 GB, viable en ≥32 GB).
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** `--no-mmap` aumenta el arranque inicial y consume RAM privada desde el segundo 0; `--mlock` en 16 GB puede provocar OOM del sistema operativo. Cero impacto en calidad.
- **Prueba del protocolo (A–H) que la mide:** **A** (carga), **B/C** (prefill/decode en iGPU/GTT Windows) y **E** (estabilidad bajo presión de memoria).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **Nivel N0 / N1.** `engine/server.py` ya incluye `mlock`, `no_mmap` y `-lm` en lista blanca, pero `desde_afinamiento()` no aplica `-lm none`/`--no-mmap` en rutas GTT fuera del tuner. Conviene unificarlo usando `-lm` si `--help` lo soporta y dejar `--mlock` opt-in con ≥32 GB y margen verificado.
- **Decisión F3:** `integrar` (estandarizar `-lm none`/`--no-mmap` en iGPU/GTT Windows y `--mlock` solo con margen ≥32 GB).

---

### T2 · Kernels SIMD especializados
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Acelera GEMV (**decode**) y GEMM por lotes (**prefill**) en CPU x86-64 cuando no hay GPU o corren expertos/capas en CPU.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):**
  - **Lección de `llm.asm`:** su kernel GEMV `Q8_0` en AVX2 puro acelera decode, pero al procesar el prompt token a token en lugar de usar GEMM por lotes, su **prefill es ~7× más lento** que `llama.cpp`.
  - **Trampa silenciosa `HAVE_FANCY_SIMD` (`ik_llama.cpp`):** CMake condiciona los kernels AVX-512 de alto rendimiento (`iqk_gemm`) a `HAVE_FANCY_SIMD` (AVX-512 VNNI + VBMI + VL + BW + DQ); un build estándar sin flags explícitos cae silenciosamente a AVX2 (análogo a `STRATA_AVX512=1` en `RustingStrata`).
- **Proyectos / archivos de referencia:** `alesha-pro/llm.asm`, `ikawrakow/ik_llama.cpp` (`CMakeLists.txt`, `iqk_gemm`), `rustingstrata_USAGE.md`.
- **Requisitos (modelo, hardware, formato, backend):** CPU x86-64 con AVX2/F16C o AVX-512 VNNI/VBMI.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** Distribuir binarios compilados con `target-cpu=native` provoca `SIGILL` en CPUs antiguas; diferencias mínimas de redondeo en empates greedy.
- **Prueba del protocolo (A–H) que la mide:** **A/B** (decode y prefill en CPU/híbrido).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **Nivel N1.** `hardware_detectors.py` (detectar AVX2/AVX-512 VNNI/VBMI real), `downloader/binaries.py` (seleccionar/advertir variante de binario) y `tuning/capacidades.py` (registrar flags de `--version`).
- **Decisión F3:** `imitar` (no mantener kernels propios; imitar la detección explícita de ISA y selección de binario óptimo).

---

### T3 · Cuantización de pesos y fragmentación de catálogo
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce huella en **memoria** y disco offline, acelera **decode** y equilibra **calidad** frente al límite de 2 GB por archivo en GitHub Releases.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** K-quants (`Q4_K_M`, `Q5_K_M`) son universales en `llama-server` CPU y Vulkan; en cambio, `IQ_KT`/Trellis (`ik_llama.cpp`), `INT4` IR (`OpenVINO`), `q4f16` (`MLC`), ternaria `PTQ1_0` (`OpenSet-LLM`/`PrismML`) y `H3G` (`Golem`) exigen motores o forks incompatibles con Vulkan/GGUF estándar, lo que duplicaría modelos en disco y fragmentaría el soporte offline.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md`, `ik_llama.cpp`, `OpenSet-LLM`, `Golem`, `MLC LLM`, GuarIdA `downloader/models.py` (`CatalogoModelos`).
- **Requisitos / Coste o riesgo:** Por debajo de ~4 bpw cae la precisión sintáctica en código, JSON y *tool calling*; mantener múltiples formatos dispara el uso de disco.
- **Prueba del protocolo (A–H) que la mide:** **B/C** (velocidad) + puerta de calidad (código/JSON/perplejidad).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **Nivel N1** en `downloader/models.py` y `downloader/compliance.py`: mantener GGUF como formato único (K-quants + `IQ4_XS` selectivo para hardware muy justo) y soportar GGUF multiparte si hace falta.
- **Decisión F3:** `imitar` (catálogo curado en GGUF) y `descartar` formatos propietarios mientras el motor base sea `llama-server`.

---

### T5 · Atención fusionada / FlashAttention
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Evita materializar la matriz de atención $O(N^2)$ durante **prefill** y **decode**, reduciendo picos de memoria en contextos largos y habilitando KV cuantizada en V (`T4`).
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Procesa la atención por teselas (*tiling*) con softmax incremental en línea. En `llama-server` (`llamacpp_server_README.md:56`), `-fa, --flash-attn [on|off|auto]` selecciona kernels fusionados en CUDA, CPU o Vulkan (`VK_KHR_cooperative_matrix`). En Vulkan depende del soporte del driver/iGPU (si falla, puede ralentizarse). `Herbert-rs` genera shaders SPIR-V con *cooperative matrix* y `OpenSet-LLM` usa atención fusionada en CPU.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md:56`, `xigh/herbert-rs`, `opensetlabs/openset-llm`, GuarIdA `engine/server.py:196-197,285-287`.
- **Requisitos / Coste o riesgo:** Cero memoria extra (ahorra VRAM/RAM). Riesgo de regresión en Vulkan si se fuerza `on` en una iGPU sin soporte rápido, por eso conviene probarlo empíricamente.
- **Prueba del protocolo (A–H) que la mide:** **B** (`pp` a 2K–8K), **C** (`tg` en contexto poblado) y **E** (pico de memoria).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **Nivel N0 / N1.** Hoy `engine/server.py:285-287` fuerza `fa = False` cuando `tipo_gpu_principal != "NVIDIA"`, y `server.py:196-197` emite `-fa` sin argumento (`b12017`+/upstream acepta `on|off|auto`). Hay que eliminar ese veto fijo, soportar `-fa auto|on|off` y dejar que `tuning/buscador.py` lo mida en Vulkan y CPU.
- **Decisión F3:** `integrar` (desbloquear `-fa` en Vulkan/CPU en `engine/server.py` y validarlo en `tuning/buscador.py`).

---

### T11 · Separar prefill y decode por dispositivo
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Ataca la asimetría entre **prefill** (cómputo paralelo) y **decode** (ancho de banda de memoria).
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** `KTransformers` ejecuta atención y prefill en GPU y expertos fríos en CPU; `FastLLM` combina `KVMem` en host + GPU. En `llama-server` solo existe aproximación parcial diferenciando hilos `-tb` (prefill) y `-t` (decode) más `-nkvo`/`-ot`.
- **Proyectos / archivos de referencia:** `KTransformers`, `FastLLM`, `llamacpp_server_README.md`.
- **Requisitos / Coste o riesgo:** La desagregación real exige sincronizar y transferir KV por PCIe entre dispositivos distintos; inviable sobre `llama-server` HTTP actual.
- **Prueba del protocolo (A–H) que la mide:** **B/C** y **H** (ejecución híbrida).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N4**; mantener `-tb`/`-t` en `engine/server.py`.
- **Decisión F3:** `solo estudiar`.

---

### T12 · Compilación de grafo por dispositivo
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce sobrecarga de despacho y fusiona operadores en **prefill** y **decode**.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** `llama.cpp` con `-DGGML_OPENVINO=ON` traduce en caliente `ggml_cgraph` a OpenVINO IR en memoria para Intel CPU/GPU/NPU; `MLC LLM` compila AOT vía Apache TVM con formato propio `q4f16`.
- **Proyectos / archivos de referencia:** `llama.cpp` (`ggml/src/ggml-openvino`), `MLC LLM`.
- **Requisitos / Coste o riesgo:** Añade cientos de MB de runtime o toolchain pesada y rompe el formato GGUF único en el caso de MLC.
- **Prueba del protocolo (A–H) que la mide:** **A/B/C** (carga inicial + tok/s).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N2 / N3** (solo considerar en el futuro una variante binaria `llama-server` con `-DGGML_OPENVINO=ON` para equipos Intel si F4 lo justifica).
- **Decisión F3:** `solo estudiar` (`GGML_OPENVINO`) / `descartar` (`MLC` por fragmentación de catálogo).

---

### T13 · Especialización por modelo / megakernels y puerta numérica FP64
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Los megakernels reducen latencia de lanzamiento en **decode**; la puerta numérica protege la **calidad** frente a optimizaciones agresivas.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** `Megakernel Zoo` genera un megakernel CUDA por `(checkpoint, GPU)` en H100/B200 y exige verificar coincidencia numérica contra referencia **FP64** antes de aceptar cualquier ganancia de velocidad. En GuarIdA, los megakernels no son portables, pero la disciplina de **puerta de calidad previa al scoring** es directamente aplicable a `tuning/`.
- **Proyectos / archivos de referencia:** `Megakernel Zoo`, `llm.asm`, GuarIdA `tuning/bateria.py` y `tuning/scoring.py`.
- **Requisitos / Coste o riesgo:** Cero coste de runtime en la puerta de calidad (prompts de control de sintaxis/JSON/coherencia antes de puntuar velocidad).
- **Prueba del protocolo (A–H) que la mide:** Puerta de calidad combinada con **B/C**.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N1** en `tuning/bateria.py` y `tuning/scoring.py`.
- **Decisión F3:** `imitar` (descartar megakernels; **imitar** la puerta obligatoria de sanidad/calidad previa al scoring de velocidad).

---

### T14 · PagedAttention / KV por bloques
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Elimina la fragmentación de memoria KV en **carga**, **prefill** y **decode** con múltiples usuarios concurrentes.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Divide la KV cache en páginas físicas fijas mapeadas por una tabla de bloques lógica (16–32 tokens en `vLLM` / `OpenVINO GenAI` / `mistral.rs` / `DynaLM`), permitiendo *Copy-on-Write*. En **monousuario local (`-np 1`)** su beneficio es bajo frente a `--kv-unified` de `llama.cpp`; solo es crítico en servidores LAN de alta concurrencia.
- **Proyectos / archivos de referencia:** `vLLM`, `OpenVINO GenAI`, `mistral.rs`, `DynaLM`, `llamacpp_server_README.md` (`--kv-unified`).
- **Requisitos / Coste o riesgo:** Exige cambiar de motor o kernels de atención propios; no compensa sustituir `llama-server` Vulkan/CPU para uso monousuario.
- **Prueba del protocolo (A–H) que la mide:** Concurrencia LAN y memoria máxima con múltiples slots.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N4** (solo explorar `--kv-unified` en `engine/server.py` si se habilita multi-slot LAN).
- **Decisión F3:** `solo estudiar`.

---

### T15 · *Continuous batching* y planificación de peticiones
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Aumenta el *throughput* agregado y evita bloqueos de cola cuando hay peticiones simultáneas.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Reconfigura el lote en cada iteración de decode en cuanto una petición termina. En `llama-server` (`llamacpp_server_README.md:178-179`), `--cont-batching` (`-cb`) viene activo por defecto y trabaja con `--parallel N` (`-np`). En monousuario local conviene mantener `-np 1` para no repartir VRAM/contexto ni bloquear la especulación; en modo servidor LAN/túnel sí conviene `-np 2..4` + `--kv-unified`.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md`, `rustingstrata_USAGE.md`, `vLLM`, `SGLang`, `mistral.rs`, GuarIdA `engine/server.py:21-22`.
- **Requisitos / Coste o riesgo:** Cada slot paralelo consume KV cache y puede restringir `-md` (`--parallel > 1`).
- **Prueba del protocolo (A–H) que la mide:** Concurrencia LAN (múltiples clientes simultáneos).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N3** en `engine/server.py` y `web/server.py`: mantener `-np 1` en local y parametrizar `-np 2..4` + `--kv-unified` cuando se sirva en LAN/túnel.
- **Decisión F3:** `integrar` (de forma condicional entre modo local y modo servidor LAN).

---

### T17 · Gestión de contexto en el arnés (RAG AST, compresión, presupuesto de tokens)
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce tokens en **prefill** (menor TTFT), evita desbordamientos de contexto (`400`) y protege la **calidad** y la estabilidad de prefijo de **T6**.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):**
  - *Lo que GuarIdA ya hace bien:* `chat.py:1190-1220` y `web/server.py:1046-1049` guardan en historial solo el mensaje limpio (inyectando `ctx_doc` solo en el último turno), y `arbol_nodos.py:16-62` (`minificar_codigo_bpe`) comprime nodos AST manteniendo firmas y expansión multihop (`proyectos.py:1292`).
  - *Fricciones detectadas:* (1) `buscar_contexto_hibrido` (`proyectos.py:1165-1347`) no acota por presupuesto de tokens (`ctx_size`), (2) `chat.py:1144,1189` y `web/server.py:1022,1051` hacen **2 llamadas HTTP síncronas previas a `/tokenize`** en cada turno, y (3) la colocación actual de `prompt_sistema` y `ctx_memoria` rompe **T6**.
  - *Ajustes concretos:* añadir `presupuesto_tokens_ctx` en `buscar_contexto_hibrido()` (recortando primero dependencias multihop y chunks de menor score RRF), sustituir las 2 llamadas previas a `/tokenize` por estimación local rápida (llamando a `/tokenize` solo si supera ~85 % de `ctx_size` y leyendo `usage.prompt_tokens` de la respuesta), y alinear prefijo con **T6**.
- **Proyectos / archivos de referencia:** GuarIdA `arbol_nodos.py`, `proyectos.py`, `chat.py`, `web/server.py`; `rustingstrata_USAGE.md:230-232`.
- **Requisitos / Coste o riesgo:** Lógica Python pura; garantizar al menos el top-1 AST/chunk en ventanas pequeñas (`2048`).
- **Prueba del protocolo (A–H) que la mide:** **F** (multiturno RAG + memoria) y **G** (código).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N1** en `proyectos.py`, `chat.py` y `web/server.py`.
- **Decisión F3:** `integrar` (elimina 2 round-trips HTTP por turno, evita desbordamientos y desbloquea T6).
