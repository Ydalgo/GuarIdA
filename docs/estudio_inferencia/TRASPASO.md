# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`, ya subida a `origin`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fases cerradas:**
  - **F0 · Encuadre** (documentación, reglas, protocolo, catálogo de técnicas, ADR 0013 propuesto).
  - **F1 + Mini-F1b · Verificación de fuentes** (todas las fichas verificadas contra fuentes primarias, incluidos `Strata`, `RustingStrata` y `DFlash2`).
  - **F3 · Estudio de técnicas** (todas las fichas `T1–T20` completadas, clasificadas y mapeadas al código real de GuarIdA en `03_catalogo_tecnicas.md` y `03b_fichas_tecnicas_apoyo.md`).
- **Siguiente fase:** **F2 · Línea base GuarIdA + experimentos N0** → después **F4 (Laboratorio)** → **F5 (ADR 0014)** → **F6 (Prototipo)**.
- **No se ha modificado código** de GuarIdA en esta rama todavía.

## Conclusión ejecutiva de F3 (para no releer todo)

1. **Alto retorno inmediato sin cambiar de motor (N0/N1):**
   - **T6 + T17 (*cache-aware prompting* y arnés):** `chat.py` y `web/server.py` ya dejan fuera del historial los fragmentos RAG anteriores, pero `web/server.py:991` incrusta `{len(docs_idx)} archivos indexados` en `prompt_sistema` (invalida la caché KV al reindexar), `ctx_memoria` se concatena al final del último turno en lugar de ir como prefijo estable, cada turno hace **2 llamadas HTTP síncronas previas a `/tokenize`**, y `engine/client.py` aún no expone `id_slot`, `cache_prompt` en chat ni `/slots/{id}?action=save|restore`.
   - **T5 + T4 + T1 (atención y memoria):** `engine/server.py:285-287` desactiva a la fuerza `-fa` en cualquier GPU no-NVIDIA (vetando Vulkan/CPU) y solo permite KV simétrica; además conviene estandarizar `-lm none`/`--no-mmap` en rutas GTT Windows fuera del tuner.
   - **T9 (*prompt lookup*):** `--lookup-cache` (o `--spec-type ngram-mod` en `v1.0.0`+) tiene coste 0 de VRAM y ataca directamente la edición de código (prueba **G**).
   - **T10 (MoE):** exponer `-cmoe`, `--moe-cache-mib` y `--moe-cache-cpu-share` junto a `--n-cpu-moe` y `-ot` en `engine/server.py` / `tuning/`.
   - **T13 + T20 (calidad):** añadir puerta obligatoria de sanidad/calidad previa al scoring y auditar *Token Inflation Trap* (`tiempo_total_hasta_acierto` y longitud `<think>`) antes de recomendar cuantizaciones `< Q4`.
2. **Técnicas diferidas o solo estudio:**
   - **T8 (`DFlash2` / `EAGLE-3` / `MTP`):** `solo estudiar` hasta evaluar la actualización de `llama-server` de `b12017` a `v1.0.0+`; además presenta regresiones documentadas en hardware limitado por ancho de banda y en chat/razonamiento largo.
   - **T18 (`KVMem`) y T19 (`Tri-shape`/`XAttention`/eviction):** `solo estudiar` (complejidad alta o riesgo en código; RAG AST + KV `q8_0` cubren 8–32K).
   - **T14 (`PagedAttention`), T11 (desagregación prefill/decode), T12 (compilación grafo):** `solo estudiar` (T15 `continuous batching` queda `integrar` de forma condicional: `-np 1` en local y `-np 2..4` en modo LAN).
   - **T3 (formatos propietarios `PTQ1_0`, `H3G`, `q4f16`, `IQ_KT`):** `descartar` mientras `llama-server` sea la base (mantener catálogo GGUF curado).

## Orden de lectura

1. [README.md](README.md): objetivo, preguntas, reglas, fases y niveles de adopción.
2. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md): tabla `T1–T20`, fichas principales, **Plan de experimentos N0 listo para F2** y boceto `MotorInferencia`.
3. [03b_fichas_tecnicas_apoyo.md](03b_fichas_tecnicas_apoyo.md): fichas de apoyo (`T1`, `T2`, `T3`, `T5`, `T11–T15`, `T17`).
4. [02_protocolo_benchmark.md](02_protocolo_benchmark.md): pruebas A–H y formato JSONL para **F2 (fase actual)** y **F4**.
5. [01_inventario_candidatos.md](01_inventario_candidatos.md) y [01b_agregador_y_manual.md](01b_agregador_y_manual.md): fichas verificadas para F4.

