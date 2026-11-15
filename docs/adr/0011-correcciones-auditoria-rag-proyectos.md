# ADR 0011: Correcciones de Auditoría del RAG de Proyectos (Fase 3)

* **Estado:** Aceptado e Implementado
* **Fecha:** 2026-11-15
* **Contexto:** Corrige defectos detectados al auditar el commit `c2217a9` (ADR 0010).

---

## 1. Defectos detectados y corrección

| # | Defecto | Corrección |
|---|---------|-----------|
| 1 | El chat llamaba a `cli.obtener_embeddings` (inexistente); el `except` lo ocultaba y el RAG nunca aportaba contexto | Se usa `ClienteLlamaOffline.calcular_embedding`. Los fallos ya no se silencian: se avisan por pantalla y log |
| 2 | Embeddings pedidos al servidor generativo | `chat.iniciar_servidor_embeddings`: `llama-server --embedding` en puerto libre, CPU cooperativa, `api_key` aleatoria, parada garantizada en `finally`. Si no es posible, aviso explícito y ranking solo léxico |
| 3 | Sin punto de entrada | Opción `[7] Proyectos y Documentos` (`menu_proyectos.py`): crear, listar, chatear, reanudar sesión, eliminar. La antigua opción `7` (alias del afinador) se elimina; el afinador sigue en `[3]` |
| 4 | Índice solo en memoria | Tabla `embeddings_cache` (BLOB `float32`, clave = SHA-256 de `modelo + texto`). La reindexación solo vectoriza lo nuevo o modificado; cambiar de modelo de embeddings no reutiliza vectores ajenos. El resumen informa de archivos sin cambios y embeddings nuevos/reutilizados |
| 5 | Flags de optimización sin uso | `LlamaServerConfig.aplicar_optimizaciones_seguras()` se aplica en `desde_afinamiento`: activa `--cache-reuse 256` y `-tb` **solo si** `llama-server --help` los anuncia. `-md`, `--lookup-cache` y `--ctx-shift` siguen siendo opt-in (ver pendientes) |
| 6 | Escaneo sin límites de seguridad | Se omiten secretos (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `credentials*`, `*.db`, `*.gguf`, …), enlaces simbólicos, rutas fuera del proyecto y archivos > 1 MB. El resumen cuenta los omitidos |
| 7 | Checksums de binarios inventados | Sustituidos por los `digest` oficiales de la API de GitHub para la release `b12017`. El perfil `win-avx2` no existe en esa release (404): ahora usa `win-cpu-x64`. macOS usa `.tar.gz` |
| 8a | Chunks por líneas | Fragmentación por presupuesto de tokens (`max_tokens_chunk`, ~256) respetando encabezados Markdown |
| 8b | Solo Python con estructura | Código no Python (`.js .ts .go .rs .java .c .cpp ...`) se fragmenta por definiciones (`function/class/fn/func/struct/...`) |
| 8c | "RRF" era una suma de puntuaciones | RRF real: rango denso (coseno) + rango léxico (identificadores AST/palabras), `1/(60+rango)`, sobre nodos AST y fragmentos en una única lista. Sin embeddings degrada a ranking léxico |
| extra | Contexto RAG acumulado en el historial | El contexto recuperado solo se envía en el turno actual; el historial guarda el mensaje limpio, de modo que no infla la ventana en turnos sucesivos |
| extra | `chat.estimar_tok_s_modelo` llamaba a `ComparadorModelosHardware.evaluar_modelo` (inexistente) | Corregido a `evaluar_modelo_completo`. Fallaba con cualquier modelo sin benchmark previo |

## 2. Verificación

- Pruebas nuevas en `tests/test_proyectos.py` (seguridad, incrementalidad, RRF léxico, chunking, código genérico, integración chat↔RAG con comprobación de que el contexto llega al prompt y no se acumula, menú) y `tests/test_engine.py` (flags condicionados, checksums reales sin duplicados).
- Los checksums se obtuvieron consultando la API de GitHub el 2026-11-15; los de `win-vulkan` y `win-cpu` coincidían con los que ya había en el código.

## 3. Pendiente / limitaciones conocidas

- **Sin medición empírica** de `--cache-reuse`, `-tb`, `--lookup-cache`, `-md` ni `--ctx-shift`. Solo se activan los dos primeros, por ser de bajo riesgo. Falta una etapa de A/B con `llama-bench` en el afinador antes de activar el resto por defecto.
- **Sin prueba end-to-end con `llama-server` real** en CI: las pruebas de chat usan dobles de prueba. El flujo contra un binario y un modelo de embeddings reales debe validarse manualmente.
- El ranking léxico usa coincidencia de identificadores, no BM25 con IDF.
- Los vectores se comparan por fuerza bruta en memoria (suficiente para repos pequeños/medianos).
- Los usuarios que ya habían descargado `llama-b12017-bin-win-avx2-x64.zip` deberían volver a aprovisionar: ese archivo no existe en la release oficial.
