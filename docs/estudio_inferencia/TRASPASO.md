# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`, ya subida a `origin`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fases cerradas:**
  - **F0 · Encuadre** (documentación, reglas, protocolo, catálogo de técnicas, ADR 0013 propuesto).
  - **F1 + Mini-F1b · Verificación de fuentes** (todas las fichas verificadas contra API GitHub / README / releases / `LICENSE.md` / `config.json` oficiales de Qwen3 en HF / agregador `awesome-local-inference-recipes`, incluidos `Niko1221/Strata`, `RustingStudio/RustingStrata` y `z-lab/dflash`).
- **Orden acordado para las siguientes fases:** **F3 (Estudio de técnicas)** → **F2 (Línea base GuarIdA + N0)** → **F4 (Laboratorio)** → **F5 (ADR 0014)** → **F6 (Prototipo)**.
- **No se ha modificado código** de GuarIdA en esta rama todavía.

## Conclusión ejecutiva de F1 + Mini-F1b (para no releer todo)

1. **`llama.cpp` (`llama-server`, hoy `b12017` en GuarIdA; upstream ya en `v1.0.0`+) sigue siendo el único motor maduro con Windows + Linux + Vulkan (APU/iGPU AMD/Intel) + CPU + GGUF + API OpenAI + tool calling.**
2. **Resultados de Mini-F1b (`Strata`, `RustingStrata`, `DFlash2`):**
   - **`RustingStrata`** (`RustingStudio/RustingStrata`, `v1.4.2`): Rust puro, binarios Windows/Linux, GGUF nativo, API OpenAI + `/tokenize` + GBNF, **Vulkan 1.3** + CUDA + HIP, TurboQuant KV (`turbo4/3/2`), `calibrate`, caché adaptativa MoE GPU+CPU y DFlash2. **Dos límites críticos:** (a) su licencia **RustingStrata License 1.0** es *source-available* no-OSI (prohíbe revender el motor) e incompatible con empaquetado GPL-3.0 (solo binario externo no redistribuido), y (b) en Vulkan exige `shaderFloat64`, por lo que **no soporta Intel Arc**.
   - **`Strata`** (`Niko1221/Strata`, `v0.2.23`, `MIT`): Windows+Linux, CUDA y AMD HIP (incl. Strix Halo), DFlash 2 por defecto, caché de conversación en RAM y `--turbo`. **Sin Vulkan ni CPU-only.**
   - **`DFlash2`** (`z-lab/dflash`, `MIT`): pesos drafter y herramienta de evaluación para especulación sin pérdida por difusión en bloques; ya tiene **PR en `llama.cpp` (#27342)**, `ik_llama.cpp`, `OpenVINO GenAI`, `Strata` y `RustingStrata`.
3. **Candidatos que pasan a F4 (laboratorio):**
   - `llama.cpp` (`b12017` vs `v1.0.0`+): **línea base N0** + flags no exploradas por `tuning/` + DFlash2/MTP.
   - `OpenVINO GenAI` (+ OVMS): **N2 solo en hardware Intel** (CPU/iGPU/NPU; probar GGUF preview vs IR INT4; desactivar telemetría GA4).
   - `ik_llama.cpp`: **N1 parcial solo en CPU-only x86-64 o NVIDIA CUDA** (sin Vulkan, sin binarios Windows oficiales).
   - `mistral.rs`: **N2 solo en CPU o Linux CUDA `sm80+`** (sin Vulkan ni CUDA Windows; tiene GGUF y prefix caching).
   - `DynaLM`: **N2 exploratorio** (binarios Windows Vulkan, `--prompt-cache` y EAGLE-3, pero sin tool calling y 4 estrellas).
   - `MLC LLM`: **N2 acotado a Vulkan AMD/Intel** (sin CPU, sin GGUF, solo nightlies).
   - `Strata` (**N2 GPU dedicada CUDA/HIP**) y `RustingStrata` (**N2 binario externo Vulkan AMD/NVIDIA o CUDA, sin Intel Arc**).
4. **Candidatos que pasan solo a F3 (técnicas N3):** `Ghost Infer`, `Golem`, `Herbert-rs` (sin mantenimiento), `OpenSet-LLM`, `KTransformers`, `FastLLM` (**KVMem**), `ExLlamaV3`, `SGLang` (RadixAttention), `vLLM` (PagedAttention), y **`DFlash2`**.
5. **Descartados:** `llm.asm`, `Candle`, `Megakernel Zoo`, `ExLlamaV2`, `openvino` core.
6. **Arquitectura Qwen3 confirmada** en HF `config.json`: `Qwen3-30B-A3B` tiene **48 capas** (no 24), 4 cabezas KV, 128 expertos (8 activos), `ctx=40960`.
7. **Aviso legal:** `h9-tec/LLM-Inference-Handbook` **no tiene licencia** (*All Rights Reserved*) — prohibido copiar contenido; solo referencia conceptual.

## Orden de lectura

1. [README.md](README.md): objetivo, preguntas, reglas, fases y niveles de adopción.
2. [01_inventario_candidatos.md](01_inventario_candidatos.md) y [01b_agregador_y_manual.md](01b_agregador_y_manual.md): fichas verificadas en F1 + Mini-F1b.
3. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md): técnicas T1–T20 para **F3 (fase actual)**.
4. [02_protocolo_benchmark.md](02_protocolo_benchmark.md): pruebas A–H y formato JSONL para **F2** y **F4**.
5. Código relevante de GuarIdA: `app/guarida_manager/engine/server.py`, `engine/client.py`, `app/guarida_manager/tuning/`, `downloader/binaries.py` (`b12017`), `hardware*.py`, `cache.py`.

