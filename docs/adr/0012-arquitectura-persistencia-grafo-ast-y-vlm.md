# ADR 0012: Arquitectura de Persistencia Segregada, Grafo AST y Pipeline Multimodal/VLM

* **Estado:** Aceptado e Implementado
* **Fecha:** 2026-11-16
* **Contexto:** Evolución de la memoria del agente, rendimiento en I/O, gobernanza de privacidad (RGPD) e ingesta multimodal inspirada en patrones de memoria persistente inmutable (CortexDB) adaptados a GuarIdA.

---

## 1. Decisiones Arquitectónicas

### 1.1 Segregación de Almacenes de Datos
Para eliminar contenciones de bloqueo (database locks) y optimizar el rendimiento de I/O según el patrón de acceso:

1. **`config.db` (SQLite):** Configuración general, inventario de hardware y rutas locales. Acceso de solo lectura predominante, transacciones infrecuentes.
2. **`telemetria_logs/` (JSONL rotativo por fecha + compresión zstd):** Ingesta append-only de métricas y eventos en tiempo real sin contención de cerrojos SQLite.
3. **`sesiones_chat.db` (SQLite en modo WAL + tablas normalizadas):**
   - Historial de conversación separado del contenido extenso.
   - Tabla inmutable de eventos de memoria y hechos clave (`hechos_proyecto`) con soporte para estado `activo` y `superseded` (auditoría histórica sin sobreescritura destructiva).
4. **`proyecto_grafo.db` (SQLite por proyecto):**
   - Topología de código y grafo AST (`nodos` y `relaciones`).
   - Caché de vectores (`embeddings_cache`).
   - Consultas relacionales y transitivas mediante `WITH RECURSIVE`.

### 1.2 Grafo de Conocimiento AST y Recuperación Multihop
- Extensión del `ArbolNodosCodigo` para registrar relaciones explícitas: `IMPORTA`, `HEREDA_DE`, `LLAMA_A`.
- Búsqueda híbrida RAG (BM25Okapi + Coseno matricial) combinada con expansión en grafo: una vez localizados los nodos semilla, se expanden sus dependencias inmediatas para asegurar contexto completo.

### 1.3 Gobernanza de Privacidad y Anonimización
- **Delimitadores `<private>...</private>`:** Sanitización en ingesta de código y prompts para excluir bloques confidenciales del índice vectorial y memoria persistente.
- **Modos de Operación Configurable:**
  - *Modo Estándar (Local-First):* Procesamiento local sin telemetría externa. Filtros de seguridad pasiva (.env, claves API, etc.).
  - *Modo RGPD Estricto (Anonimización Irreversible / K-Anonymity):* Redacción determinista no rehidratable (`[EMAIL_REDACTADO]`, `[ID_USUARIO_A]`) con log criptográfico de auditoría (HMAC) para trazabilidad legal sin retención de datos personales.

### 1.4 Ingesta Multimodal (VLM Local en GGUF)
- Sustitución de OCR plano (Tesseract) por integración de modelos Vision-Language locales (ej. `Qwen2-VL-2B-Instruct` en GGUF con proyector `mmproj`) sobre el motor `llama.cpp` existente.
- Enrutamiento automático de archivos visuales (`.png`, `.jpg`, esquemas, diagramas) a transcripción canónica estructurada (Markdown/JSON) antes de indexar en el grafo AST.

### 1.5 Interoperabilidad vía Servidor MCP
- Servidor MCP local sobre `stdio` opcional para exponer herramientas de memoria, grafo AST y consulta híbrida hacia IDEs y agentes externos (ej. Antigravity).

---

## 2. Hoja de Ruta de Implementación (Fases)

| Fase | Tarea | Componentes Afectados |
|---|---|---|
| **Fase 1** | ~~Segregación de bases de datos y rotación de telemetría JSONL~~ *(Completada)* | `cache.py`, `telemetry.py` |
| **Fase 2** | ~~Memoria declarativa inmutable (`superseded`) en chat~~ *(Completada)* | `cache.py`, `proyectos.py`, `chat.py` |
| **Fase 3** | ~~Tabla relacional de grafo AST con consultas recursivas SQLite~~ *(Completada)* | `arbol_nodos.py`, `cache.py`, `proyectos.py` |
| **Fase 4** | ~~Sanitizer de privacidad (`<private>`) y toggle de modo RGPD~~ *(Completada)* | `security/sanitizer.py`, `proyectos.py`, `chat.py` |
| **Fase 5** | ~~Router de ingesta visual con VLM (`llama.cpp` + `mmproj`)~~ *(Completada)* | `downloader/models.py`, `proyectos.py` |
| **Fase 6** | ~~Endpoint Servidor MCP local (stdio)~~ *(Completada)* | `guarida_manager/mcp/` |

---

## 3. Verificación y Uso Operativo

- **Comandos de Chat Interactivos (`guarida_manager/chat.py`):**
  - `/remember <sujeto> | <predicado> | <objeto>`: registra hechos declarativos inmutables marcando versiones anteriores contradictorias como `superseded`.
  - `/recall [all]`: consulta hechos activos o auditoría histórica completa con enlaces `sustituido_por_id` y `sha_origen`.
  - `/rgpd [on|off|status]`: conmuta entre modo `estandar` (`<private>` y secretos explícitos) y modo `rgpd_estricto` (redacción irreversible de PII con log criptográfico HMAC-SHA256).
- **Servidor MCP Local sobre `stdio` (`guarida_manager/mcp/server.py`):**
  - Arranque directo: `python -m guarida_manager.mcp.server`.
  - Herramientas expuestas: `guarida_listar_proyectos`, `guarida_buscar_contexto`, `guarida_expandir_grafo_ast`, `guarida_registrar_hecho`, `guarida_consultar_memoria`, `guarida_sanitizar_texto`.
- **Cobertura de Pruebas:**
  - `tests/test_cache.py`: segregación SQLite, mensajes compactos zstd/zlib, telemetría JSONL+Zstd y memoria inmutable `superseded`.
  - `tests/test_chat.py`: comandos `/remember`, `/recall`, extracción automática e inyección en turno de chat.
  - `tests/test_proyectos.py`: grafo AST recursivo `WITH RECURSIVE`, sanitizer `<private>`/RGPD con auditoría HMAC, ingesta visual VLM (`qwen2-vl-2b-instruct-q4` + `mmproj` y fallback binario PNG) y servidor MCP `stdio`.
