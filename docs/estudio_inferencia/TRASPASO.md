# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`, ya subida a `origin`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fases cerradas:**
  - **F0 · Encuadre** (`0dc95b8`).
  - **F1 + Mini-F1b · Verificación de fuentes** (`927c629`, `4b8a872`).
  - **F3 · Estudio de técnicas `T1–T20`** (`9257cb0`).
  - **F2 · Línea base GuarIdA + N0** (`0c4a5f2`).
  - **F4 · Laboratorio multimotor en Perfil B** (`Qwen3-4B-Q4_K_M.gguf` en `i5-1135G7` + `Intel Iris Xe`, 8 perfiles medidos en `05_resultados_f4_laboratorio.md`).
- **Siguiente fase:** **F5 · Síntesis y decisión (ADR 0014)** → **F6 · Implementación**.
- **No se ha modificado código de producción** de GuarIdA en esta rama (solo runners de estudio en `herramientas/`).

## Conclusión ejecutiva de F4 (cifras medidas reales en `Qwen3-4B Q4_K_M`)

1. **`llama.cpp b12823` (`v1.1.0-dev` Vulkan) gana en toda la línea:**
   - `B`: **`12,96 t/s`** (TTFT `7,49 s`) vs `8,57 t/s` (`b12017`), `8,68` (`DynaLM Vulkan`), `7,04` (`OpenVINO GPU`), `6,40` (`mistral.rs CPU`), `5,78` (`llama CPU`).
   - `C`: **`14,42 t/s`** (casi **2×** sobre `b12017` `7,41 t/s`, y >2,2× sobre `DynaLM Vulkan` `6,20` y `OpenVINO GPU` `6,50`).
   - `G` (edición de código con `--spec-type ngram-mod`): **`42,16 t/s`** (`b12823`) / **`40,19 t/s`** (`b12017`) frente a `5,58` (`DynaLM Vulkan`) y `5,42` (`OpenVINO GPU`).
   - `Q` (`Q_json` y `Q_python`): `ok` en `llama b12823`, `b12017`, `DynaLM Vulkan` y `OpenVINO GPU`.
2. **Los motores alternativos en Perfil B Intel no compensan:**
   - `DynaLM CPU` (`1,60 t/s`, TTFT `144,5 s` en `C`), `mistral.rs CPU` (TTFT `58,0 s` en `B`, `8,90 GB` RAM) y `OpenVINO GenAI` en GGUF directo (`24,5–30,5 s` arranque, `8,4–9,6 GB` RAM, `3,5–6,5 t/s` en `C`) quedan claramente por detrás de `llama-server`.
3. **Veredicto hacia F5:** mantener **`llama-server` como motor único por defecto**, actualizarlo de `b12017` a `b12823`+ (`v1.1.0-dev`), aplicar las mejoras **N0/N1** validadas en F2 (`T6+T17` prefijo estable + `id_slot`/`cache_prompt` + quitar 2 `/tokenize`, `T9` `ngram-mod`, `T1` `-lm none`, `T5/T4` según holgura GTT, `T13+T20` calidad) y dejar `MotorInferencia` (`T16`) desacoplado de forma ligera.

## Orden de lectura

1. [05_resultados_f4_laboratorio.md](05_resultados_f4_laboratorio.md): resultados de F4.
2. [04_resultados_f2_linea_base.md](04_resultados_f2_linea_base.md): resultados N0 de F2.
3. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md): técnicas `T1–T20` y diseño `MotorInferencia`.
4. [01_inventario_candidatos.md](01_inventario_candidatos.md): fichas primarias de todos los motores.

## Siguiente tarea concreta: F5 · Síntesis y decisión (ADR 0014)

1. Redactar `docs/adr/0014-optimizacion-motor-inferencia-n0-n1.md` con la decisión final basada en F1–F4 (matriz ponderada + plan de cambios concretos en `downloader/binaries.py`, `engine/server.py`, `engine/client.py`, `chat.py`, `web/server.py`, `proyectos.py` y `tuning/`).
2. Presentar el ADR al responsable del proyecto para aprobación antes de pasar a **F6** (implementación con tests y fusión ordenada).

## Bitácora

| Fecha | Quién | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-11-28 | Antigravity (Claude Opus) | F0 (`0dc95b8`) | F1 |
| 2026-11-28 | Antigravity (Gemini) | F1 (`927c629`) + Mini-F1b (`4b8a872`) + F3 (`9257cb0`) + F2 (`0c4a5f2`) | F4 |
| 2026-11-28 | Antigravity (Gemini) | F4 cerrada: runner `bench_estudio_f4.py`, comparativa de 8 perfiles sobre `Qwen3-4B-Q4_K_M.gguf` en Perfil B Intel (`llama b12017`, `b12823`, `DynaLM v0.6.0`, `mistral.rs v0.9.5`, `OpenVINO GenAI 2026.4.1`), informe `05_resultados_f4_laboratorio.md` | **F5 (ADR 0014)** |
