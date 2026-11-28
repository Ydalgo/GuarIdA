# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`, ya subida a `origin`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fases cerradas:**
  - **F0 · Encuadre** (documentación, reglas, protocolo, catálogo de técnicas, ADR 0013 propuesto).
  - **F1 + Mini-F1b · Verificación de fuentes** (fichas verificadas contra fuentes primarias, incluidos `Strata`, `RustingStrata` y `DFlash2`).
  - **F3 · Estudio de técnicas** (`T1–T20` mapeadas al código real de GuarIdA en `03_catalogo_tecnicas.md` y `03b_fichas_tecnicas_apoyo.md`).
  - **F2 · Línea base GuarIdA + N0** (88 mediciones reales sin errores sobre `i5-1135G7` + `Intel Iris Xe` Vulkan con `qwen2.5-3b-instruct-q4_k_m.gguf` y `llama-server b12017` en `04_resultados_f2_linea_base.md`).
- **Siguientes fases:** **F4 · Laboratorio de motores** → **F5 · Decisión (ADR 0014)** → **F6 · Prototipo** (o bien una rama derivada `estudio/n0-quickwins` si se desea aplicar ya en GuarIdA lo validado en F2).
- **No se ha modificado código de producción** de GuarIdA en esta rama (solo se añadió `herramientas/bench_estudio_f2.py`).

## Conclusión ejecutiva de F2 (cifras medidas reales)

1. **`T6 + T17` (`N0-1`, prefijo estable + `id_slot=0` + `cache_prompt=True`):**
   - En agente multiturno, evitar la mutación de `prompt_sistema` reduce el TTFT del turno 3 de **37,71 s (`N0-Base`) a 0,72 s (>52× más rápido)** y mantiene `5.396–5.629` tokens en caché durante los 5 turnos (`702–1.086 ms` TTFT).
2. **`T9` (`N0-3`, `--spec-type ngram-mod`):**
   - En edición de código (`G`), dispara la generación de `11,36 t/s` (`N0-Base`) / `5,48 t/s` (`N0-2`) a **`46,33 t/s` (4,1× sobre baseline)** con **paridad greedy exacta** (hash `db033baab52666e3`), y acelera los turnos 1–3 de `F_estable` a `18,4–23,0 t/s`.
3. **`T5 + T4` (`N0-2`, `-fa on -ctk q8_0 -ctv q8_0`) en Intel Iris Xe Vulkan:**
   - Ahorra **~600–1.000 MB RAM/GTT** (`2,45–2,80 GB` frente a `2,80–3,66 GB`), pero **penaliza el decode ~33 %** (`8,34` vs `12,44 t/s` en `B`). Debe usarse como perfil de ahorro de memoria cuando la GTT vaya justa, no por defecto en Iris Xe con holgura.
4. **`N0-4` (`--slot-save-path`):** `save=412–439 ms`, `restore=48,6–56,3 ms` (`100,86 MiB`), TTFT tras restaurar `1.002–1.066 ms` con `5.396` tokens recuperados.
5. **Vulkan vs CPU en Iris Xe:** `N0-Base` Vulkan supera claramente a `N0-CPU` (`12,44` vs `7,71 t/s` en `B`; `11,36` vs `6,36 t/s` en `G`).
6. **Hallazgo crítico para código:** `llama-server b12017` **ya eliminó** `--no-mmap`, `--mlock`, `--draft-max` y `--draft-min` (sustituidos por `-lm`, `--spec-draft-n-max` y `--spec-type`) y depreca `--no-webui` (`--no-ui`).

## Orden de lectura

1. [04_resultados_f2_linea_base.md](04_resultados_f2_linea_base.md): resultados medidos de F2 y conclusiones empíricas.
2. [01_inventario_candidatos.md](01_inventario_candidatos.md) y [02_protocolo_benchmark.md](02_protocolo_benchmark.md): candidatos y protocolo para **F4 (fase actual)**.
3. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md) y [03b_fichas_tecnicas_apoyo.md](03b_fichas_tecnicas_apoyo.md): fichas técnicas `T1–T20`.
4. [bench_estudio_f2.py](../../herramientas/bench_estudio_f2.py): runner reproducible y reanudable (`--reanudar`, `--resumen`).

