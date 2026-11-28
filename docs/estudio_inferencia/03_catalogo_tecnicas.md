# 03 · Catálogo de técnicas

> **Estado:** borrador de F0. Esta es la parte más importante para "coger un poco de muchos": aquí se estudia **cómo** consigue cada proyecto su ventaja, para decidir si en GuarIdA se **integra** el proyecto, se **imita** la técnica o solo se **estudia**. Se completa en F3 leyendo código y documentación.

Los motores no ganan todos con el mismo truco. Hay cuatro familias:

1. **Calcular más barato** (kernels, cuantización, compilación).
2. **Mover menos datos** (KV cuantizada, reparto de expertos, mapeo de memoria).
3. **Dar menos pasos secuenciales** (especulación, MTP, *lookup*).
4. **No volver a calcular lo mismo** (caché de prefijos, reutilización de KV, guardado de estado).

Para un agente de código en hardware modesto, las familias 2, 3 y 4 apuntan a tener más impacto que la 1, porque el cuello de botella habitual es el ancho de banda de memoria y el prefill de contextos largos. **Hipótesis a confirmar en F2/F4.**

Y una regla que conviene no olvidar: **el token más barato es el que no se procesa**. El RAG con AST, la compresión y el control de presupuesto de contexto que GuarIdA ya tiene son también optimización de inferencia.

## Tabla de técnicas

| # | Técnica | Familia | Dónde estudiarla | Encaje en GuarIdA | Nivel | Estado |
|---|---|---|---|---|---|---|
| T1 | Mapeo de pesos sin copias (`mmap`), fijado en RAM (`mlock`), carga rápida | 2 | llm.asm, llama.cpp | Ya disponible (`--mlock`, `--no-mmap`); falta decidir cuándo activarlo según RAM libre | N0 | pendiente |
| T2 | Kernels SIMD especializados (AVX2, AVX-512, VNNI, F16C) | 1 | llm.asm, Herbert-rs, ik_llama.cpp, OpenSet-LLM, Candle | Vía binario sustituto (ik_llama.cpp) o motor alternativo; escribir kernels propios solo en N4 | N1 / N4 | pendiente |
| T3 | Cuantización de pesos: K-quants, IQ/IQK/Trellis, GPTQ/AWQ, INT4 OpenVINO, q4f16 MLC, ternaria, H3G | 1·2 | ik_llama.cpp, HF GPTQ, OpenVINO, MLC, OpenSet-LLM, Golem | Afecta al catálogo de modelos y a la descarga offline (tamaño, 2 GB por archivo en Releases). Cada formato nuevo obliga a duplicar modelos en disco | N1 / N2 | pendiente |
| T4 | KV-cache cuantizada (q8_0 / INT8, q4) | 2 | llama.cpp `-ctk/-ctv`, Herbert-rs | El afinador ya la barre; falta medir su efecto en contexto largo (pruebas E y F) y en la calidad | N0 | pendiente |
| T5 | Atención fusionada / FlashAttention | 1·2 | llama.cpp `-fa`, Herbert-rs, MLC | El afinador ya la barre según capacidades del binario | N0 | pendiente |
| T6 | Reutilización de prefijos y estado: `--cache-reuse`, *slots* guardados (`--slot-save-path`), caché de prefijos, RadixAttention | 4 | SGLang, vLLM, llama.cpp, DynaLM | **Candidata muy fuerte.** Dos ideas concretas: (a) el arnés construye el prompt con prefijo estable (sistema + contexto de proyecto) y lo variable al final; (b) guardar en disco el estado KV del contexto de cada proyecto/sesión y restaurarlo al reabrir, para que el TTFT del primer turno sea casi nulo | N0 + N3 | pendiente |
| T7 | Decodificación especulativa con modelo borrador | 3 | llama.cpp `-md`, DynaLM, ik_llama.cpp | Qwen3-0.6B como borrador de Qwen3-4B/8B (misma familia y tokenizador). Ya soportado en `LlamaServerConfig`, no explorado por el afinador | N0 | pendiente |
| T8 | EAGLE-3 / MTP (cabezas de predicción multitoken) | 3 | DynaLM, ik_llama.cpp, Handbook | Depende de que existan cabezas entrenadas para el modelo elegido | N1 / N2 | pendiente |
| T9 | *Lookup* / n-gram (*prompt lookup decoding*) | 3 | llama.cpp `--lookup-cache`, Handbook | Muy prometedora para edición de código (prueba G). Ya soportada, no explorada | N0 | pendiente |
| T10 | Reparto de expertos MoE entre RAM y VRAM, caché de expertos | 2 | KTransformers, FastLLM, ik_llama.cpp, Ghost Infer, llama.cpp `-ot` / `--n-cpu-moe` | Abre modelos de 30B-A3B en equipos de 8 GB VRAM o en APU. `-ot` y `--n-cpu-moe` ya están en la lista blanca; falta que el afinador sepa usarlos | N0 / N1 | pendiente |
| T11 | Separar prefill y decode por dispositivo (p. ej. prefill en GPU/iGPU, decode donde rinda más) | 2 | KTransformers, Handbook | Interesante en APU; probablemente requiere motor propio o alternativo | N2 / N4 | pendiente |
| T12 | Compilación del grafo por dispositivo (TVM, IR de OpenVINO) | 1 | MLC LLM, OpenVINO | Motor alternativo por perfil (Intel → OpenVINO; Vulkan → MLC) | N2 | pendiente |
| T13 | Especialización por modelo / megakernel persistente | 1 | llm.asm, Megakernel Zoo | Solo estudio. La metodología de Megakernel Zoo (agentes que optimizan y verifican contra referencia FP64) es aplicable al propio afinador de GuarIdA | N4 | pendiente |
| T14 | PagedAttention / KV por bloques | 2 | vLLM, DynaLM | Útil sobre todo con varias peticiones a la vez (modo servicio LAN) | N2 / N3 | pendiente |
| T15 | *Continuous batching* y planificación de peticiones | — | vLLM, SGLang, mistral.rs | Solo relevante si el modo servicio atiende a varios usuarios o varios agentes en paralelo | N2 | pendiente |
| T16 | Separación servidor / motor / pipeline de modelo | — | mistral.rs, DynaLM, Candle | Inspiración para la interfaz de motores intercambiables de F6 | N3 | pendiente |
| T17 | Gestión de contexto en el arnés (RAG preciso, compresión, presupuesto de tokens) | 4 | GuarIdA (ADR 0009, 0010), Handbook | Ya existe; medir cuántos tokens se ahorran y cruzarlo con T6 | N0 | pendiente |

