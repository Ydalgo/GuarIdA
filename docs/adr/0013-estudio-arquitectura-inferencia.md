# ADR 0013: Estudio de la arquitectura de inferencia (motores y técnicas)

* **Estado:** Propuesto
* **Fecha:** 2026-11-28
* **Contexto:** Transversal a las fases 3 y 4 del proyecto. Rama `estudio/motores-inferencia`.

---

## 1. Contexto

GuarIdA depende hoy de un único motor de inferencia, `llama-server` (llama.cpp), gestionado por `engine/server.py` y afinado empíricamente por `tuning/` con persistencia en SQLite (ADR 0006, 0007 y 0010).

Varios proyectos recientes (entre ellos `alesha-pro/llm.asm`, ik_llama.cpp, Ghost Infer, DynaLM, KTransformers, OpenVINO, MLC LLM, Herbert-rs y otros) afirman mejoras importantes en hardware de consumo usando técnicas distintas: kernels especializados, cuantizaciones alternativas, KV-cache cuantizada, decodificación especulativa, reparto de expertos MoE, caché de prefijos o compilación por dispositivo.

La carga real de GuarIdA (agente de código con contextos largos y prefijos repetidos, en APU/iGPU o CPU modesta) no coincide con la de los benchmarks publicados, y muchas de esas cifras no están verificadas.

## 2. Decisión

1. Abrir un **estudio por fases** documentado en [`docs/estudio_inferencia/`](../estudio_inferencia/README.md): F0 encuadre → F1 verificación de fuentes → F2 línea base → F3 técnicas → F4 laboratorio → F5 decisión → F6 prototipo.
2. **Mantener `llama-server` como motor por defecto y línea base** mientras dure el estudio.
3. Evaluar cada hallazgo con un marco de **niveles de adopción** (N0 exprimir lo actual, N1 binario sustituto, N2 motor alternativo enchufable, N3 técnica reimplementada, N4 motor o planificador propio), priorizando los de menor coste.
4. Medir con un **protocolo común** que incluye pruebas específicas de la carga de GuarIdA (agente multiturno con reutilización de prefijo y edición de código) y una **puerta de calidad**.
5. La decisión de adopción se recogerá en un ADR posterior (previsto 0014). Hasta entonces no se fusiona la rama de estudio en `main`.

## 3. Consecuencias

* **Positivas:** decisiones de arquitectura basadas en mediciones propias; posibilidad de combinar técnicas de varios proyectos; continuidad del trabajo entre sesiones y modelos gracias a `TRASPASO.md`.
* **Negativas / riesgos:** coste de tiempo en verificación y medición; posible necesidad de distribuir más de un motor o formato de modelo (tamaño de descargas offline); licencias y soporte de Windows a revisar caso por caso.
* **Neutras:** el código de GuarIdA no cambia en F0; las optimizaciones de nivel N0 pueden adelantarse en ramas derivadas si la línea base (F2) las justifica.
