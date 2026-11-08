# ADR 0008: Adopción de Capacidades de Maya: Inspección GGUF, Caché Criptográfica y Telemetría

## Estado
Aceptado

## Contexto
Tras evaluar el motor Maya (v1.1.56), se determinó que su núcleo C++/CUDA/ROCm no es compatible con hardware Intel Iris Xe/Vulkan ni encaja con la política de binarios deterministas fuera de línea de GuarIdA. Sin embargo, su arquitectura contiene módulos en Python y patrones de diseño de alto valor que resuelven debilidades críticas identificadas en la auditoría de GuarIdA (notablemente el hallazgo crítico N1: commits flotantes y validación fail-open) y optimizan la gestión de recursos en máquinas con aceleración compartida (RAM/GTT).

Se requiere formalizar la adopción e integración de estas capacidades bajo la licencia GPL-3.0 de GuarIdA (compatible con el código MIT conservando el aviso de autoría original), manteniendo el principio de cero dependencias externas no auditadas (únicamente biblioteca estándar de Python y `psutil`).

## Decisión

1. **Lector e Inspector GGUF Nativo (`guarida_manager/core/gguf_reader.py`):**
   - Implementación basada en la biblioteca estándar (`struct`, `os`) sin dependencias de paquetes binarios externos (`gguf-py`).
   - Validación estructural inmediata: comprobación de magic bytes (`GGUF`), versión de formato, lectura segura de cabeceras, tensores y shards particionados (`check_shards`).
   - Extracción de metadatos del modelo: arquitectura (`general.architecture`), tamaño de contexto nativo (`*.context_length`), conteo de capas (`*.block_count`), recuento y distribución de expertos MoE (`*.expert_count`, `*.expert_used_count`).
   - Integración con `comparator.py` y `hardware.py`: sustitución de tablas de estimación empíricas estáticas por cálculo dinámico de huella en VRAM/RAM basado en la geometría real de los tensores.

2. **Caché Persistente de Verificación Criptográfica (`guarida_manager/core/verificador.py`):**
   - Sistema de caché indexado por tupla `(ruta_absoluta, tamano_bytes, mtime_ns)` mapeada a su digest `sha256`.
   - Persistencia local en SQLite/JSON (`.guarida_verified.json` en `~/.guarida/`).
   - Reducción del coste I/O: evita verificar repetidamente archivos multigiabyte en arranques sucesivos o verificaciones periódicas de integridad si el archivo no ha cambiado.
   - Soporte para listas blancas de hashes canónicos (contemplando republicaciones legítimas upstream).

3. **Endurecimiento del Catálogo de Modelos (Cierre de Hallazgo N1):**
   - Prohibición de referencias flotantes (`main`, `latest`) en las definiciones de modelos.
   - Fijación obligatoria de commit SHA completo de Hugging Face y SHA-256 por archivo/shard en el catálogo oficial de GuarIdA.
   - Política estricta *fail-closed*: abortar inmediatamente la descarga, verificación o ejecución si no se dispone del hash o este no concuerda.

4. **Telemetría de Hardware Agnóstica en Windows (`guarida_manager/hardware/telemetria.py`):**
   - Monitorización unificada de GPU mediante DXGI y contadores de rendimiento PDH (`pdh.dll`) vía `ctypes`.
   - Soporte nativo para GPU integrada Intel Iris Xe, permitiendo consultar uso de motor 3D/Compute y memoria compartida/dedicada en Windows sin dependencias de fabricantes propietarios (NVML/ROCm).
   - Aislamiento de colectores propietarios (NVML) en procesos hijos efímeros para evitar que un fallo del driver corrompa o congele el proceso principal de GuarIdA.

5. **Robustez de Descargas HTTP y Privacidad:**
   - Consulta previa de tamaño vía petición `HEAD` (`Content-Length`) antes de iniciar descargas parciales.
   - Control de rangos HTTP para evitar bucles de reanudación ante códigos de respuesta `416 Range Not Satisfiable`.
   - Sanitización de cabeceras en redirecciones HTTP (`add_unredirected_header` / aislamiento de tokens) para evitar filtración de credenciales a dominios de distribución CDN de terceros.

6. **Desacoplamiento del Motor y Soporte MoE:**
   - Formalización del `Protocol BackendInferencia` en `guarida_manager/motor/` definiendo el ciclo de vida abstracto (`iniciar`, `detener`, `estado_salud`, `obtener_endpoint`), con `LlamaCppBackend` como implementación inicial.
   - Habilitación en lista blanca de parámetros de llama.cpp para descarga parcial de MoE (`--n-cpu-moe`, `-ot/--override-tensor`) en `FLAGS_PERMITIDOS_EXTRA_ARGS`, permitiendo ubicar expertos pesados en RAM mientras los tensores de atención se conservan en la GPU.

## Consecuencias
- **Positivas:**
  - Resolución definitiva del riesgo de integridad N1 mediante fijación criptográfica inmutable.
  - Arranques y validaciones significativamente más rápidos gracias a la caché de hash.
  - Métricas precisas de GPU en Windows para Intel Iris Xe sin herramientas externas.
  - Detección precisa de archivos truncados o corruptos antes de invocar el binario de inferencia.
  - Código desacoplado y preparado para incorporar backends adicionales o modelos MoE sin alterar la arquitectura central.
- **Negativas / Retos:**
  - Requiere mantener el parser de cabeceras GGUF si la especificación upstream introduce versiones de formato no retrocompatibles.
  - La telemetría DXGI/PDH añade lógica específica de plataforma para entornos Windows.
