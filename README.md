# GuarIdA

> **IA local offline para desarrollo.** Un agente de programación que corre en tu máquina, sin internet, sin telemetría, con permisos por rol aplicados fuera del modelo.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Estado](https://img.shields.io/badge/estado-Fase%201%20cerrada-informational)
![Plataforma](https://img.shields.io/badge/plataforma-Linux%20%7C%20Windows-lightgrey)

---

## Índice

- [De dónde viene el proyecto](#de-dónde-viene-el-proyecto)
- [El nombre](#el-nombre)
- [Qué es y qué no es](#qué-es-y-qué-no-es)
- [Primer enfoque: programación](#primer-enfoque-programación)
- [Estado actual: Fase 1 cerrada](#estado-actual-fase-1-cerrada)
- [Hoja de ruta](#hoja-de-ruta)
- [Instalación y Uso (Entorno de desarrollo)](#instalación-y-uso-entorno-de-desarrollo)
- [Licencia](#licencia)
- [Créditos y Agradecimientos](#créditos-y-agradecimientos)

---

## De dónde viene el proyecto

GuarIdA nace de un proyecto anterior basado en KoboldCpp que quedó en *stand-by* porque se estaba centrando demasiado esfuerzo en la interfaz y dejando de lado lo básico. En lugar de seguir parcheando, se vuelve al punto 0 con la experiencia ya adquirida.

El problema de fondo: la IA se ha democratizado con un éxito enorme, pero conforme ha crecido en potencia y conocimiento han aparecido nuevos problemas — déficit de stock y subida de precios en RAM, NVMe de quinta generación y, sobre todo, GPUs capaces de mover modelos con soltura. Cualquier usuario doméstico, pequeño empresario o autónomo puede usar IA por Internet, pero a costa de perder **control y privacidad**. Y eso no es un problema menor.

## El nombre

*GuarIdA* parece esconderse, pero debe leerse con una mirada más amplia. Una guarida es un sitio protegido: puede ser cualquier cosa, y en nuestro caso es **cualquier hardware doméstico**, con sus gráficas integradas. El proyecto está pensado para ordenadores modernos que puedan comprarse o ampliarse ligeramente para IA local y offline. Nadie debería saber qué pasa en nuestra guarida, qué documentos compartimos ni qué se habla en ella.

## Qué es y qué no es

- **No** nace con la intención de ser un software cerrado ni un asistente en la nube.
- **Sí** es, en esta primera etapa, una serie de programas y configuraciones para democratizar las IAs locales offline en hardware modesto.
- Quizás tarde, pero lo tendremos tarde y controlado. Quizás sea lento, pero es *nuestro* lento. El objetivo es un producto eficaz, aunque no sea el más rápido.

## Primer enfoque: programación

El primer dominio es la programación. Cualquier modelo en la nube tendrá mejores resultados y será mucho más rápido; no es el deseo del proyecto competir en esos parámetros. Se compite en **seguridad, privacidad y capacidad de uso en cualquier situación**, incluso sin conexión. Solo se necesita el sistema operativo, el hardware y un punto de luz que alimente ese PC modesto.

## Estado actual: Fase 1 cerrada

### Stack de inferencia

| Elemento | Valor |
|---|---|
| Backend | `llama-server` con Vulkan (build `b11707`) |
| Servicio | systemd de usuario, puerto `8083` |
| Modelo | Qwen2.5-Coder-7B (contexto 32k), GGUF, Q4 |
| Contexto en uso | 16 384 tokens |
| Estado del GTT | ~93 % en la APU con esta configuración |

**Restricción operativa:** no se sube a 32k sin reducir `--n-gpu-layers` o el tipo de KV cache. Cualquiera de las dos palancas degrada el rendimiento medido. Se acepta como límite conocido.

**KoboldCpp** (puerto `5001`) se mantiene solo como referencia, no como backend del stack.

### Por qué llama.cpp Vulkan y no KoboldCpp

En esta fase se midieron **KoboldCpp Vulkan, llama.cpp CPU y llama.cpp Vulkan** con los mismos cuatro casos: generar una función, corregir un bug, explicar un fragmento y responder con contexto largo. En el proyecto anterior se habían evaluado también Ollama y LM Studio.

| Caso | KoboldCpp Vulkan | llama.cpp CPU | llama.cpp Vulkan |
|---|---:|---:|---:|
| Generar función | 13,05 t/s | 7,51 t/s | 11,99 t/s |
| Corregir bug | 12,01 t/s | 8,20 t/s | 13,01 t/s |
| Explicar código | 10,50 t/s | 6,89 t/s | 12,68 t/s |
| Contexto largo | 0,53 t/s | 0,11 t/s | **0,80 t/s** |

- En casos cortos, KoboldCpp y llama.cpp Vulkan están empatados (variaciones dentro del ruido).
- En **contexto largo**, llama.cpp Vulkan es ~50 % más rápido. Es el escenario que importa para un agente, porque el prompt crece con las iteraciones.
- llama.cpp CPU se descartó: ~7× más lento en contexto largo (386 s frente a 53 s).
- FlashAttention se descartó en Vulkan/APU: sin ganancia consistente y ligeramente peor en contexto largo.

El argumento de fondo no es solo el rendimiento: `llama-server` es el binario oficial de llama.cpp, comparte ecosistema con el arnés que ejecutará las herramientas, permite control granular de parámetros (KV cache K/V por separado, batch size, samplers) y funciona como backend puro sin web UI y sin `--tools`. **La seguridad la da el arnés, no el servidor.**

### Arquitectura en construcción

1. **Arnés:** valida ruta, operación y rol antes de ejecutar cada herramienta. La seguridad no la da el prompt.
2. **Roles:** Conversacional (solo lectura), Coder (worktree aislado), Patcher, Tester, Reviewer, Security, Documentador.
3. **Worktrees aislados:** un parche nunca toca el proyecto original hasta que se aprueba.

## Hoja de ruta

- [x] **Fase 1:** infraestructura de inferencia medida y cerrada.
- [ ] **Fase 2:** contrato del arnés + rol Conversacional.
- [ ] **Fase 3:** rol Coder en worktree aislado.
- [ ] **Fase 4:** aislamiento del sistema (Landlock/bubblewrap en Linux; usuario sin permiso de escritura en Windows).
- [ ] **Fase 1.5 (opcional, condicionada al arnés):** optimización fina del backend (KV cache `q4_0`, batch size, samplers, concurrencia).

## Instalación y Uso (Entorno de desarrollo)

### 1. Clonar el repositorio y requisitos
Se requiere Python 3.10 o superior y la librería `psutil`.

```bash
git clone git@github.com:Ydalgo/GuarIdA.git
cd GuarIdA
pip install psutil
```

### 2. Menú de Inicio Interactivo
Para acceder al panel interactivo de terminal y gestionar diagnósticos, caché y pruebas:

```bash
python main.py
# O también mediante el módulo del paquete:
python -m guarida_manager
```

### 3. Comandos directos por submódulo
Si prefieres ejecutar una función específica sin pasar por el menú interactivo:

- **Diagnóstico del Hardware (CPU, RAM, GPU, hash SHA-256):**
  ```bash
  python -m guarida_manager.hardware
  ```

- **Prueba de Asignación y Estrés Real de Memoria (GPU VRAM + RAM):**
  ```bash
  python -m guarida_manager.memory_probe
  ```

- **Estado de Caché y Base de Datos (SQLite local):**
  ```bash
  python -m guarida_manager.cache
  ```

- **Catálogo de Modelos y Auditoría Legal (EU AI Act):**
  ```bash
  python -m guarida_manager.downloader.models
  ```

- **Aprovisionamiento Único del Búnker (Setup 100% Offline):**
  ```bash
  python -m guarida_manager.downloader.provisioning
  ```

- **Ejecutar Suite de Pruebas Unitarias:**
  ```bash
  python -m unittest discover tests
  ```

### 4. Gobernanza y Cumplimiento Normativo (EU AI Act)
GuarIdA incorpora un motor de auditoría legal automática para usuarios en **España y la Unión Europea** basado en el **Reglamento (UE) 2024/1689 (EU AI Act)**:
- Verificación del resumen público del conjunto de datos de entrenamiento (Art. 53(1)(d)).
- Respeto a las directivas de derechos de autor y reservas de minería de datos (Directiva UE 2019/790).
- Compatibilidad de licencias de código abierto (Apache-2.0, MIT).

### 5. Criptografía Preparada para la Era Postcuántica (PQC-Ready)
El almacenamiento local, la configuración y el estado del búnker se protegen mediante primitivas resistentes a la computación cuántica:
- Derivación de claves basada en la función esponja **SHAKE-256** (FIPS 202) y **SHA3-512** (256 bits de seguridad cuántica simétrica).
- Cifrado simétrico autenticado (*Encrypt-then-MAC*) para evitar ataques de manipulación o extracción futura (*harvest now, decrypt later*).

### 6. Decisiones de Arquitectura (ADRs)
- [ADR 0001: Arquitectura Base y Gestor de Inferencia Local](docs/adr/0001-arquitectura-base-fase-1.md)
- [ADR 0002: Verificación Empírica y Prueba de Estrés de Memoria GPU/GTT](docs/adr/0002-verificacion-empirica-memoria-gpu.md)
- [ADR 0003: Aprovisionamiento Único Offline, Gobernanza Regional y Seguridad Postcuántica](docs/adr/0003-aprovisionamiento-offline-gobernanza-postcuantica.md)

## Licencia

GuarIdA se distribuye bajo **GNU General Public License v3.0 (GPL-3.0)**. Es una licencia *copyleft*: cualquier derivado distribuido debe mantener la misma licencia y publicar su código fuente. El proyecto es y será siempre OpenSource; quien lo siga no puede cerrarlo.

Consulta [LICENSE](LICENSE) para el texto completo.

---

## Créditos y Agradecimientos

Este proyecto se construye y evoluciona mediante desarrollo asistido en colaboración con modelos de Inteligencia Artificial que han aportado en distintas etapas:

- **DeepSeek:** Por su valiosa colaboración en los inicios del proyecto, ayudando a plantear los primeros experimentos y la conceptualización de la inferencia local offline.
- **Claude:** Por su apoyo fundamental en la definición de la arquitectura, el enfoque de seguridad desacoplado del modelo y la estructuración del diseño general.
- **Gemini:** Por la ingeniería de software y el desarrollo técnico activo de la Fase 1 (detección de hardware nativo, persistencia en SQLite, gestión de binarios y construcción del entorno).
