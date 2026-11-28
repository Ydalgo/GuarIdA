# 03 · Catálogo de técnicas

> **Estado:** **Fase 3 cerrada (2026-11-28).** Las 20 técnicas (`T1–T20`) han sido estudiadas y clasificadas frente al código real de GuarIdA (`engine/server.py`, `engine/client.py`, `chat.py`, `web/server.py`, `proyectos.py`, `tuning/`, `downloader/`).
> - Aquí figuran la tabla resumen `T1–T20`, las fichas de las **10 técnicas de mayor impacto o riesgo** (`T4`, `T6`, `T7`, `T8`, `T9`, `T10`, `T16`, `T18`, `T19`, `T20`), el **Plan de experimentos N0 listo para F2** y la **Base arquitectónica preliminar para F5/F6**.
> - Las 10 fichas de apoyo (`T1`, `T2`, `T3`, `T5`, `T11`, `T12`, `T13`, `T14`, `T15`, `T17`) están en [03b_fichas_tecnicas_apoyo.md](03b_fichas_tecnicas_apoyo.md).

Los motores ganan velocidad por cuatro vías distintas:
1. **Calcular más barato** (kernels, cuantización, compilación).
2. **Mover menos datos** (KV cuantizada, reparto de expertos, mapeo de memoria).
3. **Dar menos pasos secuenciales** (especulación, MTP, *lookup*).
4. **No volver a calcular lo mismo** (caché de prefijos, reutilización de KV, guardado de estado).

**Conclusión clave de F3:** antes de cambiar de motor, GuarIdA tiene margen muy alto en **N0/N1** (arnés + `llama-server`) combinando **T6 + T17** (*cache-aware prompting*, `id_slot`, `--slot-save-path`, quitar las 2 llamadas previas a `/tokenize`), **T5 + T4** (desbloquear `-fa` en Vulkan/CPU y KV `q8_0`), **T9** (`--lookup-cache` en edición de código) y **T20** (auditoría de *Token Inflation Trap*).

---

## Tabla resumen (T1–T20 · verificada en F3)

