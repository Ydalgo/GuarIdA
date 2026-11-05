# ADR 0007: Afinamiento Empírico y Benchmarking Reproducible

## Estado
Aceptado

## Contexto
El lanzamiento por defecto de `llama-server` o el uso de configuraciones estáticas no garantiza el aprovechamiento óptimo de la aceleración por hardware (Vulkan, CUDA, CPU multi-hilo, memoria compartida GTT/VRAM). Asimismo, un barrido por fuerza bruta en una rejilla completa ($ngl \times t \times c \times b \times ub \times kv \times fa$) incurre en miles de arranques inviables temporalmente.

Se requería un subsistema desacoplado que descubra dinámicamente las capacidades del binario instalado, explore por etapas el espacio de parámetros de forma guiada con poda temprana, aplique una batería de estrés estadísticamente rigurosa (descarte de calentamientos, repeticiones adaptativas por CV% e intervalos de confianza bootstrap) y persista perfiles y sesiones versionados para comparar modelos de manera reproducible.

## Decisión
1. **Descubrimiento del Binario (`guarida_manager/tuning/capacidades.py`):**
   - Inspección automática de `--version`, `--help` y `--list-devices` tanto en `llama-server` como en `llama-bench`.
   - Mapeo de flags soportados frente a una lista blanca de candidatos seguros (`FLAGS_CANDIDATOS_EXPLORABLES`), validando compatibilidad (`ubatch <= batch`, cuantización KV con Flash Attention, descarte de `--mlock` o `--numa` según sistema operativo).
   - Persistencia en tabla SQLite `capacidades_binario` indexada por `sha256_binario`.

2. **Perfiles Versionados (`guarida_manager/tuning/perfiles.py`):**
   - Definición de `PerfilBarrido` y `PerfilBateria` serializados con hash SHA-256 canónico (claves ordenadas).
   - Perfiles predefinidos: `rapido` (~10 min), `estandar` (~45 min) y `exhaustivo`.

3. **Búsqueda por Etapas con Poda Temprana (`guarida_manager/tuning/buscador.py`):**
   - Etapa 0: Baseline por defecto.
   - Etapa 1: Búsqueda binaria de $n\_gpu\_layers$ máximo estable en VRAM/GTT y comprobación de escalones inferiores.
   - Etapa 2: Afinamiento de hilos de CPU (núcleos físicos vs lógicos).
   - Etapa 3: Exploración de `batch_size` y `ubatch_size`.
   - Etapa 4: Combinatoria de Flash Attention y cuantización de KV Cache (`f16`, `q8_0`, `q4_0`).
   - Etapa 5: Escalones de contexto máximo estable ($2k \to 4k \to 8k \to 16k \to 32k$).
   - Poda temprana de configuraciones cuya mediana inicial sea inferior al umbral del mejor candidato.

4. **Ciclo de Vida y Batería de Estrés (`ejecutor.py`, `bateria.py`):**
   - Puerto dinámico por intento, monitor de memoria en hilo daemon (RAM del árbol de procesos y VRAM) y clasificación de fallos mediante análisis del log (OOM, flag desconocido, timeout).
   - Pruebas de prefill (PP), generación sostenida (TG), latencia primer token (TTFT en streaming), escenario mixto y verificación determinista de JSON.
   - Control de variables de confusión (`cache_prompt=False`, `temperature=0`, seed determinista, `ignore_eos=True`).
   - Estadística rigurosa: calentamientos descartados, repeticiones adaptativas si $CV > 5\%$ y cálculo de Intervalo de Confianza 95% mediante remuestreo bootstrap no paramétrico.

5. **Scoring, Informes y Menú (`scoring.py`, `informes.py`, `menu.py`, `__main__.py`):**
   - Objetivos configurables: `chat`, `batch`, `agente_contexto_largo`, `equilibrado` y cálculo del frente de Pareto multiobjetivo.
   - Desempate por menor consumo de memoria ante solapamiento de intervalos de confianza.
   - Persistencia en `bench_sesiones`, `bench_configs`, `bench_ejecuciones` y actualización automática de `configuraciones_optimas`.
   - Exportación de informes en CSV y JSON a `~/.guarida/informes/` y comparador visual entre sesiones.
   - Interfaz en el menú principal (Opción 7) y CLI no interactiva: `python -m guarida_manager.tuning --modelo X --perfil estandar --objetivo chat`.

## Consecuencias
- **Positivas:**
  - Optimización empírica desatendida respetando un presupuesto temporal acotado.
  - Reproducibilidad científica: cualquier modelo puede ser sometido a idéntico perfil de batería sobre el mismo hardware.
  - Seguridad reforzada: saneamiento estricto de banderas CLI y asignación dinámica de puertos sin colisión.
  - Sin dependencias de terceros: 100% biblioteca estándar de Python + `psutil`.
