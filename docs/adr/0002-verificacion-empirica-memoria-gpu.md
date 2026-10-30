# ADR 0002: Verificación Empírica y Prueba de Estrés de Memoria GPU/GTT

## Estado
Aceptado

## Contexto
En la inferencia local sobre hardware de consumo (especialmente APUs AMD Ryzen y gráficas integradas Intel Iris Xe), la memoria de vídeo (VRAM) se nutre dinámicamente de la memoria RAM del sistema mediante WDDM en Windows y DRM/GTT en Linux.

Los drivers y el sistema operativo reportan valores teóricos de memoria (por ejemplo, pools compartidos del 50 % de la RAM). Sin embargo, **no se puede dar por hecho la compatibilidad real basándose únicamente en estimaciones estáticas**:
1. Existen restricciones internas del driver de GPU sobre el tamaño máximo de un buffer individual (`maxMemoryAllocationSize` / `maxStorageBufferRange`), donde intentar asignar bloques mayores a 2-3 GiB de forma unitaria falla con `VK_ERROR_OUT_OF_DEVICE_MEMORY (-2)` aunque haya suficiente memoria total disponible.
2. La memoria puede ser virtualmente reservada por el sistema operativo sin que exista capacidad física para paginarla (overcommit), lo que ocasionaría caídas (*crashes*) o activación del *OOM killer* durante la carga del modelo o la generación de tokens.

## Decisiones Arquitectónicas

### 1. Prohibición de Asunciones Estáticas (Principio de Verificación Empírica)
* **Decisión:** Ningún parámetro de asignación extrema se da por válido sin una prueba activa de asignación real, mapeo de memoria y verificación de escritura/lectura.
* **Justificación:** Garantiza que el servidor de inferencia nunca intente offloadear capas a la GPU que el hardware o el driver rechazarán en tiempo de ejecución.

### 2. Estrategia de Asignación por Bloques (*Chunking*) en GPU
* **Decisión:** La memoria en la GPU se asigna y prueba en bloques discretos (habitualmente de 1.0 a 1.5 GiB) hasta alcanzar el límite real del driver Vulkan.
* **Justificación:** Evita el límite de tamaño por asignación individual de Vulkan y permite medir el techo exacto de memoria que la GPU admite físicamente.

### 3. Prueba de Escritura Forzada y Verificación de Integridad
* **Decisión:** Para cada bloque asignado en GPU VRAM o en RAM del sistema:
  - Se mapea el buffer a espacio de memoria de usuario (`vkMapMemory` o `bytearray`).
  - Se escriben patrones deterministas en límites de página (4 KB).
  - Se realiza una lectura y comparación de comprobación antes de liberar.
* **Justificación:** Fuerza al sistema operativo y a la MMU/GTT a comprometer páginas físicas reales (*page-table commit*) y descarta corrupciones de memoria.

### 4. Módulo `memory_probe.py` Desacoplado
* **Decisión:** Implementar la prueba en un módulo especializado accesible tanto desde CLI (`python -m guarida_manager.memory_probe`) como desde el menú principal interactivo (`main.py`) y como test unitario automatizado.
