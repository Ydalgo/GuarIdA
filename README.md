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

## Estado actual

El proyecto está enfocado en exprimir hardware doméstico real (APUs, gráficas integradas de portátiles o GPUs modestas), funcionando 100% en local y sin conexión a internet tras la configuración inicial.

Tenemos cerrado el núcleo de diagnóstico, aprovisionamiento y persistencia:
- Detección real de hardware (CPU, RAM y memoria VRAM/GTT compartida tanto en Windows como en Linux).
- Prueba empírica de estrés de memoria: antes de dar nada por bueno, se fuerza la asignación en memoria para ver si el hardware aguanta.
- Catálogo multirrol: soporte para modelos de código, chat, embeddings y modelos sin censura para pruebas de seguridad.
- Persistencia en SQLite (`guarida.db`): almacena la mejor configuración conseguida en cada máquina (capas GPU, contexto, velocidad de tokens). Si borras el `.gguf` para liberar espacio, la configuración afinada no se pierde.
- Gestor de herramientas: detección y descarga de herramientas portables (`llama-server`, `git`, `ripgrep`).
- Auditoría legal transparente (EU AI Act) para saber el estado de licencias y datos de entrenamiento de cada modelo.

<details>
<summary>Histórico: comparativa previa de inferencia (fase inicial del proyecto)</summary>

Datos de rendimiento medidos en pruebas iniciales previas con APU/Vulkan:

| Caso | KoboldCpp Vulkan | llama.cpp CPU | llama.cpp Vulkan |
|---|---:|---:|---:|
| Generar función | 13,05 t/s | 7,51 t/s | 11,99 t/s |
| Corregir bug | 12,01 t/s | 8,20 t/s | 13,01 t/s |
| Explicar código | 10,50 t/s | 6,89 t/s | 12,68 t/s |
| Contexto largo | 0,53 t/s | 0,11 t/s | **0,80 t/s** |

Conclusiones de la comparativa:
- `llama-server` Vulkan rinde mejor en contextos largos, que es lo que devora un agente con iteraciones sucesivas.
- No delegar seguridad en el modelo: la seguridad la gestiona el arnés del sistema, no el prompt.
</details>

## Hoja de ruta

- [x] **Fase 1: Base de hardware, diagnóstico y aprovisionamiento offline** (detección GPU/GTT, caché SQLite, herramientas del búnker y perfiles afinados).
- [ ] **Fase 2: Motor de inferencia local y control de procesos** (levantamiento autónomo de `llama-server`, cliente HTTP local offline y verificación de salud).
- [ ] **Fase 3: Arnés de agentes y roles** (orquestación en bucles iterativos, árboles de nodos, embeddings y parches en worktrees de Git).
- [ ] **Fase 4: Aislamiento del sistema** (sandboxing de herramientas a nivel de sistema operativo).

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

- **Comparador de Cuantizaciones y Memoria de Contexto:**
  ```bash
  python -m guarida_manager.comparator
  ```

- **Estado y Descarga de Herramientas del Búnker (llama-server, git, ripgrep):**
  ```bash
  python -m guarida_manager.downloader.tools
  ```

- **Aprovisionamiento Único del Búnker (Setup 100% Offline):**
  ```bash
  python -m guarida_manager.downloader.provisioning
  ```

- **Ejecutar Suite de Pruebas Unitarias:**
  ```bash
  python -m unittest discover tests
  ```

### 4. Separación de roles (ahorro de memoria y tokens)
En vez de cargar un modelo gigante para todo, dividimos las tareas:
- **Chat / Interacción:** Modelo ligero y rápido en español (ej. Qwen2.5-3B) para entenderte y coordinar sin ensuciar la ventana de contexto con bloques de código.
- **Coder:** Modelo técnico especializado en código y parches diff (ej. Qwen2.5-Coder-7B en Q4 o Q3).
- **Embeddings:** Vectorización de código y árboles sintácticos (ej. BGE-M3 o Nomic Embed) para buscar rápido en el repositorio sin enviar archivos enteros al modelo.
- **Sin Censura / Desalineado (Opcional):** Modelos sin filtros para auditorías de seguridad y pentesting local.

