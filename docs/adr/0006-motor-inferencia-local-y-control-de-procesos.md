# ADR 0006: Motor de Inferencia Local y Control de Procesos (Fase 2)

## Estado
Aceptado

## Contexto
En la Fase 1 se consolidaron la detección de hardware (CPU, núcleos, RAM y memoria VRAM/GTT compartida), las pruebas empíricas de estrés de memoria, el gestor de caché SQLite, el aprovisionamiento de herramientas portables (`llama-server`, `git`, `ripgrep`) y la persistencia de configuraciones óptimas afinadas por hardware.

Para dar inicio a la Fase 2, se requiere desacoplar el ciclo de vida del proceso de inferencia del resto de la aplicación y disponer de un cliente de comunicación HTTP 100% offline que opere sin dependencias externas adicionales (utilizando la biblioteca estándar de Python), garantizando el funcionamiento en entornos bunkerizados y sin acceso a redes externas.

## Decisión
1. **Gestor del Servidor (`guarida_manager/engine/server.py`):**
   - Implementar `LlamaServerConfig` para estructurar y validar todos los parámetros de línea de comandos de `llama-server` (`-m`, `--host`, `--port`, `-ngl`, `-c`, `-b`, `-t`, `--cache-type-k`, `--no-webui`, etc.).
   - Implementar `LlamaServerConfig.desde_afinamiento` para enlazar automáticamente el arranque del modelo con la mejor configuración empírica registrada en la tabla `configuraciones_optimas` de SQLite para el `hash_hardware` del equipo actual.
   - Implementar `GestorLlamaServer` para supervisar el subproceso con creación sin ventana en Windows (`CREATE_NO_WINDOW`), monitorización de estado/uptime y parada controlada (`terminate` con fallback a `kill`).

2. **Cliente Offline de Inferencia (`guarida_manager/engine/client.py`):**
   - Construir `ClienteLlamaOffline` basado exclusivamente en `urllib.request` y `json` nativo de Python 3.
   - Proveer soporte directo para los endpoints clave de `llama-server`:
     - `/health`: Verificación no invasiva de salud y carga de modelo.
     - `/slots`: Monitorización de ocupación de ranuras de contexto y concurrencia.
     - `/v1/chat/completions`: Formato compatible con OpenAPI/OpenAI para roles conversacionales y de código.
     - `/completion`: Inferencia de texto plano nativa de llama.cpp.
     - `/tokenize` y `/detokenize`: Inspección y conteo exacto de tokens previo a la inferencia para control del presupuesto de contexto.
     - `/embedding`: Vectorización para búsquedas semánticas y árboles de nodos AST.

## Consecuencias
- **Positivas:**
  - El motor de inferencia corre aislado como un servicio local autocontenido en `127.0.0.1:8083`.
  - Cero dependencias añadidas a `pip` (solo Python estándar).
  - Los modelos arrancan de forma instantánea con el afinamiento óptimo específico del hardware.
  - El sistema de agentes (Fase 3) podrá interactuar con una interfaz limpia, tipada y con gestión robusta de errores offline.
