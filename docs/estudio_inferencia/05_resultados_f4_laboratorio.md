# 05 · Resultados de Fase 4 · Laboratorio multimotor (Perfil B Intel)

> **Estado:** **Fase 4 cerrada en Perfil B (2026-11-28).** Comparativa directa de 8 perfiles sobre el **mismo archivo GGUF** (`Qwen3-4B-Q4_K_M.gguf`) en hardware doméstico real (`i5-1135G7` + `Intel Iris Xe` + Windows 11). Datos en bruto: [2026-11-28_731271e2_f4_qwen3-4b.jsonl](resultados/2026-11-28_731271e2_f4_qwen3-4b.jsonl). Runner: [bench_estudio_f4.py](../../herramientas/bench_estudio_f4.py).

---

## 1. Entorno y artefactos verificados

- **Hardware (Perfil B):** `11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz` (4C/8T), `31,64 GB RAM`, `Intel(R) Iris(R) Xe Graphics` (`Vulkan0`, `15,82 GB` GTT compartida), `hash_hardware`: `731271e2a58e85b04463a945ce07b2827482d386761287eaebdf6b2c18a6dc86`.
- **Modelo único:** `Qwen3-4B-Q4_K_M.gguf` (`2.381,59 MiB`, `sha256: 7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`).
- **Homogeneización:** sufijo `/no_think` añadido de forma uniforme al último mensaje de usuario para evitar que `Qwen3-4B` agote `max_tokens` dentro de `<think>`.
- **Motores y versiones probadas:**
  - `llama.cpp` `b12017` (`0.8.0-dev`, commit `5047748f1`, binario actual de GuarIdA) — Vulkan y CPU.
  - `llama.cpp` `b12823` (`1.1.0-dev`, commit `3ab385146`, última release Windows Vulkan) — Vulkan.
  - `DynaLM v0.6.0` (binarios oficiales Windows x64 Vulkan y CPU, `--prompt-cache`).
  - `mistral.rs v0.9.5` (binario oficial Windows x64 CPU, `--prefix-cache-n 8`).
  - `OpenVINO GenAI 2026.4.1.0` (`OpenVINO 2026.4.1`, `OPENVINO_TELEMETRY_OPT_OUT=1`, carga directa de GGUF en `GPU` y `CPU`).

---

## 2. Tabla comparativa principal (mismo GGUF `Qwen3-4B-Q4_K_M`)

| Motor | Backend | Rep. | Startup (ms) | B · TTFT / TG | C · TTFT / TG | G (Código) · TTFT / TG | RAM pico (MB) | Calidad (`Q`) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **`llama-latest-N0win` (`b12823`)** | **Vulkan** | 2 | 4.210 | **7,49 s / 12,96 t/s** | **32,85 s / 14,42 t/s** | **15,06 s / 42,16 t/s** | 4.736–8.272 | `ok` / `ok` |
| **`llama-b12017-N0win`** | **Vulkan** | 2 | 4.526 | 10,67 s / 8,57 t/s | 36,28 s / 7,41 t/s | 19,75 s / **40,19 t/s** | 4.696–7.251 | `ok` / `ok` |
| **`dynalm-vulkan` (`v0.6.0`)** | Vulkan | 2 | **1.605** | 8,09 s / 8,68 t/s | 53,13 s / 6,20 t/s | 21,58 s / 5,58 t/s | 6.542–7.327 | `ok` / `ok` |
| **`openvino-genai-gpu` (`2026.4.1`)** | Intel GPU | 1 | 24.512 | 23,45 s / 7,04 t/s | 96,88 s / 6,50 t/s | 36,13 s / 5,42 t/s | **9.624** | `ok` / `ok` |
| **`llama-b12017-CPU`** | CPU | 2 | 2.302 | 12,53 s / 5,78 t/s | 56,24 s / 3,93 t/s | 24,97 s / **25,21 t/s** | **3.715–5.096** | `ok` / `ok` |
| **`mistralrs-cpu` (`v0.9.5`)** | CPU | 1 | 4.941 | 57,96 s / 6,40 t/s | *(>7 min)* | — | **8.898** | — |
| **`openvino-genai-cpu` (`2026.4.1`)** | CPU | 1 | 30.510 | 40,99 s / 5,03 t/s | 143,55 s / 3,53 t/s | *(detenido)* | 8.148–8.427 | — |
| **`dynalm-cpu` (`v0.6.0`)** | CPU | 2 | 2.528 | 40,77 s / 4,89 t/s | 144,48 s / 1,60 t/s | *(detenido)* | 5.745–6.432 | — |

---

## 3. Agente multiturno (`F_estable`, turnos 1–3)

