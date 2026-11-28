# Visión futura de GuarIdA (Fase 5+ · RFCs conceptuales)

> **Estado:** Exploratorio / Visión futura (Fase 5+)  
> **Fecha:** 2026-11-28  
> **Alcance:** Documentación estratégica y análisis arquitectónico. No altera la hoja de ruta activa de Fase 3/4 ni el [Estudio de arquitectura de inferencia](https://github.com/Ydalgo/GuarIdA/blob/estudio/motores-inferencia/docs/estudio_inferencia/README.md) en curso (ADR 0014 queda reservado para dicho estudio según [ADR 0013](https://github.com/Ydalgo/GuarIdA/blob/estudio/motores-inferencia/docs/adr/0013-estudio-arquitectura-inferencia.md)).

---

## 1. Propósito

GuarIdA nació con una premisa clara: **democratizar la IA local, offline y privada sobre hardware doméstico real**, automatizando la complejidad técnica para que el usuario no tenga que ser ingeniero de sistemas ni especialista en IA para exprimir su máquina.

Hasta ahora, el núcleo del proyecto se ha centrado en:
1. Detección y prueba empírica de hardware (`hardware.py`, `memory_probe.py`).
2. Afinado reproducible de inferencia local en GGUF (`tuning/`, `engine/server.py`).
3. Indexación AST + RAG local + memoria declarativa e ingesta visual VLM (`proyectos.py`, `arbol_nodos.py`, `chat.py`, [ADR 0012](../adr/0012-arquitectura-persistencia-grafo-ast-y-vlm.md)).

Esta carpeta recoge y analiza dos líneas de evolución natural para cuando las fases operativas actuales (Fase 3, Fase 4 y Estudio de Inferencia) estén estabilizadas:
- Que **cualquier usuario pueda adaptar y hacer aprender a sus modelos locales** (desde repositorios y conversaciones) de forma automática y ajustada a su hardware, sin limitarse solo a RAG.
- Que **GuarIdA deje de estar acoplado al rol único de programación** y evolucione hacia un **núcleo agnóstico capaz de orquestar redes de agentes multimodales especializados** (texto, código, visión, audio, imagen, vídeo y ejecución de herramientas).

---

## 2. Documentos de esta carpeta

| Documento | Contenido principal |
|---|---|
| [01 · Aprendizaje adaptativo local](01_aprendizaje_adaptativo_local.md) | Revisión crítica de la propuesta inicial (RAG vs. QLoRA vs. memoria procedimental), escalera de aprendizaje sectorizada por hardware (`L0`–`L3`), arquitectura del *Adaptive Learning Engine*, puente `GGUF ↔ Safetensors`, Multi-LoRA, privacidad/RGPD y experimento piloto. |
| [02 · Arquitectura multimodelo y red de agentes](02_arquitectura_multimodelo_y_red_agentes.md) | Evolución de GuarIdA desde un enfoque centrado en *coder* hacia un núcleo agnóstico con verticales, transición de `RolAgente` a Registro de Capacidades, catálogo de motores offline ligeros, *swapping* de memoria, Multi-LoRA y evolución de `MensajeInterModelo`. |

---

## 3. Piezas ya existentes en GuarIdA que sirven de cimiento

Lejos de empezar de cero, buena parte de la infraestructura necesaria para esta visión futura ya existe en el búnker:

| Capacidad necesaria en el futuro | Pieza actual en GuarIdA | Qué aporta hoy y qué faltaría |
|---|---|---|
| Conocimiento exacto del hardware | [hardware.py](../../app/guarida_manager/hardware.py), [memory_probe.py](../../app/guarida_manager/memory_probe.py) | Detecta CPU, RAM, VRAM/GTT y valida límites reales con prueba de estrés. Permite decidir qué nivel de aprendizaje (`L0`–`L3`) y qué agentes caben en memoria. |
| Perfilado empírico de rendimiento | [tuning/](../../app/guarida_manager/tuning/__init__.py) | Encuentra el *Punto Dulce* por máquina y lo guarda en SQLite (`configuraciones_optimas`). Base directa para el futuro planificador de recursos. |
| Perfiles de hardware y motores enchufables | [02_protocolo_benchmark.md](https://github.com/Ydalgo/GuarIdA/blob/estudio/motores-inferencia/docs/estudio_inferencia/02_protocolo_benchmark.md), [Estudio de inferencia](https://github.com/Ydalgo/GuarIdA/blob/estudio/motores-inferencia/docs/estudio_inferencia/README.md) | Define Perfiles **A, B, C, D** y el nivel de adopción **N2** (motores alternativos intercambiables tras API local). |
| Memoria declarativa inmutable | [cache.py](../../app/guarida_manager/cache.py), `sesiones_chat.db` (`hechos_proyecto`) | Ya soporta hechos con estado `activo` / `superseded` y trazabilidad de origen ([ADR 0012](../adr/0012-arquitectura-persistencia-grafo-ast-y-vlm.md)). Base del nivel `L0` de aprendizaje sin pesos. |
| Memoria documental y grafo de conocimiento | [proyectos.py](../../app/guarida_manager/proyectos.py), [arbol_nodos.py](../../app/guarida_manager/arbol_nodos.py) | Indexación incremental por SHA-256, búsqueda híbrida y grafo AST en `proyecto_grafo.db`. Detecta exactamente qué archivos cambian. |
| Privacidad y sanitización | [sanitizer.py](../../app/guarida_manager/security/sanitizer.py) | Delimitadores `<private>...</private>`, filtros de secretos y modo `rgpd_estricto`. Imprescindible para no contaminar datasets ni pesos. |
| Inspección de pesos nativos | [tensors_engine.py](../../app/guarida_manager/engine/tensors_engine.py) | Ya inspecciona `.safetensors` sin cargar todos los pesos en RAM. Punto de partida para validar modelos base entrenables. |
| Protocolo inter-agente | [roles.py](../../app/guarida_manager/roles.py) (`RolAgente`, `MensajeInterModelo`) | Define mensajes JSON tipados entre roles. Requiere generalizarse de 4 roles fijos a capacidades y referencias a artefactos. |
| Interoperabilidad externa | [mcp/server.py](../../app/guarida_manager/mcp/server.py) | Expone memoria y grafo AST vía MCP `stdio`. Permite conectar herramientas y agentes externos de forma controlada. |
| Operación en red local | [Iniciar_Servicio.bat](../../Iniciar_Servicio.bat) | Expone el servicio en LAN (`0.0.0.0:8080`), útil a futuro para delegar entrenamientos pesados a un nodo local potente (`L3`). |

---

## 4. Disciplina de alcance: qué preparar ya y qué NO hacer todavía

GuarIdA ya aprendió en su etapa previa con KoboldCpp (documentado en [README.md](../../README.md)) el riesgo de dispersar esfuerzos antes de consolidar la base. Por ello, esta documentación sigue una regla estricta de contención:

### Qué NO hacer todavía
- **No meter PyTorch, CUDA, `bitsandbytes` ni `transformers` en el paquete portable actual:** añadiría entre 2 y 5 GB al `.zip`/`.msi` offline, complicaría el soporte en Windows/APU y chocaría con el objetivo de portabilidad ligera.
- **No construir pipelines de entrenamiento antes de cerrar Fase 3, Fase 4 y el Estudio de Inferencia (F4–F6):** la prioridad inmediata es la orquestación de código en worktrees, el sandboxing del sistema operativo y la optimización del motor de inferencia.
- **No abrir múltiples verticales de golpe:** la programación sigue siendo la vertical principal donde validar toda nueva capacidad.

### Qué SÍ conviene tener en cuenta hoy (coste casi cero)
1. **En F5/F6 del Estudio de Inferencia:** cuando se diseñe la abstracción de motores intercambiables (nivel N2), modelarla como un registro de **capacidades** (`MotorCapacidad` / `text_gen`, `embeddings`, `vision`, `audio_stt`, etc.) en lugar de asumir que todo motor es un `llama-server` de texto.
2. **En `MensajeInterModelo` ([roles.py](../../app/guarida_manager/roles.py)):** mantener el `payload` preparado para transportar **referencias a artefactos locales** (ruta, `mime_type`, `sha256`, etiqueta de privacidad) en lugar de incrustar binarios o textos enormes.
3. **En `sesiones_chat.db`:** conservar señales ligeras de calidad (si una respuesta o parche fue aceptado, corregido o rechazado por el usuario o por tests) y respetar siempre `<private>` / `rgpd_estricto` desde la captura.
