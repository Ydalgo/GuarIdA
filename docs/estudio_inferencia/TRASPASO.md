# Traspaso del estudio (léeme primero)

> Documento para que cualquier persona u otro modelo pueda continuar el estudio sin el historial de la conversación. **Actualízalo al terminar cada sesión de trabajo.**

## Estado actual

- **Fecha de la última actualización:** 2026-11-28
- **Rama:** `estudio/motores-inferencia` (sale de `main` en `b0a4ef7`). **No fusionar en `main`** hasta que exista el ADR de decisión (F5) aceptado por el responsable del proyecto.
- **Fase cerrada:** F0 · Encuadre (documentación de fases, inventario inicial, protocolo, catálogo de técnicas, ADR 0013 propuesto).
- **Siguiente fase:** F1 · Verificación de fuentes. F2 (línea base) y F3 (técnicas) pueden ir después en paralelo.
- **No se ha modificado código** de GuarIdA en esta rama todavía.

## Orden de lectura

1. [README.md](README.md): objetivo, preguntas, reglas, fases y niveles de adopción.
2. [01_inventario_candidatos.md](01_inventario_candidatos.md): qué hay que verificar y en qué orden.
3. [03_catalogo_tecnicas.md](03_catalogo_tecnicas.md): qué técnicas importan y cómo encajan.
4. [02_protocolo_benchmark.md](02_protocolo_benchmark.md): solo cuando toque medir (F2/F4).
5. Código relevante de GuarIdA: `app/guarida_manager/engine/server.py` (`LlamaServerConfig`, lista blanca de flags), `engine/client.py`, `app/guarida_manager/tuning/` (afinador por etapas), `hardware*.py`, `cache.py` (`configuraciones_optimas`).
6. ADR relacionados: 0006 (motor), 0007 (afinamiento), 0008 (GGUF/telemetría), 0010 (optimizaciones del motor).

## Siguiente tarea concreta (F1)

Rellenar la ficha de [01_inventario_candidatos.md](01_inventario_candidatos.md) para cada candidato, en este orden:

1. **Prioridad A:** llama.cpp (versión que distribuye GuarIdA), ik_llama.cpp, Ghost Infer, DynaLM, OpenVINO/OpenVINO GenAI, KTransformers, Herbert-rs, llm.asm.
2. **Prioridad B:** MLC LLM, Golem, mistral.rs, Candle, FastLLM, OpenSet-LLM.
3. **Prioridad C (G = sin enlace):** solo comprobar que existen; si no se encuentran, marcar `no encontrado` y no dedicarles más tiempo.

Para cada uno: leer LICENSE, README, releases e issues; anotar la fecha de consulta; mover sus cifras al registro de afirmaciones con la fuente exacta (URL del README/commit). Confirmar también la arquitectura de Qwen3 (capas, cabezas KV) en los `config.json` oficiales y corregir la tabla de KV de [02_protocolo_benchmark.md](02_protocolo_benchmark.md) si hiciera falta.

Al cerrar F1: actualizar la columna **Estado F1**, ajustar prioridades con lo aprendido, marcar F1 como cerrada en el README y en este documento, y hacer commit.

## Reglas que no hay que romper

- **No inventar cifras.** Lo no medido se queda en `null` o como "afirmación del autor".
- **No dar por buena la conversación previa con ChatGPT:** ya tenía al menos dos errores (capas de Qwen3-30B-A3B y arquitectura de DynaLM). Todo dato se confirma en la fuente primaria.
- **No mezclar formatos** de cuantización distintos en una misma tabla de velocidad.
- **Comparar siempre contra `llama-server` bien afinado**, no con valores por defecto.
- **Coste de integración y licencia cuentan tanto como la velocidad.** GuarIdA es GPL-3.0, offline, Windows + Linux.
- Los cambios de código derivados del estudio van en ramas propias a partir de esta (p. ej. `estudio/n0-flags-afinador`), con tests.

## Convención de commits en esta rama

`docs(estudio): …` para documentación; `bench(estudio): …` para resultados y scripts de medida; `feat(estudio): …` para prototipos. Mensajes en español.

## Bitácora

| Fecha | Quién | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-11-28 | Antigravity (Claude Opus) | F0: fases, reglas, inventario de 27 entradas, protocolo con pruebas A–H, catálogo de 17 técnicas, ADR 0013 propuesto. Detectadas erratas en la conversación previa | Empezar F1 por los candidatos de prioridad A |