| # | Técnica | Familia | Referencias principales | Nivel GuarIdA | Decisión F3 | Ficha |
|---|---|---|---|---|---|---|
| **T1** | Mapeo `mmap`, `--no-mmap` (`-lm none`), `--mlock` | 2 | `llama.cpp`, `llm.asm` | N0 / N1 | **`integrar`** *(estandarizar `-lm none` en GTT)* | [03b](03b_fichas_tecnicas_apoyo.md#t1--mapeo-de-pesos-mmap-mlock-y-carga-rápida) |
| **T2** | Kernels SIMD (AVX2, AVX-512, `HAVE_FANCY_SIMD`) | 1 | `llm.asm`, `ik_llama.cpp`, `RustingStrata` | N1 | **`imitar`** *(detección ISA en `hardware_detectors.py`)* | [03b](03b_fichas_tecnicas_apoyo.md#t2--kernels-simd-especializados) |
| **T3** | Cuantización de pesos y fragmentación de catálogo | 1·2 | `llama.cpp`, `ik_llama.cpp`, `OpenSet-LLM`, `Golem`, `MLC` | N1 | **`imitar`** GGUF / **`descartar`** formatos propios | [03b](03b_fichas_tecnicas_apoyo.md#t3--cuantización-de-pesos-y-fragmentación-de-catálogo) |
| **T4** | KV-cache cuantizada (`q8_0`, `q4_0`, TurboQuant, Hadamard) | 2 | `llama.cpp`, `RustingStrata`, `ik_llama.cpp`, `Herbert-rs`, `ExLlamaV3` | N0 / N1 | **`integrar`** (`q8_0` / asimétrico) · `solo estudiar` TurboQuant/Hadamard | [Abajo](#t4--kv-cache-cuantizada) |
| **T5** | Atención fusionada / FlashAttention (`-fa`) | 1·2 | `llama.cpp`, `Herbert-rs`, `OpenSet-LLM` | N0 / N1 | **`integrar`** *(quitar veto fijo no-NVIDIA en `server.py`)* | [03b](03b_fichas_tecnicas_apoyo.md#t5--atención-fusionada--flashattention) |
| **T6** | Reutilización de prefijos, `id_slot` y guardado en disco | 4 | `llama.cpp`, `OpenSet-LLM`, `DynaLM`, `RustingStrata`, `SGLang` | N0 + N3 | **`integrar`** *(prioridad #1 para TTFT multiturno)* | [Abajo](#t6--reutilización-de-prefijos-y-estado) |
| **T7** | Decodificación especulativa con borrador (`-md`) | 3 | `llama.cpp` (`Qwen3-0.6B`), `RustingStrata` | N0 / N2 | **`integrar`** *(opt-in solo con holgura VRAM)* | [Abajo](#t7--decodificación-especulativa-con-modelo-borrador--md----model-draft) |
| **T8** | **DFlash2**, EAGLE-3 y MTP | 3 | `z-lab/dflash`, `llama.cpp` PR #27342, `Strata`, `OpenVINO`, `DynaLM` | N0 / N4 | **`solo estudiar`** *(esperar migración `llama-server v1.0.0+`)* | [Abajo](#t8--dflash2-eagle-3-y-mtp) |
| **T9** | *Prompt lookup* / n-gram / suffix (`--lookup-cache`) | 3 | `llama.cpp`, `ik_llama.cpp`, `Strata`, `Ghost Infer` | N0 / N1 | **`integrar`** *(prioridad alta en edición de código)* | [Abajo](#t9--prompt-lookup--n-gram--suffix) |
| **T10** | Reparto y caché dinámica de expertos MoE | 2 | `llama.cpp`, `ik_llama.cpp`, `RustingStrata`, `Strata`, `Golem`, `KTransformers` | N0 / N1 | **`integrar`** *(`-cmoe`, `--moe-cache-mib`, `-ot` en `tuning/`)* | [Abajo](#t10--reparto-y-caché-dinámica-de-expertos-moe) |
| **T11** | Separar prefill y decode por dispositivo | 2 | `KTransformers`, `FastLLM`, `llama.cpp` (`-tb`/`-t`) | N0 / N4 | **`solo estudiar`** *(mantener `-tb`/`-t` en `server.py`)* | [03b](03b_fichas_tecnicas_apoyo.md#t11--separar-prefill-y-decode-por-dispositivo) |
| **T12** | Compilación de grafo por dispositivo | 1 | `llama.cpp` (`-DGGML_OPENVINO=ON`), `MLC LLM` | N2 / N3 | **`solo estudiar`** (`GGML_OPENVINO`) / **`descartar`** MLC | [03b](03b_fichas_tecnicas_apoyo.md#t12--compilación-de-grafo-por-dispositivo) |
| **T13** | Megakernels y puerta numérica FP64 | 1 | `Megakernel Zoo`, `llm.asm` | N1 | **`imitar`** *(puerta de calidad previa al scoring en `tuning/`)* | [03b](03b_fichas_tecnicas_apoyo.md#t13--especialización-por-modelo--megakernels-y-puerta-numérica-fp64) |
| **T14** | PagedAttention / KV por bloques | 2 | `vLLM`, `OpenVINO GenAI`, `mistral.rs`, `DynaLM` | N4 | **`solo estudiar`** *(bajo impacto en monousuario)* | [03b](03b_fichas_tecnicas_apoyo.md#t14--pagedattention--kv-por-bloques) |
| **T15** | *Continuous batching* y planificación (`-cb`, `-np`) | — | `llama.cpp`, `RustingStrata`, `vLLM`, `mistral.rs` | N0 / N3 | **`integrar`** *(condicional: `-np 1` local, `-np 2..4` LAN)* | [03b](03b_fichas_tecnicas_apoyo.md#t15--continuous-batching-y-planificación-de-peticiones) |
| **T16** | Separación servidor / motor e interfaz `MotorInferencia` | — | `mistral.rs`, `RustingStrata` (`timings`, `/props`) | N1 / N3 | **`integrar`** *(interfaz `MotorInferencia` + `timings` unificados)* | [Abajo](#t16--separación-servidor--motor--pipeline-e-interfaz-motorinferencia) |
| **T17** | Gestión de contexto en arnés (RAG AST, presupuesto) | 4 | GuarIdA (`proyectos.py`, `arbol_nodos.py`, `chat.py`, `web/server.py`) | N0 / N1 | **`integrar`** *(presupuesto de tokens y quitar 2 `/tokenize`)* | [03b](03b_fichas_tecnicas_apoyo.md#t17--gestión-de-contexto-en-el-arnés-rag-ast-compresión-presupuesto-de-tokens) |
| **T18** | **KVMem** (KV jerárquico GPU+RAM *pre-RoPE mean-K*) | 2 | `FastLLM` (`docs/kvmem.md`) | N3 / N4 | **`solo estudiar`** *(RAG+KV `q8_0` cubren 8–32K sin complejidad)* | [Abajo](#t18--kvmem-kv-cache-jerárquico-gpu--ram) |
| **T19** | Atención dispersa en prefill (`Tri-shape`/`XAttention`) y KV eviction | 1·2 | `OpenVINO GenAI` | N3 / N4 | **`solo estudiar`** *(riesgo en código por eviction permanente)* | [Abajo](#t19--atención-dispersa-en-prefill-tri-shape--xattention-y-kv-token-eviction) |
| **T20** | Auditoría de *Token Inflation Trap* en razonamiento | — | Literatura cuantización + `RustingStrata` (`--thinking-budget`) | N0 / N1 | **`imitar`** *(medir tiempo total a acierto en `tuning/`)* | [Abajo](#t20--auditoría-de-token-inflation-trap) |

---

## Fichas técnicas principales (F3)

### T4 · KV-cache cuantizada
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce drásticamente el consumo de VRAM/RAM de la KV-cache en contextos largos y disminuye el tráfico de memoria en `decode` (limitado por ancho de banda), afectando ligeramente a `calidad`.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** En lugar de almacenar claves (K) y valores (V) en `f16` (2 bytes/elemento), los cuantiza por bloques a 8, 5 o 4 bits (`-ctk`/`-ctv` en `llama.cpp`: `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1`, `f8_e4m3`). Como K es más sensible a *outliers* que V, varios motores aplican transformaciones ortogonales previas: `RustingStrata` (`rustingstrata_USAGE.md:151-158`) implementa **TurboQuant** (`turbo4`/`turbo3`/`turbo2` y `--k`/`--v` asimétricos) rotando bloques de 128 valores con signed-Walsh y centroides Lloyd-Max; `ik_llama.cpp` aplica Hadamard sobre K y V (`-khad`/`-vhad`); `ExLlamaV3` cuantiza KV de 2 a 8 bits por separado; `Herbert-rs` usa KV INT8 con VNNI; y `OpenSet-LLM` expone `--kv8`/`--kv6`/`--kv5`.
- **Proyectos / archivos de referencia:** `llama.cpp` (`llamacpp_server_README.md:71-72`), `RustingStrata` (`rustingstrata_USAGE.md:146-158`), `ikawrakow/ik_llama.cpp`, `turboderp-org/exllamav3`, `xigh/herbert-rs`, `opensetlabs/openset-llm`.
- **Requisitos (modelo, hardware, formato, backend):** En `llama-server`, requiere `head_size` múltiplo de 32 para ciertos formatos y **FlashAttention (`-fa`) activo** para cuantizar V (`-ctv q4_0`, etc.). TurboQuant en `RustingStrata` requiere CUDA.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** `q8_0` tiene pérdida de calidad casi nula (en `RustingStrata` ~6 % más lento en decode 32K y ~14 % en prefill 32K por decuantización, pero reduce la KV a la mitad). `q4_0` o `<4 bits` degradan la recuperación exacta de identificadores si no hay rotación Hadamard/Walsh.
- **Prueba del protocolo (A–H) que la mide:** **B/C** (impacto en `pp`/`tg`), **E** (ahorro de VRAM/GTT a 8K–32K) y **F/G** (regresión en multiturno y código).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **Nivel N0 / N1.** `engine/server.py:219-221` solo permite `kv_cache_type` simétrico (`--cache-type-k` y `--cache-type-v` iguales). Conviene permitir configuración asimétrica (p. ej. `ctk=q8_0`, `ctv=q4_0` o `f16`/`q8_0`) condicionada a `-fa` activo, y añadirla a `tuning/buscador.py` con puerta de calidad en `tuning/bateria.py`.
- **Decisión F3:** `integrar` (KV `q8_0` en VRAM/GTT ajustada y probar asimétrico `q8_0/q4_0` cuando `-fa` esté disponible; `solo estudiar` TurboQuant y Hadamard KV al no estar en `llama-server` upstream).

---

### T6 · Reutilización de prefijos y estado
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Elimina el recálculo redundante de **prefill** (TTFT) en conversaciones multiturno, bucles agénticos y reanudación de sesiones tras reiniciar o cambiar de proyecto.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):**
  - **En `llama-server` (`llamacpp_server_README.md`):**
    1. `cache_prompt` compara los tokens entrantes con los del slot y solo evalúa el sufijo nuevo. Con `--cache-reuse N` (ya a `256` en `engine/server.py:155`), desplaza fragmentos KV mediante *KV shifting* a partir de `N` tokens coincidentes.
    2. `id_slot` fija la petición a un slot concreto para evitar que un sub-agente o tarea auxiliar pise el KV del usuario.
    3. `--slot-save-path DIR` + `POST /slots/{id}?action=save|restore|erase` vuelcan o restauran en disco el estado KV binario de un slot.
    4. En `llama.cpp` reciente, `--cache-ram N` aparca slots inactivos en RAM del host.
  - **En otros motores:** *agent-loop resume* (`OpenSet-LLM`), `--prompt-cache <DIR>` (`DynaLM`), `--cache-ram` + `--preserve-thinking` (`RustingStrata`), `RadixAttention` (`SGLang`, árbol radix para concurrencia).
  - **Cambios concretos necesarios en GuarIdA (*cache-aware prompting*):**
    1. **`engine/client.py`:** añadir `id_slot` y `cache_prompt` opcionales a `completar_chat()`, y métodos `guardar_slot(id_slot, filename)`, `restaurar_slot(id_slot, filename)` y `borrar_slot(id_slot)`.
    2. **`engine/server.py`:** añadir `slot_save_path: Optional[Path] = None` a `LlamaServerConfig` (`--slot-save-path` si figura en `--help`).
    3. **`chat.py` (L976-977, L1180-1184) y `web/server.py` (L991-992, L1040-1044):**
       - Quitar `({len(docs_idx)} archivos indexados)` de `prompt_sistema` para no invalidar toda la caché KV al reindexar un archivo.
       - Sacar `ctx_memoria` (`formatear_contexto_memoria_canonica`) del final de `prompt_usuario_final` y ubicarlo como bloque estable tras `prompt_sistema` (antes del historial).
       - Asignar `id_slot=0` (monousuario) y `cache_prompt=True`; al cambiar de sesión/proyecto o cerrar, usar `guardar_slot`/`restaurar_slot`.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md`, `rustingstrata_USAGE.md`, `OpenSet-LLM`, `DynaLM`, `SGLang`, y GuarIdA (`engine/client.py`, `engine/server.py`, `chat.py`, `web/server.py`).
- **Requisitos (modelo, hardware, formato, backend):** Cualquier GGUF en `llama-server`. `--slot-save-path` exige espacio en disco; `--cache-ram` exige RAM libre (acotar p. ej. `1024–2048` MiB en equipos de 8–16 GB).
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** `cache_prompt=True` puede variar mínimamente desempates numéricos entre prefill y decode; `--cache-reuse` tras saltos largos puede afectar levemente a la atención si el modelo es sensible a RoPE. Complejidad baja/media.
- **Prueba del protocolo (A–H) que la mide:** **F** (multiturno con prefijo estable + RAG/memoria) y **G** (edición/reanudación de código).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 + N3** en `engine/client.py`, `engine/server.py`, `chat.py`, `web/server.py` y `tuning/bateria.py`.
- **Decisión F3:** `integrar` (prioridad #1: estabilizar `prompt_sistema`/`ctx_memoria` + `id_slot`/`cache_prompt` da ganancia directa en TTFT sin cambiar de motor).

---

### T7 · Decodificación especulativa con modelo borrador (`-md` / `--model-draft`)
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Acelera **decode** generando *K* tokens candidatos con un modelo pequeño y verificándolos en paralelo con el modelo objetivo, empeorando ligeramente **carga** y **memoria**.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Un borrador de la misma familia/tokenizador (p. ej. `Qwen3-0.6B` para `Qwen3-4B`/`8B`) genera hasta `draft-max` tokens; el objetivo los verifica en un único forward paralelo manteniendo exactamente su distribución greedy. `engine/server.py:136-137,208-211` ya soporta `-md` y `--draft-max`, pero `aplicar_optimizaciones_seguras()` los excluye por riesgo de OOM. **Aviso de migración (`llamacpp_server_README.md`):** en `llama.cpp v1.0.0+`, `--draft-max`/`--draft-min` pasaron a `--spec-draft-n-max`, `--spec-draft-n-min`, `--spec-draft-p-min`, `--spec-type draft-simple`, `-ngld` y `-ctkd/-ctvd`.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md:116-117,255-296`, `rustingstrata_USAGE.md:89-100`, GuarIdA `engine/server.py`.
- **Requisitos (modelo, hardware, formato, backend):** Mismo tokenizador (`Qwen3-0.6B` + `4B/8B`); GPU dedicada de 8–16 GB con holgura para ambos modelos + KV. En iGPU/APU con GTT compartida o CPU puro, la contención de memoria suele anular la ganancia.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** ~0,5–1,0 GB extra de VRAM (riesgo de OOM en Vulkan si el modelo objetivo ya ajusta la GTT); incompatibilidad habitual con `-np > 1`; sin pérdida de calidad.
- **Prueba del protocolo (A–H) que la mide:** **B / C** (decode `tg`), puerta de calidad (equivalencia greedy) y **D/E** (VRAM pico).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N2** en `engine/server.py` (soporte dual de flags `b12017` vs `v1.0.0+`), `tuning/capacidades.py` y `tuning/buscador.py` (etapa opt-in solo si `target + draft + margen < gtt_disponible_gb`).
- **Decisión F3:** `integrar` (opt-in solo en GPU dedicada 8–16 GB con holgura de VRAM, nunca por defecto en iGPU/CPU).

---

### T8 · DFlash2, EAGLE-3 y MTP
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Acelera **decode** eliminando el borrador autoregresivo secuencial: genera bloques completos en paralelo (**DFlash2**), predice múltiples tokens desde cabezas integradas (**MTP**) o desde características ocultas multinivel (**EAGLE-3**).
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):**
  - **DFlash2 (`z-lab/dflash`, `llama.cpp` PR #27342 / `v1.0.0+`):** modelo ligero de *block diffusion* con convoluciones dinámicas de dos pasos sobre estados ocultos del objetivo (`block_size <= 5` en 4-bit; en `llama.cpp` `--spec-type draft-dflash2`).
  - **MTP / EAGLE-3:** en `llama.cpp v1.0.0+` `--spec-type draft-mtp` / `draft-eagle3`.
  - **Límites reales (`Strata v0.2.23`, `rustingstrata_USAGE.md`):** DFlash2 **empeora** en hardware limitado por ancho de banda de memoria, en chat creativo o razonamiento largo y con concurrencia > 8; MTP pierde rendimiento en MoE si los expertos están en CPU (`RTX 3060 12 GB`).
- **Proyectos / archivos de referencia:** `z-lab/dflash`, `ggml-org/llama.cpp` PR #27342 (`llamacpp_server_README.md:282`), `Niko1221/Strata v0.2.23`, `rustingstrata_USAGE.md:83-105`, `OpenVINO GenAI`, `DynaLM`.
- **Requisitos (modelo, hardware, formato, backend):** Exige `llama.cpp v1.0.0+` (`b12017` no lo tiene), sidecar GGUF específico por modelo exacto (~0,55 GB) y GPU con holgura de VRAM/ancho de banda.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** Complejidad alta (actualizar binario + gestionar sidecars por modelo) y riesgo real de regresión en APU/iGPU y en chat/razonamiento.
- **Prueba del protocolo (A–H) que la mide:** **B / C** y **F / G** (separando código frente a chat/razonamiento).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N4** (bloqueado hasta migrar `downloader/binaries.py` desde `b12017` a `v1.0.0+`).
- **Decisión F3:** `solo estudiar` (posponer hasta evaluar la actualización de `llama-server` a `v1.0.0+` en F2/F4; priorizar antes T9 por riesgo cero).

---

### T9 · Prompt lookup / n-gram / suffix
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Acelera el **decode** sin modelo borrador ni VRAM extra cuando la respuesta reutiliza fragmentos literales del prompt (edición de código, refactorización, JSON, citas).
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Toma los últimos *N* tokens generados, busca coincidencias en el contexto previo o tabla n-gram y propone los *M* tokens siguientes para verificarlos en paralelo con el modelo objetivo. En `b12017` (`engine/server.py:135,205-206`) existe `--lookup-cache`; en `llama.cpp v1.0.0+` (`llamacpp_server_README.md:164-165,282-294`) evoluciona a `-lcs`/`-lcd` y `--spec-type ngram-simple | ngram-mod` (pool ligero ~16 MB con *rolling hash*). `RustingStrata` / `Strata` reportan **+6–11 %** en edición de código y hasta **~2×** en texto repetitivo en Vulkan; `Ghost Infer` lo activa por defecto.
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md`, `ik_llama.cpp`, `rustingstrata_USAGE.md:106-119`, `rustingstrata_CALIBRATION.md:142-162`, `Ghost Infer`, GuarIdA `engine/server.py`.
- **Requisitos (modelo, hardware, formato, backend):** Cualquier modelo GGUF en CPU, Vulkan o CUDA; ~0–16 MB RAM extra, 0 VRAM extra.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** Cero pérdida de calidad (verificación exacta). En prosa libre sin repetición puede añadir ~2–5 % de overhead si el borrador es demasiado largo.
- **Prueba del protocolo (A–H) que la mide:** **G** (edición de código / refactorización) como prueba principal + **C** (prosa) para descartar regresiones.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N1** en `engine/server.py` (comprobar soporte en `--help` y activar en perfil código), `tuning/capacidades.py`, `tuning/bateria.py` y `tuning/buscador.py` (incorporar escenario G).
- **Decisión F3:** `integrar` (prioridad alta: coste nulo en VRAM, cero descargas extra y ataque directo al caso de uso principal de GuarIdA).

---

### T10 · Reparto y caché dinámica de expertos MoE
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Permite ejecutar modelos MoE (p. ej. `Qwen3-30B-A3B`) cuyos pesos superan la VRAM o la apertura GTT compartida (8–16 GB), evitando OOM en **carga** y reduciendo el cuello de botella PCIe en **prefill/decode**.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):**
  - `llama-server`: `-cmoe`/`--cpu-moe`, `-ncmoe N` (`--n-cpu-moe`), `-ot <regex>=<buffer>`, `--moe-cache-mib N` (caché VRAM para expertos en host) y `--moe-cache-cpu-share F` (fracción de fallos que se ejecutan en CPU sin subir por PCIe).
  - `ik_llama.cpp`: `ClassLRU` (frecuencia + decaimiento temporal) para reducir fallos de caché.
  - `RustingStrata` (`src/expert_cache.rs`): reequilibra dinámicamente expertos entre VRAM y CPU según el enrutamiento real (`STRATA_FIXED_EXPERTS=1` fija el reparto para greedy reproducible).
  - `Strata`, `Golem`, `KTransformers`, `FastLLM`: atención y expertos calientes en GPU; expertos fríos en RAM/CPU en paralelo (o memoria host direccionable en Vulkan).
- **Proyectos / archivos de referencia:** `llamacpp_server_README.md`, `ik_llama.cpp`, `RustingStrata` (`src/expert_cache.rs`), `Strata`, `Golem`, `KTransformers`, `FastLLM`.
- **Requisitos (modelo, hardware, formato, backend):** Modelo MoE GGUF + RAM suficiente para expertos fríos.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** Si la caché es pequeña aparece *thrashing* PCIe; la reasignación dinámica altera el orden de reducción numérica (empates greedy).
- **Prueba del protocolo (A–H) que la mide:** **H** (MoE híbrido: todo RAM, `--n-cpu-moe`, `-ot`, `--moe-cache-mib`) + **B/C/D**.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N1** en `engine/server.py` (exponer `-cmoe`, `--moe-cache-mib`, `--moe-cache-cpu-share` junto a `--n-cpu-moe` y `-ot` ya permitidos), `tuning/capacidades.py` y `tuning/buscador.py` (etapa MoE condicional cuando el modelo sea MoE o supere VRAM/GTT).
- **Decisión F3:** `integrar` (exponer flags MoE de `llama-server` y añadir exploración condicional en `tuning/`).

---

### T16 · Separación servidor / motor / pipeline e interfaz `MotorInferencia`
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Desacopla GuarIdA de las flags concretas de `llama-server`, unifica la **telemetría** (`prefill`, `decode`, `cache_n`) y prepara el camino para motores intercambiables en F6 sin reescribir el arnés.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** `mistral.rs` separa **Server** (HTTP), **Engine** (planificador/batching) y **Pipeline** (arquitectura/cuantización/backend); `RustingStrata` unifica el esquema JSON de `timings` (`prompt_n`, `prompt_ms`, `prompt_per_second`, `predicted_n`, `predicted_ms`, `predicted_per_second`, `cache_n`), `GET /props` y `POST /tokenize`, y hace que `calibrate` consuma un formato único de benchmark.
- **Proyectos / archivos de referencia:** `mistral.rs`, `rustingstrata_USAGE.md`, `rustingstrata_CALIBRATION.md`, GuarIdA `engine/server.py`, `engine/client.py`, `tuning/`.
- **Requisitos (modelo, hardware, formato, backend):** Python `Protocol`/`ABC` usando solo librería estándar.
- **Coste o riesgo (calidad, memoria extra, complejidad, licencia):** Evitar sobre-ingeniería antes de tener datos de F4; diseñar una interfaz mínima compatible primero con `llama-server`.
- **Prueba del protocolo (A–H) que la mide:** **A–H** (recolección uniforme de métricas y `cache_n`).
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N1 / N3** en `engine/base.py` (nuevo), `engine/client.py` (exponer `timings`, `GET /props`, `id_slot`, `cache_prompt`, `/slots`), `engine/server.py` y `tuning/ejecutor.py`.
- **Decisión F3:** `integrar` (completar `engine/client.py` para F2 y dejar diseñada la interfaz `MotorInferencia` para F5/F6).

---

### T18 · KVMem (KV cache jerárquico GPU + RAM)
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Permite contextos de 64K–1M tokens con VRAM limitada paginando páginas KV en RAM y recuperándolas por contenido (`memoria`, `prefill`, `decode`, riesgo en `calidad`).
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** En `FastLLM` (`fastllm_kvmem.md`), divide el historial en páginas fijas en RAM de host (*pinned*) y mantiene en GPU un presupuesto `resident_tokens` (`sink + recent + retrieval`). Indexa cada página con la media FP32 de sus claves **antes de RoPE** (`pre-RoPE mean-K`) y trae a VRAM solo las páginas mejor puntuadas por la query actual.
- **Proyectos / archivos de referencia:** `FastLLM` (`fastllm_kvmem.md`), `kvmem/kvmem-llama.cpp`.
- **Requisitos / Coste o riesgo:** Exclusivo de `FastLLM` (CUDA), incompatible con *prefix caching* compartido y **es atención dispersa aproximada**: omitir páginas puede degradar la recuperación exacta de símbolos en código.
- **Prueba del protocolo (A–H) que la mide:** **E** (32K–128K), **D**, **F**.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N3 / N4**; no existe en `llama-server` GGUF. En 8–32K el RAG AST (`arbol_nodos.py`) + KV `q8_0` (`T4`) cubren la necesidad con exactitud.
- **Decisión F3:** `solo estudiar`.

---

### T19 · Atención dispersa en prefill (`Tri-shape` / `XAttention`) y KV token eviction
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Reduce el coste cuadrático de `prefill` en prompts muy largos y acota la `memoria` de KV mediante descarte de tokens de baja importancia.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** `OpenVINO GenAI` (`SchedulerConfig`) combina prefill disperso por bloques (`Tri-shape`, `XAttention` por antidiagonales) con `cache_eviction_config` (protege *Start Area* y *Recent Area*, expulsa permanentemente tokens de *Evictable Area*).
- **Proyectos / archivos de referencia:** `openvinotoolkit/openvino.genai`.
- **Requisitos / Coste o riesgo:** Específico de `OpenVINO GenAI` (formato IR, hardware Intel); la expulsión permanente de KV puede borrar nombres de variables o reglas clave en código.
- **Prueba del protocolo (A–H) que la mide:** **B/D** (TTFT > 8K), **E**, **F/G**.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N3 / N4** (si `OpenVINO GenAI` entra en F4 para perfil Intel, validar con puerta de calidad en código).
- **Decisión F3:** `solo estudiar`.

---

### T20 · Auditoría de "Token Inflation Trap"
- **Qué problema resuelve y en qué fase (prefill / decode / carga / memoria / calidad):** Evita elegir modelos/cuantizaciones `< Q4` que aparentan más `tok/s` pero generan cadenas `<think>` mucho más largas por pérdida de certeza, empeorando **latencia total** y **calidad**.
- **Cómo funciona (en palabras propias, con referencia técnica o código fuente leído):** Las cuantizaciones agresivas en modelos de razonamiento aumentan el *CoT Token Inflation Ratio* (bucles de auto-verificación), haciendo que el tiempo total hasta la respuesta correcta suba aunque `decode tok/s` sea mayor. `RustingStrata` (`rustingstrata_USAGE.md:166-168`) mitiga el techo con `--thinking-budget N` (inyecta `</think>` al alcanzar `N`).
- **Proyectos / archivos de referencia:** Estudio empírico sobre *Token Inflation Trap*, `RustingStrata` (`--thinking-budget`), GuarIdA `tuning/bateria.py` y `tuning/scoring.py`.
- **Requisitos / Coste o riesgo:** Ninguno en runtime; solo añadir métricas de longitud `<think>` y `tiempo_total_hasta_acierto` al evaluador.
- **Prueba del protocolo (A–H) que la mide:** **F / G / H** + puerta de calidad.
- **Encaje en GuarIdA (nivel N0–N4 y módulos concretos afectados):** **N0 / N1** en `tuning/bateria.py` y `tuning/scoring.py`.
- **Decisión F3:** `imitar` (incorporar medición de tiempo total hasta acierto y desglose `<think>` antes de recomendar cuantizaciones `< Q4`).

---

## Plan de experimentos N0 listo para F2

Antes de tocar motores externos (F4), **F2** medirá el `llama-server` actual de GuarIdA (`b12017`) y su posible actualización a `v1.0.0`+ aplicando directamente las conclusiones de F3 en una batería controlada (**pruebas A–G** de [02_protocolo_benchmark.md](02_protocolo_benchmark.md)):

| Exp. | Configuración a medir frente al baseline actual de `tuning/` | Técnicas | Qué esperamos comprobar |
|---|---|---|---|
| **N0-Base** | `llama-server b12017` con perfil actual de `tuning/` (sin `id_slot`, `-fa off` en no-NVIDIA, KV `f16`) | — | Línea base real (especialmente TTFT en **F** y tok/s en **E/G**) |
| **N0-1** | Igual que `N0-Base` + **arnés estable** (quitar `len(docs_idx)` de `prompt_sistema`, mover `ctx_memoria` a prefijo fijo, `id_slot=0`, `cache_prompt=True`) | **T6 + T17** | Caída drástica de TTFT en turnos 2–5 de **F** |
| **N0-2** | `N0-1` + **`-fa` habilitado en Vulkan/CPU** + **KV `q8_0`** (y prueba asimétrica `q8_0/q4_0` si `-fa` activo) + **`-lm none` / `--no-mmap`** en GTT Windows | **T5 + T4 + T1** | Menor VRAM/GTT y mejor *prefill/decode* en **E** (8K–16K) sin degradar calidad |
| **N0-3** | `N0-2` + **`--lookup-cache`** (en `b12017`) / `--spec-type ngram-mod` (en `v1.0.0`+) | **T9** | Ganancia en edición de código (**G**) y verificación de cero regresión en prosa (**C**) |
| **N0-4** | `N0-2` + **`--slot-save-path`** (`save`/`restore` entre sesiones) | **T6** | Tiempo de reanudación en frío de un proyecto con 8K de contexto |
| **N0-5** | *(Solo si hay GPU ≥12 GB o MoE)* **`-md Qwen3-0.6B`** (`T7`) y **`-ncmoe` / `--moe-cache-mib`** (`T10`) | **T7 + T10** | Viabilidad y ganancia real frente a contención de bus |
| **N0-Up** | Comparar `llama-server b12017` vs **`llama.cpp v1.0.0+`** en `N0-3` (y evaluar DFlash2 en F4 si aporta) | **T8 + T9** | Si actualizar el binario distribuido en `binaries.py` mejora Vulkan/CPU por sí solo |

---

## Base arquitectónica preliminar para F5 / F6

Si F4 confirma que merece la pena soportar más de un motor según perfil de hardware (por ejemplo `OpenVINO GenAI/OVMS` en Intel o `ik_llama.cpp`/`mistral.rs`/`RustingStrata` en escenarios concretos), la integración en F6 seguiría el patrón de **T16** sin romper el resto de GuarIdA:

```text
chat.py / web/server.py / proyectos.py  (arnés estable T6+T17, sin flags de motor)
          │
          ▼
   MotorInferencia (ABC/Protocol en engine/base.py)
   ├── ciclo_vida: arrancar(cfg), detener(), salud(), capacidades()
   ├── inferencia: completar_chat(..., id_slot, cache_prompt), completar_texto()
   ├── estado:     guardar_slot(id, ruta), restaurar_slot(id, ruta)
   ├── utilidades: props(), tokenizar(), embedding()
   └── telemetría: TimingsNormalizados(prompt_n, prompt_ms, predicted_n, predicted_ms, cache_n)
          │
          ├── AdaptadorLlamaServer   (N0 — siempre disponible, Windows/Linux/Vulkan/CPU)
          └── Adaptadores opcionales (N1/N2 — solo si ganan en F4 y cumplen licencia)
```

Y `tuning/` (`buscador.py`, `bateria.py`, `scoring.py`) evolucionará para:
1. Incluir escenarios cortos equivalentes a **F (multiturno)** y **G (edición de código)**, no solo una petición aislada.
2. Aplicar una **puerta de calidad + auditoría *Token Inflation Trap* (`T13 + T20`)** antes de premiar velocidad.
3. Explorar condicionalmente `T9` (lookup), `T10` (MoE) y `T7` (borrador si hay holgura real de VRAM).
