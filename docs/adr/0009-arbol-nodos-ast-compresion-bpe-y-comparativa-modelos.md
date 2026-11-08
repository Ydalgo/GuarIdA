# ADR 0009: Árbol de Nodos AST, Compresión BPE, Búsqueda Híbrida RRF y Comparativa Cara a Cara

* **Estado:** Aceptado e Implementado
* **Fecha:** 2026-11-08
* **Contexto:** Fase 2 / Fase 3 (Motor de Inferencia Local, Afinamiento Empírico y Arnés de Contexto AST)

---

## 1. Contexto y Problema

En hardware doméstico con gráficas integradas (como Intel Iris Xe o AMD Radeon iGPU con memoria compartida GTT), la lectura del prompt (*Prefill / PP*) y el consumo de memoria de la caché KV crecen linealmente con el número de tokens enviados al modelo generativo (`Coder`). Enviar archivos de código fuente completos en cada consulta:
1. Satura la ventana de contexto y el ancho de banda de memoria compartida.
2. Incrementa drásticamente el tiempo hasta el primer token (*TTFT*) y la latencia total.
3. Introduce "ruido" contextual (funciones y clases irrelevantes) que degrada la precisión de modelos cuantizados en 4 bits (`Q4_K_M`).

Además, los modelos codificadores de embeddings puros en formato GGUF (arquitectura BERT/Nomic/Jina/BGE) operan exclusivamente sobre el endpoint `/embedding` y no soportan `/completion`, por lo que requieren coexistir con el servidor generativo sin colisionar en puertos ni agotar la VRAM/GTT.

---

## 2. Decisiones Técnicas Adoptadas

### 2.1. Descomposición en Árbol Sintáctico de Nodos (`ArbolNodosCodigo`)
Se implementa el módulo `guarida_manager/arbol_nodos.py` que analiza código fuente mediante `ast` y lo estructura jerárquicamente en instancias `NodoAST` (`MODULO`, `CLASE`, `FUNCION`, `METODO`):
* Cada nodo conserva su firma exacta, docstring, rango de líneas, relación padre-hijos y huella semántica compacta (`texto_para_embedding`).

### 2.2. Poda de Esqueleto AST y Minificación Consciente de BPE (`minificar_codigo_bpe`)
Para minimizar el número de tokens procesados por el modelo sin perder estructura sintáctica:
* **Esqueleto AST (`construir_contexto_optimo`):** Cuando se recupera un método de una clase, se incluye únicamente la cabecera de la clase (`class Nombre:`) y el cuerpo del método objetivo, omitiendo el resto de métodos hermanos no relacionados.
* **Compresión Sintáctica BPE:** Se eliminan comentarios `#`, docstrings redundantes y líneas en blanco, y se comprime la indentación de 4 espacios a 1 espacio por nivel (reduciendo tokens BPE de espaciado en ~35-50% sin alterar la semántica de Python).

### 2.3. Búsqueda Híbrida RRF (Coseno Vectorial + Símbolos AST) y Caché SHA-256
* **Caché de Embeddings en Memoria (`_CACHE_EMBEDDINGS_AST`):** Los textos se indexan por su hash `SHA-256`. Nodos AST que no han cambiado entre iteraciones reutilizan su vector en `0.0 ms` sin invocar HTTP `/embedding`.
* **Fusión de Rango Recíproco (RRF):** `buscar_nodos_relevantes` combina la similitud coseno densa ($70\%$) con la coincidencia léxica de identificadores técnicos extraídos del AST ($30\%$), garantizando precisión exacta en nombres de funciones, constantes y algoritmos.

### 2.4. Arquitectura Dual de Servidores y Reutilización de KV Cache (`cache_prompt=True`)
* **Doble instancia coordinada:** Durante las pruebas comparativas y la ejecución asistida por AST, se levanta una instancia ligera de `llama-server --embedding` en un puerto dinámico libre en CPU para el modelo vectorial, manteniendo el modelo generativo (`Qwen2.5-Coder` o `Qwen3`) en su puerto principal con su configuración óptima de SQLite.
* **Protección automática contra OOM en Vulkan (`desde_afinamiento`):** Si el tamaño físico del archivo `.gguf` supera la memoria GTT disponible en la GPU integrada (ej. modelos MoE de 30B / 17.7 GB en iGPUs de 8 GB), el sistema asigna automáticamente `-ngl 0 -nkvo` (con autorrecuperación en modo CPU puro `--device none`) para evitar `vk::Device::allocateMemory: ErrorOutOfDeviceMemory`.
* **Persistencia progresiva del Punto Dulce en SQLite:** `BuscadorAfinamientoEtapas` guarda el mejor perfil parcial en `configuraciones_optimas` en cada etapa superada y `obtener_configuracion_optima` incluye respaldo automático sobre `bench_configs`.

---

## 3. Resultados Empíricos Verificados (Intel Core i5-1135G7 + Intel Iris Xe)

Medición real ejecutada sobre `qwen2.5-coder-7b-abliterated-q4` + `nomic-embed-text-v1.5`:

| Métrica | Inferencia Directa (Baseline) | Árbol AST + BPE + KV Cache | Mejora Empírica |
| :--- | :---: | :---: | :---: |
| **Tokens de Prompt** | `629 tokens` | `164 tokens` (`163` en KV Cache, `1` evaluado) | **73.93% ahorro (`3.84x` menos tokens)** |
| **Overhead Búsqueda AST** | N/A | `0.20 ms` (con caché SHA-256) | Despreciable |
| **Velocidad Creación (`TG`)** | `6.55 tok/s` | `6.56 tok/s` | Estable |
| **Latencia Total** | `8363.49 ms` | `3193.02 ms` | **`2.62x` más rápido (-5.17 s)** |
| **Calidad de Respuesta** | `75.0%` | `87.5%` | **+12.5 puntos porcentuales** |

---

## 4. Consecuencias

* **Positivas:** Reducción superior al 70% en consumo de contexto, aceleración >2.5x en hardware modesto sin pérdida de privacidad, mejora en la precisión de respuesta al eliminar ruido del prompt y comparativa directa cara a cara entre familias de modelos (`Qwen2.5` vs `Qwen3`) y motores de embeddings (`Nomic`, `Jina Code`, `Snowflake Arctic`, `MiniLM`, `BGE-M3`).
* **Mantenimiento:** La resolución de descargas en `DescargadorModelos` incluye consulta de respaldo a la API de Hugging Face (`/api/models/{repo}`) para tolerar cambios de nombres de archivos `.gguf` en repositorios comunitarios.