## Siguiente tarea concreta: F4 · Laboratorio de motores (o rama N0)

### Opción A · F4 (Comparativa de motores en Perfil B Intel / otros perfiles)
1. Descargar un modelo de la familia de referencia (`Qwen3-4B Q4_K_M` GGUF) y, si se prueba `N0-Up`, `llama.cpp v1.0.0+`.
2. Comparar en este equipo (`Perfil B · Intel Iris Xe / CPU`) los candidatos verificados en F1 para este hardware frente al ganador N0 de `llama-server`:
   - **`OpenVINO GenAI` (+ OVMS):** GGUF directo vs IR INT4 en Intel CPU + iGPU (`--opt_out` en telemetría).
   - **`mistral.rs`:** binario oficial Windows CPU (`Q4_K_M`, prefix caching).
   - **`DynaLM`:** binario Windows CPU/Vulkan exploratorio (`--prompt-cache`).
   - *(Solo en GPU AMD/NVIDIA si hay equipo Perfil C/D disponible: `RustingStrata`, `Strata`, `ik_llama.cpp`, `MLC LLM`).*
3. Guardar los resultados en `resultados/AAAA-MM-DD_<hash_hw>_<motor>.jsonl` con el mismo esquema y puerta de calidad `Q`.

### Opción B · Rama derivada `estudio/n0-quickwins` (aplicar ya lo demostrado en F2)
Si se decide llevar ya a GuarIdA las mejoras N0 probadas en F2 (en una rama nueva desde `estudio/motores-inferencia` o `main`, con tests):
1. Estabilizar `prompt_sistema` (quitar `{len(docs_idx)}`) y mover `ctx_memoria` a bloque fijo tras el sistema en `chat.py` y `web/server.py`, y quitar las 2 llamadas previas a `/tokenize`.
2. Añadir `id_slot`, `cache_prompt` y `guardar_slot`/`restaurar_slot` en `engine/client.py`.
3. Actualizar `LlamaServerConfig` en `engine/server.py` para `b12017`+ (`-lm`, `--spec-type ngram-mod`, `--spec-draft-n-max`, `--slot-save-path`, `-cmoe`, `--moe-cache-mib`).

## Reglas que no hay que romper

- **No inventar cifras.** Lo no medido se queda en `null` o como "afirmación del autor".
- **No mezclar formatos** de cuantización distintos en una misma tabla de velocidad.
- **Comparar siempre contra `llama-server` bien afinado** (el combo ganador N0 de F2, no valores por defecto).
- **Medir calidad y tiempo total** (puerta `Q` + paridad greedy + *Token Inflation Trap*).
- **No copiar contenido de `h9-tec/LLM-Inference-Handbook`** (sin licencia).

## Convención de commits en esta rama

`docs(estudio): …` para documentación; `bench(estudio): …` para resultados y scripts de medida; `feat(estudio): …` para prototipos. Mensajes en español.

## Bitácora

| Fecha | Quién | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-11-28 | Antigravity (Claude Opus) | F0: fases, reglas, inventario inicial, protocolo A–H, catálogo de técnicas, ADR 0013 propuesto (`0dc95b8`) | Completar F1 |
| 2026-11-28 | Antigravity (Gemini) | F1 cerrada: verificación primaria de 20+ repos, agregador, 12 proyectos sin enlace, `config.json` de Qwen3 (`927c629`) | Mini-F1b |
| 2026-11-28 | Antigravity (Gemini) | Mini-F1b cerrada y reordenación a **F3 → F2** (`4b8a872`): verificados `Strata`, `RustingStrata` y `DFlash2` | Empezar **F3** |
| 2026-11-28 | Antigravity (Gemini) | F3 cerrada (`9257cb0`): estudio técnico `T1–T20` mapeado al código de GuarIdA + plan N0 | Empezar **F2** |
| 2026-11-28 | Antigravity (Gemini) | F2 cerrada: prompts A–G/Q, runner `bench_estudio_f2.py`, 88 mediciones reales en Perfil B (`i5-1135G7` + `Iris Xe` Vulkan) con `b12017` y `qwen2.5-3b-instruct-q4_k_m.gguf`, informe `04_resultados_f2_linea_base.md` | **F4** (laboratorio de motores) o rama `estudio/n0-quickwins` |