## Siguientes tareas concretas

### 1. Fase actual: F3 · Estudio de técnicas (sin requerir hardware de benchmark)
Rellenar las fichas técnicas de [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md) leyendo el código/documentación de los repositorios de referencia y clasificándolas como `integrar` / `imitar` / `solo estudiar` / `descartar`:
1. **T6** (caché de prefijos y estado: *cache-aware prompting* en el arnés de GuarIdA, `--slot-save-path`, *agent-loop resume* de OpenSet-LLM, RadixAttention, caché escalada en RAM de Strata).
2. **T7 / T8 / T9** (especulación sin pérdida: `-md` Qwen3-0.6B, **DFlash2** `z-lab/dflash` + `llama.cpp` PR #27342, MTP, `--lookup-cache` / `suffix` en edición de código).
3. **T4 / T18 / T19** (KV cuantizada: `-ctk/-ctv`, **TurboQuant** de RustingStrata, Hadamard KV de `ik_llama.cpp`; **KVMem** de FastLLM; XAttention/Tri-shape de OpenVINO GenAI).
4. **T10** (reparto y caché dinámica de expertos MoE: `-ot`/`--n-cpu-moe`, `ik_llama.cpp` ClassLRU, `RustingStrata` `expert_cache.rs`, `Strata`, `Golem`).

### 2. Después de F3: F2 · Línea base GuarIdA + quick-wins N0
1. Crear `docs/estudio_inferencia/resultados/prompts/` con prompts fijos (A–G, español + código, sin datos personales).
2. Ejecutar las pruebas A–G contra el `llama-server b12017` actual de GuarIdA en el equipo local (registrar `hash_hardware`, perfil y JSONL en `resultados/`), midiendo baseline actual de `tuning/` vs **N0 afinado** (incluyendo las técnicas seleccionadas en F3) y valorar actualización de `b12017` a `llama.cpp v1.0.0`+.

## Reglas que no hay que romper

- **No inventar cifras.** Lo no medido se queda en `null` o como "afirmación del autor".
- **No mezclar formatos** de cuantización distintos en una misma tabla de velocidad.
- **Comparar siempre contra `llama-server` bien afinado**, no con valores por defecto.
- **Medir calidad y tiempo total** (cuidado con la *Token Inflation Trap* en modelos de razonamiento cuantizados).
- **Coste de integración, privacidad offline y licencia cuentan tanto como la velocidad.** GuarIdA es GPL-3.0, 100 % offline, Windows + Linux.
- Los cambios de código derivados del estudio van en ramas propias a partir de esta (p. ej. `estudio/n0-flags-afinador`), con tests.

## Convención de commits en esta rama

`docs(estudio): …` para documentación; `bench(estudio): …` para resultados y scripts de medida; `feat(estudio): …` para prototipos. Mensajes en español.

## Bitácora

| Fecha | Quién | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-11-28 | Antigravity (Claude Opus) | F0: fases, reglas, inventario inicial, protocolo A–H, catálogo de técnicas, ADR 0013 propuesto. Creada rama `estudio/motores-inferencia` (`0dc95b8`). Descargadas fuentes primarias y `config.json` de Qwen3 | Completar F1 |
| 2026-11-28 | Antigravity (Gemini) | F1 cerrada: push inicial, verificación paralela con guardado incremental de 20+ repos, agregador `awesome-local-inference-recipes` (1.328 filas), 12 proyectos sin enlace y 4 modelos recientes, `config.json` oficiales de Qwen3 (confirmado 48 capas en 30B-A3B), mapa legal del `Handbook`, actualización de inventario, protocolo, técnicas y traspaso (`927c629`) | Mini-F1b (`Strata`, `RustingStrata`, `DFlash2`) |
| 2026-11-28 | Antigravity (Gemini) | Mini-F1b cerrada y reordenación a **F3 → F2**: verificados `Niko1221/Strata` (`v0.2.23`, MIT, CUDA/HIP sin Vulkan), `RustingStudio/RustingStrata` (`v1.4.2`, licencia *source-available* `RustingStrata 1.0` incompatible con empaquetado GPL-3.0, Vulkan sin Intel Arc por `shaderFloat64`, GGUF+TurboQuant) y `z-lab/dflash` (MIT, PR #27342 en `llama.cpp`) | Empezar **F3** (fichas de técnicas T6, T7–T9/DFlash2, T10, T4/T18/T19) |
