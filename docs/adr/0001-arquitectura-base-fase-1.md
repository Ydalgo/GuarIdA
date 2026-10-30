# ADR 0001: Arquitectura Base y Gestor de Inferencia Local (Fase 1)

## Estado
Aceptado

## Contexto
GuarIdA es un Entorno de Desarrollo Agéntico Local (LADE) concebido para operar bajo una filosofía de "búnker digital": soberano, privado, portable y capaz de ejecutarse en hardware modesto (incluyendo APUs de 16 GB de RAM compartida) hasta estaciones de trabajo con GPUs dedicadas.

Para la Fase 1, el objetivo es construir el Gestor de Inferencia Local que servirá de motor para los futuros agentes (Coder, Tester) y el arnés de permisos de la Fase 2.

## Decisiones Arquitectónicas Cerradas

### 1. Portable Bundle en lugar de Docker
* **Decisión:** Descartar Docker en favor de un paquete portable en Python con binarios nativos precompilados.
* **Justificación:** Docker introduce sobrecarga de memoria RAM, dificulta el acceso directo a la GPU y a la memoria GTT mediante Vulkan en sistemas híbridos/APU, y requiere un demonio con privilegios de administrador/root que contradice el aislamiento estricto del búnker.

### 2. Gestión de Procesos mediante Python `subprocess.Popen` en lugar de `systemd`
* **Decisión:** El ciclo de vida del servidor de inferencia (`llama-server`) se controlará directamente desde Python usando `subprocess.Popen`.
* **Justificación:** `systemd` limita la compatibilidad exclusivamente a distribuciones Linux específicas. El uso de `subprocess.Popen` garantiza portabilidad total y homogénea en Windows, Linux y macOS.

### 3. Motor Oficial de llama.cpp (Vulkan / CPU) frente a LM Studio o KoboldCpp
* **Decisión:** Emplear exclusivamente las distribuciones binarias oficiales de `llama.cpp` con soporte Vulkan y fallback a CPU.
* **Justificación:** Se descartan intermediarios cerrados o dependientes de interfaces gráficas complejas para mantener el control directo sobre los argumentos de ejecución (`--ctx-size`, `--n-gpu-layers`, `--port`, `--host`).

### 4. Descarga Exclusiva de GGUF Precompilados de Hugging Face
* **Decisión:** No compilar ni cuantizar modelos localmente a partir de `safetensors`.
* **Justificación:** Convertir y cuantizar modelos grandes (e.g. 30B) exige picos de más de 60 GB de RAM, resultando inviable en equipos de consumo o APUs de 16 GB. Se descargarán modelos ya cuantizados en formato GGUF directamente desde Hugging Face Hub.

### 5. Enfoque "Terminal Primero" (CLI)
* **Decisión:** No incluir interfaces gráficas de usuario en la Fase 1.
* **Justificación:** Toda la lógica de benchmarks, gestión de binarios y ejecución de inferencia debe ser automatizable y verifiable desde la línea de comandos antes del desarrollo de la interfaz gráfica en PyQt6 (Fase 3).

### 6. Persistencia de Estado en SQLite (`sqlite3`)
* **Decisión:** Emplear SQLite integrado en la biblioteca estándar de Python para el estado de modelos, benchmarks y módulos instalados. Los archivos JSON quedan reservados exclusivamente para la configuración de usuario (`config.json`).
* **Justificación:** SQLite previene condiciones de carrera, proporciona consultas indexadas de alta velocidad para la caché de benchmarks por hash de hardware y garantiza integridad transaccional sin requerir servicios externos.

### 7. Hash de Hardware como Clave de Caché de Benchmarks
* **Decisión:** Cada resultado de benchmark se indexa combinando el ID del modelo con un SHA-256 del modelo de CPU, la RAM total del sistema y el dispositivo GPU detectado.
* **Justificación:** Si el usuario modifica la configuración de hardware o traslada el búnker a otra máquina, el hash cambia automáticamente forzando un nuevo benchmark óptimo.

### 8. Seguridad Activa Nativa (`watchdog` y `psutil`)
* **Decisión:** Implementar monitorización de integridad y modo búnker mediante bibliotecas estándar y de Python puro, descartando dependencias de bajo nivel del sistema operativo como `auditd`.