## Siguiente tarea concreta: F2 · Línea base GuarIdA + experimentos N0

Seguir el **Plan de experimentos N0** de [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md#plan-de-experimentos-n0-listo-para-f2):
1. Crear `docs/estudio_inferencia/resultados/prompts/` con prompts deterministas fijos (A–G, español + código Python, sin datos personales).
2. Ejecutar un script reproducible de medición (usando el formato JSONL de [02_protocolo_benchmark.md](02_protocolo_benchmark.md)) sobre el hardware local actual contra `llama-server b12017`:
   - **`N0-Base`:** perfil actual de `tuning/` (`-fa off` en no-NVIDIA, KV `f16`, sin `id_slot`).
   - **`N0-1` (`T6+T17`):** prefijo estable (`prompt_sistema` sin conteo de archivos + `ctx_memoria` en bloque fijo) + `id_slot=0` + `cache_prompt=True`.
   - **`N0-2` (`T5+T4+T1`):** `N0-1` + `-fa` en Vulkan/CPU + KV `q8_0` (y asimétrica si aplica) + `-lm none` / `--no-mmap` en GTT Windows.
   - **`N0-3` (`T9`):** `N0-2` + `--lookup-cache` (medir **G** edición y **C** prosa).
   - **`N0-4` (`T6`):** `N0-2` + `--slot-save-path` (`save`/`restore`).
   - **`N0-Up`:** comparar `b12017` frente a `llama.cpp v1.0.0+` (flags nuevas: `-fa auto`, `--spec-type ngram-mod`, `-lm none`, `--spec-draft-n-max`, y DFlash2 si aplica).
3. Si algún experimento N0 requiere un cambio pequeño de código (p. ej. `engine/client.py` / `server.py`), implementarlo en rama derivada (p. ej. `estudio/n0-flags-afinador`) o prototipo aislado con tests verdes antes de consolidar en F6.

## Reglas que no hay que romper

- **No inventar cifras.** Lo no medido se queda en `null` o como "afirmación del autor".
- **No mezclar formatos** de cuantización distintos en una misma tabla de velocidad.
- **Comparar siempre contra `llama-server` bien afinado**, no con valores por defecto.
- **Medir calidad y tiempo total** (cuidado con la *Token Inflation Trap* en modelos de razonamiento cuantizados).
- **No copiar contenido de `h9-tec/LLM-Inference-Handbook`** (sin licencia).
- Los cambios de código derivados del estudio van en ramas propias a partir de esta, con tests.

## Convención de commits en esta rama

`docs(estudio): …` para documentación; `bench(estudio): …` para resultados y scripts de medida; `feat(estudio): …` para prototipos. Mensajes en español.

## Bitácora

| Fecha | Quién | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-11-28 | Antigravity (Claude Opus) | F0: fases, reglas, inventario inicial, protocolo A–H, catálogo de técnicas, ADR 0013 propuesto. Creada rama `estudio/motores-inferencia` (`0dc95b8`). Descargadas fuentes primarias y `config.json` de Qwen3 | Completar F1 |
| 2026-11-28 | Antigravity (Gemini) | F1 cerrada: push inicial, verificación paralela de 20+ repos, agregador, 12 proyectos sin enlace y 4 modelos recientes, `config.json` oficiales de Qwen3 (`927c629`) | Mini-F1b (`Strata`, `RustingStrata`, `DFlash2`) |
| 2026-11-28 | Antigravity (Gemini) | Mini-F1b cerrada y reordenación a **F3 → F2** (`4b8a872`): verificados `Strata`, `RustingStrata` y `DFlash2` | Empezar **F3** |
| 2026-11-28 | Antigravity (Gemini) | F3 cerrada: estudio paralelo de `T1–T20` mapeado a `engine/`, `chat.py`, `web/server.py`, `proyectos.py` y `tuning/`; fichas en `03_catalogo_tecnicas.md` y `03b_fichas_tecnicas_apoyo.md`; plan de experimentos N0 para F2 y boceto `MotorInferencia` | Empezar **F2** (prompts A–G y experimentos `N0-Base`..`N0-Up`) |
