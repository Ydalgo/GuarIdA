# ADR 0005: Persistencia de Perfiles de Afinamiento Óptimo y Ecosistema de Herramientas Portables

## Estado
Aceptado

## Contexto
En un entorno de desarrollo agéntico local y desconectado (Búnker GuarIdA), dos factores resultan críticos para la viabilidad operativa a largo plazo:
1. **Memoria permanente de afinamiento:** Calibrar los parámetros de ejecución de un modelo (capas offloadeadas a GPU `n_gpu_layers`, tamaño de contexto `ctx_size`, tamaño de batch y tipo de cuantización de KV Cache) exige tiempo de prueba y consumo de cómputo. Si un modelo se archiva o se descarta (por ejemplo, porque resulta lento para interacción conversacional en tiempo real pero es viable para procesamiento en segundo plano o parches nocturnos), eliminar el archivo `.gguf` pesado no debe destruir la configuración óptima conseguida. Si el usuario vuelve a descargar el modelo o decide reutilizarlo, el sistema debe aplicar directamente los parámetros óptimos afinados sin requerir recalibración.
2. **Ecosistema de herramientas offline:** El agente no solo depende de modelos LLM y de `llama-server`. Para trabajar con seguridad y autonomía necesita herramientas clave del sistema:
   - **`git`:** Indispensable para la creación de *worktrees* aislados donde el rol Coder aplica parches sin comprometer el código fuente original.
   - **`ripgrep` (`rg`):** Motor de búsqueda textual en código a hipervelocidad necesario para que el agente localice funciones, símbolos y dependencias sin saturar la memoria de contexto ni degradar la velocidad.

## Decisiones Arquitectónicas

### 1. Entidad y Tabla `configuraciones_optimas` en SQLite
* **Decisión:** Crear una tabla dedicada indexada por `(modelo_id, hash_hardware)` para preservar:
  - `n_gpu_layers`, `ctx_size`, `batch_size`, `kv_cache_tipo`.
  - Rendimiento empírico medido (`tok_s_medido`, `gtt_pico_mb`).
  - Nota técnica / motivo de descarte (ej. *"Lento para chat interactivo (1.2 t/s), pero afinado para background batch"*).
  - Indicador de configuración recomendada activa.
* **Justificación:** Garantiza que el conocimiento empírico adquirido nunca se pierda aunque el archivo binario `.gguf` se borre del disco para liberar almacenamiento.

### 2. Promoción Automática de Benchmarks al Archivar
* **Decisión:** Al invocar `archivar_modelo_sin_archivo()`, el sistema consulta el historial de benchmarks del modelo y promueve automáticamente la mejor marca registrada a la tabla `configuraciones_optimas` antes de desvincular el archivo físico.
* **Justificación:** Cero pérdida de trabajo: el afinamiento queda blindado para reutilización futura.

### 3. Gestor de Herramientas Portables (`GestorHerramientasBunker`)
* **Decisión:** Implementar un gestor modular de herramientas y binarios que:
  - Detecta si las herramientas (`llama-server`, `git`, `ripgrep`) están instaladas en el sistema anfitrión.
  - Permite descargar versiones portables oficiales (ej. MinGit para Windows, binarios de ripgrep) durante la ventana única de conexión.
  - Almacena los ejecutables en `~/.guarida/bin/tools/` y los registra en SQLite.
* **Justificación:** Asegura que el búnker disponga de todo el instrumental de desarrollo necesario antes de cortar el acceso a Internet.
