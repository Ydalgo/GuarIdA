# ADR 0010: Optimizaciones Avanzadas de Inferencia, Subsistema de Proyectos y RAG de Repositorio Local

* **Estado:** Aceptado e Implementado
* **Fecha:** 2026-11-15
* **Contexto:** Transición Fase 2 -> Fase 3 (Optimizaciones de Motor, Indexación de Repositorio y Sesiones Persistentes)

---

## 1. Contexto y Motivación

Para permitir que el usuario mantenga conversaciones técnicas fundamentadas con su propio código y documentación ("experiencia NotebookLM local") sin conexión a Internet y sin depender de servicios en la nube:
1. Se requiere estructurar proyectos locales y workspaces de trabajo.
2. Es indispensable adjuntar documentos heterogéneos (`.py`, `.md`, `.txt`, `.json`, `.toml`) e indexar tanto árboles sintácticos de código (AST) como bloques semánticos de texto con solapamiento.
3. Se deben recuperar evidencias mediante búsqueda híbrida RRF con citas exactas de fuentes (`[Fuente: archivo:líneas]`).
4. Se requiere optimizar el motor `llama-server` para maximizar el throughput de lectura de prompt (`PP`), soportar ventanas de contexto extendidas sin degradación y aislar parámetros sensibles (`api_key` vía variables de entorno).

---

## 2. Decisiones Técnicas Adoptadas

### 2.1. Optimizaciones de Rendimiento y Contexto en `llama-server`
* **Flags de Aceleración y Contexto Extendido en `LlamaServerConfig`:**
  - `-tb / --threads-batch`: Asignación de hilos dedicados para la fase de procesamiento de prompt (`PP`).
  - `--ctx-shift`: Rotación de ventana de contexto sin descartar el estado ni forzar recomputación completa del KV cache.
  - `--cache-reuse N`: Reutilización de fragmentos comunes en KV cache entre turnos.
  - `--lookup-cache N`: Decodificación especulativa ngram ligera para código repetitivo sin requerir modelo borrador adicional.
  - `-md / --model-draft` y `--draft-max`: Soporte para decodificación especulativa asistida por un modelo ligero (ej. `Qwen2.5-0.5B`).
  - `--mlock` y `--no-mmap`: Control directo de asignación de memoria RAM para mitigar fallos de página en hardware modesto.
  - Inclusión de lista blanca en `FLAGS_PERMITIDOS_EXTRA_ARGS` para prevenir inyección de argumentos no autorizados.

### 2.2. Seguridad Operativa
* **Ocultación de API Key en Entorno:**
  - El token `api_key` generado criptográficamente (`secrets.token_urlsafe(32)`) se pasa a `llama-server` exclusivamente a través de las variables de entorno `LLAMA_ARG_API_KEY` y `LLAMA_API_KEY`, impidiendo su exposición en la tabla de procesos del sistema operativo.

### 2.3. Subsistema de Proyectos y Repositorio (`guarida_manager/proyectos.py`)
* **GestorProyectos:**
  - Creación, listado y eliminación de proyectos asociados a directorios locales.
  - Escaneo recursivo descartando carpetas de entorno/versión (`.git`, `venv`, `node_modules`, `__pycache__`).
  - **Indexación Dual:**
    - Código Python: Generación de árbol sintáctico `NodoAST` (`MODULO`, `CLASE`, `FUNCION`, `METODO`) vía `arbol_nodos.py`.
    - Documentación y configuración: Fragmentación semántica `ChunkDocumento` respetando cabeceras markdown (`#`) y solapamiento controlado.
  - **Búsqueda Híbrida RRF:** Fusión de similitud coseno vectorial con coincidencia léxica de identificadores técnicos y citas de fuentes verificables.

### 2.4. Persistencia Relacional en SQLite (`guarida_manager/cache.py`)
* Nuevas entidades relacionales inicializadas automáticamente con migraciones idempotentes:
  - `proyectos`: Catálogo de workspaces y repositorios analizados.
  - `documentos_proyecto`: Registro de rutas, hashes SHA-256, recuento de nodos y estado de indexación.
  - `sesiones_chat`: Sesiones de conversación vinculadas a proyectos y modelos.
  - `mensajes_chat`: Historial de turnos con métricas de tokens, latencia y fuentes AST/documentales JSON citadas.

---

## 3. Consecuencias y Verificación

* **Compatibilidad 100% Offline:** Todo el flujo opera localmente con cero peticiones a redes externas.
* **Trazabilidad:** Cada respuesta del modelo en modo proyecto expone las fuentes consultadas y su relevancia.
* **Persistencia:** Las sesiones de conversación se conservan en `guarida.db` y permiten reanudar turnos de chat.
* **Verificación:** 107 tests unitarios automatizados en verde (`tests/test_proyectos.py`, `tests/test_engine.py`, `tests/test_chat.py`, etc.).
