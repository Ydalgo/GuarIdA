# GuarIdA

> **IA local offline para desarrollo.** Un agente de programación que corre en tu máquina, sin internet, sin telemetría, con permisos por rol aplicados fuera del modelo.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Estado](https://img.shields.io/badge/estado-Fase%201%20cerrada-informational)
![Plataforma](https://img.shields.io/badge/plataforma-Linux%20%7C%20Windows-lightgrey)

---

## Índice

- [Descargas y Versiones en GitHub](#descargas-y-versiones-en-github)
- [De dónde viene el proyecto](#de-dónde-viene-el-proyecto)
- [El nombre](#el-nombre)
- [Qué es y qué no es](#qué-es-y-qué-no-es)
- [Primer enfoque: programación](#primer-enfoque-programación)
- [Estado actual: Fase 1 cerrada](#estado-actual-fase-1-cerrada)
- [Hoja de ruta](#hoja-de-ruta)
- [Instalación y Uso](#instalación-y-uso)
- [Estructura del proyecto y rutas](#estructura-del-proyecto-y-rutas)
- [Licencia](#licencia)
- [Créditos y Agradecimientos](#créditos-y-agradecimientos)

---

## Descargas y Versiones en GitHub

En la sección **Releases** de GitHub y en el repositorio dispones de **tres formatos** según tu necesidad. Ninguno requiere tener Python instalado previamente en el equipo:

| Versión | Archivo en GitHub | Qué incluye | Cuándo usarla |
|---|---|---|---|
| **A. Portable (Todo preparado)** | `GuarIdA-Portable-win64-vX.Y.Z.zip` *(Releases)* | Código + Python embebido (`runtime/`) + dependencias + herramientas (`llama-server`, `MinGit`, `ripgrep` en `datos/bin/`). | **Recomendada en Windows 10/11.** Descomprimir y doble clic en `Iniciar_GuarIdA.bat` o `Iniciar_Web.bat`. |
| **B. Desde cero (Código fuente)** | `git clone` o `Source code (zip)` | Solo código fuente y scripts de instalación (`Instalar_Desde_Cero.bat` / `instalar_desde_cero.sh`). | Para compilar/descargar todo desde el principio en **Windows, Linux o macOS** (los scripts descargan Python portable, dependencias y herramientas). |
| **C. Instalador MSI Offline** | `GuarIdA-Offline-Setup-x64-vX.Y.Z.msi` *(Releases)* | Todo el paquete preparado dentro de un instalador nativo de Windows sin conexión. | Para instalar en equipos Windows sin internet (crea accesos directos en Menú Inicio y Escritorio en `%LocalAppData%\Programs\GuarIdA`). |

> **Nota sobre modelos `.gguf`:** Debido al límite de 2 GB por archivo en GitHub Releases, los modelos de IA no van incluidos en el `.zip` ni en el `.msi`. Puedes descargarlos una sola vez desde el propio menú de GuarIdA o copiar tus archivos `.gguf` a la carpeta `datos/models/`.

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
- [x] **Fase 2: Motor de inferencia local, Punto Dulce y Árbol de Nodos AST** (levantamiento autónomo de `llama-server` con perfiles óptimos de SQLite, afinador empírico por etapas, indexación AST + compresión BPE + búsqueda híbrida RRF y comparativa cara a cara `Qwen2.5` vs `Qwen3`).
- [ ] **Fase 3: Arnés de agentes y roles** (en curso). Hecho: proyectos, indexación incremental de repositorios/documentos, RAG local con citas y sesiones de chat persistentes (menú `[7]`). Pendiente: orquestación autónoma en bucles iterativos, permisos por rol y aplicación de parches en worktrees de Git.
- [ ] **Fase 4: Aislamiento del sistema** (sandboxing de herramientas a nivel de sistema operativo).

## Instalación y Uso

### Opción A: Versión Portable (Windows 11 / Win64, sin instalar nada)
1. Descarga `GuarIdA-Portable-win64-vX.Y.Z.zip` desde **Releases** y descomprímelo en cualquier carpeta.
2. Haz doble clic en:
   - `Iniciar_GuarIdA.bat` para abrir el menú interactivo en terminal.
   - `Iniciar_Web.bat` para abrir la interfaz web local.

### Opción B: Desde cero (Windows, Linux y macOS — no requiere Python previo)
1. Clona o descarga el código fuente:
   ```bash
   git clone git@github.com:Ydalgo/GuarIdA.git
   cd GuarIdA
   ```
2. Ejecuta el instalador automático según tu sistema operativo (descarga Python embebido en `runtime/`, instala dependencias y descarga `llama-server`, `git` y `ripgrep` en `datos/bin/`):
   - **Windows:** doble clic en `Instalar_Desde_Cero.bat` (o directamente `Iniciar_GuarIdA.bat`, que lo lanza si falta `runtime/`).
   - **Linux / macOS:**
     ```bash
     chmod +x *.sh scripts/instalar_unix.sh
     ./instalar_desde_cero.sh
     ./iniciar_guarida.sh   # o ./iniciar_web.sh
     ```

### Opción C: Generar o publicar el `.zip` portable, `.msi` offline y Docker (GHCR)
Al hacer push de un tag `v*` (por ejemplo `git tag v0.2.0 && git push origin v0.2.0`), el workflow [release.yml](.github/workflows/release.yml) ejecuta los tests, compila `GuarIdA-Portable-win64` + `GuarIdA-Offline-Setup-x64.msi` + `SHA256SUMS.txt` para **GitHub Releases**, y publica la imagen Docker en **GitHub Packages (`ghcr.io/ydalgo/guarida`)**.

En local también puedes construir los paquetes manualmente:
```powershell
# 1. Generar GuarIdA-Portable-win64-vX.Y.Z.zip en dist\
powershell -ExecutionPolicy Bypass -File scripts\crear_portable_win64.ps1

# 2. Generar GuarIdA-Offline-Setup-x64-vX.Y.Z.msi en dist\ (requiere WiX Toolset: dotnet tool install --global wix)
powershell -ExecutionPolicy Bypass -File scripts\crear_msi_offline.ps1
```

### GuarIdA como servicio (Red local, Docker y acceso desde Internet)
- **Red local (Wi-Fi / LAN):** ejecuta `Iniciar_Servicio.bat` (Windows) o `./iniciar_servicio.sh` (Linux/macOS) para escuchar en `0.0.0.0:8080` y acceder desde móviles o tablets con la IP local mostrada en consola.
- **Desde Internet sin abrir puertos ni dominio:** pulsa **Acceso Remoto** en la barra superior de la web o arranca con `--remoto` (`Iniciar_Servicio.bat --remoto`). Usa `cloudflared` (Apache-2.0, gratuito) y protege el acceso con un código aleatorio.
- **Docker / GitHub Packages:**
  ```bash
  docker compose up -d
  ```

## Estructura del proyecto y rutas

```text
GuarIdA/
├── Iniciar_GuarIdA.bat / iniciar_guarida.sh   # Arranque CLI (usa runtime/ embebido)
├── Iniciar_Web.bat / iniciar_web.sh           # Arranque Web (usa runtime/ embebido)
├── Instalar_Desde_Cero.bat / instalar_desde_cero.sh
├── main.py
├── guarida_manager/                           # Código fuente del paquete
├── runtime/                                   # Python embebido + dependencias (ignorado en Git)
├── datos/                                     # Modo portable: bin/, models/, logs/, *.db, config.json
├── scripts/                                   # Instaladores internos y generadores de Release (.zip / .msi)
├── docs/                                      # ADRs y documentación técnica
└── tests/                                     # Suite de pruebas
```

**Resolución de rutas (`DIRECTORIO_RAIZ_GUARIDA`):**
1. Si existe la variable de entorno `GUARIDA_HOME`, se usa esa ruta.
2. Si existe `.portable`, `runtime/` o `datos/` en la raíz del proyecto (**modo portable**), todo se guarda dentro de `datos/`.
3. En instalaciones globales con `pip`, se usa `~/.guarida`.

### Uso avanzado (Entorno de desarrollo con Python del sistema)
Si prefieres usar tu propio Python 3.10+ del sistema en lugar del runtime embebido:
```bash
pip install -e .
python main.py
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

### 9. Afinador Empírico, Punto Dulce y Árbol de Nodos AST (Compresión BPE + KV Cache)
Sistema automatizado para encontrar el **Punto Dulce** de cualquier modelo sobre el hardware local y acelerar la inferencia de código mediante poda sintáctica AST:
- **Descubrimiento de capacidades:** Detección dinámica de flags de `llama-server` y `llama-bench`.
- **Búsqueda por etapas con guardado progresivo en SQLite:** Exploración guiada ($ngl \to threads \to batch/ubatch \to kv/fa \to ctx$) que persiste la mejor configuración parcial en `configuraciones_optimas` y `bench_configs` (reportando velocidad de lectura `PP tok/s`, velocidad de creación `TG tok/s` y contexto máximo estable).
- **Árbol de Nodos AST + Compresión BPE + Búsqueda Híbrida RRF (`guarida_manager/arbol_nodos.py`):** Descompone archivos de código en nodos sintácticos (`MODULO`, `CLASE`, `FUNCION`, `METODO`), indexa embeddings con caché `SHA-256`, fusiona similitud coseno con símbolos AST (RRF) y construye un esqueleto minificado consciente de BPE reutilizando la caché KV (`cache_prompt=True`).
- **Resultados empíricos medidos en Intel Core i5-1135G7 + Iris Xe (`qwen2.5-coder-7b` + `nomic-embed-text-v1.5`):**
  - **Ahorro de tokens:** de `629` a `164 tokens` (**73.93% de ahorro / `3.84x` menos tokens**).
  - **Aceleración (Speedup):** latencia reducida de `8363 ms` a `3193 ms` (**`2.62x` más rápido**).
  - **Calidad técnica:** incremento del `75.0%` al **`87.5%`** al eliminar ruido contextual.
- **Uso vía CLI:**
  ```bash
  python -m guarida_manager.tuning --modelo qwen2.5-coder-7b-q4 --perfil rapido --objetivo coder_ast
  ```

### 10. Proyectos y chat con tu repositorio (RAG 100% local)
Menú principal → `[7] Proyectos y Documentos`:
- **Proyectos:** registra una carpeta (código y/o documentación). Se indexa al abrir el chat: Python por árbol AST; Markdown/texto por fragmentos de ~256 tokens; JS/TS/Go/Rust/Java/C/C++ por definiciones.
- **Indexación incremental:** los embeddings se guardan en `guarida.db` (clave = modelo + SHA-256 del texto); reindexar solo vectoriza lo nuevo o modificado.
- **Búsqueda:** Reciprocal Rank Fusion (coseno + coincidencia léxica de identificadores). Sin servidor de embeddings degrada a ranking léxico, avisando.
- **Citas:** cada respuesta lista `archivo:líneas` de las fuentes usadas. El contexto recuperado solo viaja en el turno actual para no inflar la ventana.
- **Sesiones:** los chats se guardan por proyecto y se pueden reanudar.
- **Seguridad:** no se indexan `.env*`, claves (`*.pem`, `*.key`, `id_rsa*`), `*.db`, modelos, enlaces simbólicos, rutas fuera del proyecto ni archivos > 1 MB.

### 11. Decisiones de Arquitectura (ADRs)
- [ADR 0001: Arquitectura Base y Gestor de Inferencia Local](docs/adr/0001-arquitectura-base-fase-1.md)
- [ADR 0002: Verificación Empírica y Prueba de Estrés de Memoria GPU/GTT](docs/adr/0002-verificacion-empirica-memoria-gpu.md)
- [ADR 0003: Aprovisionamiento Único Offline, Gobernanza Regional y Seguridad Postcuántica](docs/adr/0003-aprovisionamiento-offline-gobernanza-postcuantica.md)
- [ADR 0004: Arquitectura Multi-Rol Especializada, Aprovisionamiento Flexible y Comparador de Cuantizaciones](docs/adr/0004-arquitectura-multi-rol-aprovisionamiento-flexible.md)
- [ADR 0005: Persistencia de Perfiles de Afinamiento Óptimo y Ecosistema de Herramientas Portables](docs/adr/0005-persistencia-afinamiento-optimo-y-herramientas-bunker.md)
- [ADR 0006: Motor de Inferencia Local y Control de Procesos](docs/adr/0006-motor-inferencia-local-y-control-de-procesos.md)
- [ADR 0007: Afinamiento Empírico y Benchmarking Reproducible](docs/adr/0007-afinamiento-empirico-y-benchmarking-reproducible.md)
- [ADR 0008: Adopción Selectiva de Capacidades Maya (Inspección GGUF, Caché y Telemetría)](docs/adr/0008-adopcion-capacidades-maya-inspeccion-gguf-cache-y-telemetria.md)
- [ADR 0009: Árbol de Nodos AST, Compresión BPE, Búsqueda Híbrida RRF y Comparativa Cara a Cara](docs/adr/0009-arbol-nodos-ast-compresion-bpe-y-comparativa-modelos.md)
- [ADR 0010: Optimizaciones Avanzadas de Inferencia, Subsistema de Proyectos y RAG de Repositorio Local](docs/adr/0010-optimizaciones-motor-proyectos-y-rag-repositorio.md)
- [ADR 0011: Correcciones de Auditoría del RAG de Proyectos (Fase 3)](docs/adr/0011-correcciones-auditoria-rag-proyectos.md)

## Licencia

GuarIdA se distribuye bajo **GNU General Public License v3.0 (GPL-3.0)**. Es una licencia *copyleft*: cualquier derivado distribuido debe mantener la misma licencia y publicar su código fuente. El proyecto es y será siempre OpenSource; quien lo siga no puede cerrarlo.

Consulta [LICENSE](LICENSE) para el texto completo.

---

## Créditos y Agradecimientos

Este proyecto se construye y evoluciona mediante desarrollo asistido en colaboración con modelos de Inteligencia Artificial que han aportado en distintas etapas:

- **DeepSeek:** Por su valiosa colaboración en los inicios del proyecto, ayudando a plantear los primeros experimentos y la conceptualización de la inferencia local offline.
- **Claude:** Por su apoyo fundamental en la definición de la arquitectura, el enfoque de seguridad desacoplado del modelo y la estructuración del diseño general.
- **Gemini:** Por la ingeniería de software y el desarrollo técnico activo de la Fase 1 (detección de hardware nativo, persistencia en SQLite, gestión de binarios y construcción del entorno).