| Motor | T1 · TTFT / TG | T2 · TTFT / TG | T3 · TTFT / TG | Cache tok (T1→T3) |
|---|---|---|---|---|
| **`llama-b12017-N0win`** | 29,21 s / **18,40 t/s** | 2,76 s / **21,38 t/s** | 2,48 s / **10,04 t/s** | 2.667 → 5.329 → 5.430 |
| **`llama-latest-N0win` (`b12823`)** | 27,96 s / 10,27 t/s | 3,05 s / 7,02 t/s | 2,64 s / 9,79 t/s | 2.667 → 5.329 → 5.441 |
| **`dynalm-vulkan` (`v0.6.0`)** | 51,46 s / 6,46 t/s | **1,87 s** / 6,16 t/s | **1,84 s** / 6,38 t/s | *(interno)* |
| **`openvino-genai-gpu`** | 55,99 s / 6,29 t/s | 4,79 s / 6,23 t/s | 4,45 s / 6,16 t/s | *(interno)* |
| **`llama-b12017-CPU`** | 51,19 s / 5,19 t/s | 6,05 s / 3,53 t/s | 5,28 s / 3,25 t/s | 2.667 → 5.329 → 5.442 |

---

## 4. Registro honesto de incidencias y límites observados

1. **`dynalm-cpu` (`v0.6.0`):** detenido tras completar 2 repeticiones de `B` y `C` porque `C` tardó **144,48 s de TTFT y 1,60 t/s en decode** (2,5× más lento que `llama-b12017-CPU` y 9× más lento que `llama-latest-N0win`). Además no soporta *tool calling* en `v0.6.0`.
2. **`mistralrs-cpu` (`v0.9.5`):** detenido tras >7 min; completó `B` (`6,40 t/s` en decode), pero con **TTFT de 57,96 s** (4,6× más lento en prefill que `llama-b12017-CPU`) y un pico de **8,90 GB de RAM** para un modelo de 2,38 GB.
3. **`openvino-genai-cpu` (`2026.4.1`):** detenido tras completar `B` (`5,03 t/s`, TTFT `40,99 s`) y `C` (`3,53 t/s`, TTFT `143,55 s`, RAM `8,43 GB`). En carga directa de GGUF queda por detrás de `llama-b12017-CPU` y exige **30,5 s** de compilación/arranque inicial.
4. **`openvino-genai-gpu` (`2026.4.1`):** cargó GGUF directamente sobre Intel Iris Xe y pasó `Q`, pero tardó **24,5 s** en arrancar, consumió **9,62 GB de RAM** y rindió la mitad que `llama-latest-N0win` (`6,50` vs `14,42 t/s` en `C`; prefill 3× más lento). *(No se ejecutó conversión aparte a IR INT4 porque implicaría duplicar el catálogo fuera de GGUF en GuarIdA).*
5. **Motores pendientes de otros perfiles (C/D):** `ik_llama.cpp`, `Strata`, `RustingStrata` y `MLC LLM` no aplicaban a Perfil B Intel CPU/iGPU (o requieren GPU dedicada AMD/NVIDIA) y quedan documentados en [01_inventario_candidatos.md](01_inventario_candidatos.md).

---

## 5. Veredicto preliminar de F4 (de cara a F5 · ADR 0014)

1. **`llama.cpp` con Vulkan + optimizaciones N0 es el ganador indiscutible en Perfil B (hardware doméstico Intel Iris Xe / CPU):** supera en prefill, decode, memoria, arranque y compatibilidad (*tool calling* + GGUF único) a `DynaLM`, `mistral.rs` y `OpenVINO GenAI` en GGUF.
2. **Actualizar `llama.cpp` de `b12017` a `b12823`+ (`v1.1.0-dev`) da un salto enorme gratis:** en `Qwen3-4B Q4_K_M` sobre Iris Xe Vulkan pasa de **`8,57 -> 12,96 t/s`** en `B` (**+51 %**), de **`7,41 -> 14,42 t/s`** en `C` (**+95 %**), y de **`10,81 -> 1,67 s`** de TTFT en `Q` manteniendo `42,16 t/s` en edición de código (`G`) con `ngram-mod`.
3. **No merece la pena sustituir `llama-server` por `DynaLM`, `mistral.rs` ni `OpenVINO GenAI` en GuarIdA** (ni añadir el coste de mantener múltiples formatos/runtimes para Perfil B). La recomendación para **F5 (ADR 0014)** apunta a **N0 + N1 parcial**: actualizar `llama-server` en `downloader/binaries.py`, aplicar los ajustes N0 (`T6+T17`, `T9` `ngram-mod`, `T5/T4` según holgura GTT, `T1`, `T13+T20`) y mantener la interfaz `MotorInferencia` (`T16`) ligera por si en el futuro se añade un adaptador opcional en perfil C/D.