### 5. Memoria de afinamiento en hardware
Afinar un modelo en hardware modesto lleva tiempo. Cuando encontramos el punto dulce de capas GPU (`n_gpu_layers`), contexto y memoria, se guarda en `guarida.db`:
- Si borras un archivo `.gguf` de 8 GB para hacer hueco en el disco, **la configuración afinada se queda guardada**.
- Si vuelves a descargar ese modelo en el futuro, el búnker ya sabe exactamente cómo correrlo en tu máquina sin tener que repetir pruebas.

### 6. Herramientas portables
El agente funciona desconectado gracias a herramientas locales (detecta las del sistema o las descarga en su carpeta):
- **`llama-server`:** El motor de inferencia con soporte Vulkan/CPU.
- **`git`:** Para crear ramas y *worktrees* aislados donde el agente prueba los parches sin tocar tu código principal.
- **`ripgrep` (`rg`):** Para buscar en el código en milisegundos en vez de devorar tokens indexando archivos enteros.

### 7. Auditoría legal y normativa (EU AI Act)
Para saber qué metemos en la máquina, el catálogo revisa licencias y datos de entrenamiento según la ley europea de IA (Reglamento UE 2024/1689):
- Muestra el estado legal y las fuentes públicas de entrenamiento.
- **Es informativo, no restrictivo:** te avisa de la situación legal del modelo, pero no te impide usar lo que quieras en tu máquina.

### 8. Seguridad y cifrado
El estado del búnker y los datos locales se aseguran con derivación SHAKE-256 / SHA3 y comprobaciones HMAC para evitar manipulaciones locales.

### 9. Decisiones de Arquitectura (ADRs)
- [ADR 0001: Arquitectura Base y Gestor de Inferencia Local](docs/adr/0001-arquitectura-base-fase-1.md)
- [ADR 0002: Verificación Empírica y Prueba de Estrés de Memoria GPU/GTT](docs/adr/0002-verificacion-empirica-memoria-gpu.md)
- [ADR 0003: Aprovisionamiento Único Offline, Gobernanza Regional y Seguridad Postcuántica](docs/adr/0003-aprovisionamiento-offline-gobernanza-postcuantica.md)
- [ADR 0004: Arquitectura Multi-Rol Especializada, Aprovisionamiento Flexible y Comparador de Cuantizaciones](docs/adr/0004-arquitectura-multi-rol-aprovisionamiento-flexible.md)
- [ADR 0005: Persistencia de Perfiles de Afinamiento Óptimo y Ecosistema de Herramientas Portables](docs/adr/0005-persistencia-afinamiento-optimo-y-herramientas-bunker.md)

## Licencia

GuarIdA se distribuye bajo **GNU General Public License v3.0 (GPL-3.0)**. Es una licencia *copyleft*: cualquier derivado distribuido debe mantener la misma licencia y publicar su código fuente. El proyecto es y será siempre OpenSource; quien lo siga no puede cerrarlo.

Consulta [LICENSE](LICENSE) para el texto completo.

---

## Créditos y Agradecimientos

Este proyecto se construye y evoluciona mediante desarrollo asistido en colaboración con modelos de Inteligencia Artificial que han aportado en distintas etapas:

- **DeepSeek:** Por su valiosa colaboración en los inicios del proyecto, ayudando a plantear los primeros experimentos y la conceptualización de la inferencia local offline.
- **Claude:** Por su apoyo fundamental en la definición de la arquitectura, el enfoque de seguridad desacoplado del modelo y la estructuración del diseño general.
- **Gemini:** Por la ingeniería de software y el desarrollo técnico activo de la Fase 1 (detección de hardware nativo, persistencia en SQLite, gestión de binarios y construcción del entorno).
