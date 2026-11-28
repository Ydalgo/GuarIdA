# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`, ya subida a `origin`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fases cerradas:**
  - **F0 · Encuadre** (documentación, reglas, protocolo, catálogo de técnicas, ADR 0013 propuesto).
  - **F1 · Verificación de fuentes** (todas las fichas verificadas contra API GitHub / README / releases / `config.json` oficiales de Qwen3 en HF / agregador `awesome-local-inference-recipes`).
- **Siguientes fases:** **F2 · Línea base GuarIdA** y **F3 · Estudio de técnicas** (pueden ejecutarse en paralelo). Opcionalmente una mini-verificación **F1b** para `Niko1221/Strata` y `RustingStudio/RustingStrata` (descubiertos en F1 con fuerte tracción en MoE + Vulkan).
- **No se ha modificado código** de GuarIdA en esta rama todavía.

## Conclusión ejecutiva de F1 (para no releer todo)

1. **`llama.cpp` (`llama-server`, hoy `b12017` en GuarIdA; upstream ya en `v1.0.0`+) sigue siendo el único motor maduro con Windows + Linux + Vulkan (APU/iGPU AMD/Intel) + CPU + GGUF + API OpenAI + tool calling.** Casi ningún rival cubre Vulkan en Windows.
2. **Candidatos que pasan a F4 (laboratorio):**
   - `llama.cpp` (`b12017` vs `v1.0.0`+): **línea base N0** + exprimir flags no exploradas por `tuning/` (`-md`, `--lookup-cache`, `--slot-save-path`, `-ot`/`--n-cpu-moe`, MTP/DFlash2).
   - `OpenVINO GenAI` (+ OVMS): **N2 solo en hardware Intel** (CPU/iGPU/NPU; probar GGUF preview vs IR INT4; ¡desactivar telemetría GA4!).
   - `ik_llama.cpp`: **N1 parcial solo en CPU-only x86-64 o NVIDIA CUDA** (sin Vulkan, sin binarios Windows oficiales).
   - `mistral.rs`: **N2 solo en CPU o Linux CUDA `sm80+`** (sin Vulkan ni CUDA Windows; tiene GGUF y prefix caching).
   - `DynaLM`: **N2 exploratorio** (tiene binarios Windows Vulkan, `--prompt-cache` y EAGLE-3, pero sin tool calling y solo 4 estrellas).
   - `MLC LLM`: **N2 acotado a Vulkan AMD/Intel** (sin CPU, sin GGUF, solo nightlies).
3. **Candidatos que pasan solo a F3 (técnicas N3):** `Ghost Infer` (lookup exacto + caché MoE, descartado como motor por NVRTC EULA + solo CUDA), `Golem` (offload MoE host Vulkan, sin Windows), `Herbert-rs` (sin mantenimiento; estudiar KV INT8+VNNI), `OpenSet-LLM` (*agent-loop resume* en disco, atención fusionada CPU), `KTransformers` (prefix cache 3 niveles + MoE hot/cold), `FastLLM` (**KVMem** GPU+RAM), `ExLlamaV3` (KV 2–8b), `SGLang` (RadixAttention), `vLLM` (PagedAttention), y **`DFlash2`** (`z-lab/dflash`, ya integrado en `llama.cpp`).
4. **Descartados:** `llm.asm` (solo Linux AVX2, solo Qwen3-0.6B, ~7× más lento en prefill), `Candle` (cubierto por `mistral.rs`), `Megakernel Zoo` (solo H100/B200), `ExLlamaV2` (archivado), `openvino` core (se evalúa vía `openvino.genai`).
5. **Hallazgo emergente (F1b opcional):** `Strata` (`Niko1221/Strata`) y **`RustingStrata`** (`RustingStudio/RustingStrata`, Rust + **Vulkan** + CUDA + GGUF para MoE).
6. **Arquitectura Qwen3 confirmada** en HF `config.json`: `Qwen3-30B-A3B` tiene **48 capas** (no 24), 4 cabezas KV, 128 expertos (8 activos), `ctx=40960`.
7. **Aviso legal:** `h9-tec/LLM-Inference-Handbook` **no tiene licencia** (*All Rights Reserved*) — prohibido copiar contenido; solo referencia conceptual.

## Orden de lectura

1. [README.md](README.md): objetivo, preguntas, reglas, fases y niveles de adopción.
2. [01_inventario_candidatos.md](01_inventario_candidatos.md) y [01b_agregador_y_manual.md](01b_agregador_y_manual.md): fichas verificadas en F1.
3. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md): técnicas T1–T20 para F3.
4. [02_protocolo_benchmark.md](02_protocolo_benchmark.md): pruebas A–H y formato JSONL para F2/F4.
5. Código relevante de GuarIdA: `app/guarida_manager/engine/server.py`, `engine/client.py`, `app/guarida_manager/tuning/`, `downloader/binaries.py` (`b12017`), `hardware*.py`, `cache.py`.

## Siguientes tareas concretas

### Opción 1 · F2 (Línea base GuarIdA + quick-wins N0)
1. Crear `docs/estudio_inferencia/resultados/prompts/` con prompts fijos (A–G, español + código, sin datos personales).
2. Ejecutar las pruebas A–G contra el `llama-server b12017` actual de GuarIdA en el equipo local (registrar `hash_hardware`, perfil y JSONL en `resultados/`), midiendo:
   - Baseline actual de `tuning/` vs **N0 afinado** (`-fa`, `-ctk q8_0 -ctv q8_0`, `--cache-reuse`, `--slot-save-path`, `--lookup-cache` en G, `-md` con Qwen3-0.6B, y `-ot`/`--n-cpu-moe` en H si hay MoE).
   - Comparar también si `llama.cpp v1.0.0`+ aporta mejora directa (MTP/DFlash2, Vulkan) sobre `b12017`.

### Opción 2 · F3 (Estudio de técnicas — sin requerir hardware de benchmark)
Rellenar las fichas técnicas de [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md) priorizando las de mayor impacto en GuarIdA (agente de código, contexto 8–16k, APU/Vulkan):
1. **T6** (caché de prefijos, *cache-aware prompting* en el arnés de GuarIdA, `--slot-save-path`, *agent-loop resume* de OpenSet-LLM, RadixAttention).
2. **T7/T8/T9** (especulación: `-md` Qwen3-0.6B, **DFlash2**, MTP, `--lookup-cache` en edición de código).
3. **T4/T18/T19** (KV cuantizada + Hadamard KV, **KVMem** de FastLLM, XAttention/Tri-shape).
4. **T10** (reparto/caché de expertos MoE: `-ot`/`--n-cpu-moe`, `ik_llama.cpp`, `Strata`/`RustingStrata`, `Golem`).

### Opción 3 · F1b (rápida, ~10 min)
Verificar ficha completa (licencia, releases, Windows, Vulkan, API OpenAI) de `Niko1221/Strata` y `RustingStudio/RustingStrata` antes de cerrar la lista de F4.

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
| 2026-11-28 | Antigravity (Gemini) | F1 cerrada: push inicial, verificación paralela con guardado incremental de 20+ repos, agregador `awesome-local-inference-recipes` (1.328 filas), 12 proyectos sin enlace y 4 modelos recientes, `config.json` oficiales de Qwen3 (confirmado 48 capas en 30B-A3B), mapa legal del `Handbook`, actualización de inventario, protocolo, técnicas y traspaso | F2 (línea base + N0), F3 (fichas de técnicas clave T6/T8/T9/T10/T18) o mini-F1b (`Strata`/`RustingStrata`) |