## Plantilla de ficha técnica (F3)

```markdown
### T<n> · <Técnica>
- Qué problema resuelve y en qué fase (prefill / decode / carga / memoria):
- Cómo funciona (resumen propio, con referencia al código o documento leído):
- Proyectos donde se ha estudiado (archivo/función concreta si aplica):
- Requisitos (modelo, hardware, formato, backend):
- Coste o riesgo (calidad, memoria extra, complejidad, licencia):
- Prueba del protocolo que la mide:
- Encaje en GuarIdA y nivel N0–N4:
- Decisión: integrar / imitar / solo estudiar / descartar (motivo):
```

## Ideas abiertas para F5/F6 (no decididas)

- **Interfaz de motores** (`MotorInferencia`): `arrancar`, `detener`, `salud`, `capacidades`, `chat`, `completar`, `tokenizar`, `embeddings`, `guardar_estado`/`restaurar_estado`. `llama-server` sería la primera implementación; las demás solo si superan F4.
- **Afinador multimotor:** el `tuning/` actual ya decide flags por hardware y lo guarda en SQLite; extenderlo para que también elija **motor y estrategia** (especulación, reparto MoE, KV) y lo mida con las pruebas F y G, no solo con una petición aislada.
- **AdaptiveLLM** como evolución natural de esa capa, no como motor monolítico escrito desde cero: primero planificador por capas/bloques/expertos apoyado en motores existentes, kernels propios solo donde haya evidencia.
