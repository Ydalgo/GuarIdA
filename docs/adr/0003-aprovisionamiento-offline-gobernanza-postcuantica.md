# ADR 0003: Aprovisionamiento Único Offline, Gobernanza Regional (EU AI Act) y Seguridad Postcuántica

## Estado
Aceptado

## Contexto
GuarIdA opera bajo una filosofía de **Búnker Digital**: soberano, privado y 100% offline. Para garantizar que el entorno funcione sin conexión a Internet tras su configuración, se debe realizar un proceso de **aprovisionamiento único** (*one-shot bootstrap*) donde se descargan y verifican todos los componentes requeridos:
1. Binarios nativos de inferencia oficiales de `llama.cpp` ajustados al SO y al backend gráfico detectado (Vulkan o CPU).
2. Dependencias del ecosistema para capacidades complementarias fuera de línea (generación de informes PDF, interfaces web o de escritorio).
3. Modelos de lenguaje en formato GGUF precompilado (sin compilación en local) clasificados por dominio: programación en la etapa actual y modelos generalistas en etapas posteriores.
4. Modelos de vectorización (*embeddings*) indispensables para la navegación de árboles de nodos, grafos sintácticos (AST) y bucles iterativos de programación agéntica.
5. Cifrado integral del almacenamiento local preparado para resistir criptoanálisis postcuántico.
6. Cumplimiento normativo y gobernanza legal según la región del usuario (específicamente la Ley de IA Europea / *EU AI Act* en España/UE).

## Decisiones Arquitectónicas

### 1. Conexión a Internet Restringida a la Ventana de Aprovisionamiento Inicial
* **Decisión:** La conexión a Internet solo se utiliza una vez durante la fase de preparación del búnker. Una vez aprovisionado, el sistema opera con total aislamiento de red.
* **Justificación:** Previene telemetría, filtraciones de código, fugas de propiedad intelectual y ataques a la cadena de suministro en tiempo de ejecución.

### 2. Gobernanza Regional Automatizada y Cumplimiento con el EU AI Act
* **Decisión:** Integrar un motor de evaluación normativa regional (`compliance.py`) que audita cada modelo del catálogo:
  - **Art. 53(1)(d) del Reglamento (UE) 2024/1689 (EU AI Act):** Verificación de publicación del resumen técnico del conjunto de datos de entrenamiento (`training_summary_url`).
  - **Directiva (UE) 2019/790 (Copyright):** Respeto a las reservas de derechos de autor y políticas de exclusión (*TDM opt-out*).
  - **Licencias auditables:** Validación de licencias de código abierto compatibles (Apache-2.0, MIT, etc.).
* **Justificación:** Garantiza que los desarrolladores y autónomos en España y la Unión Europea operen dentro de la legalidad comunitaria vigente sin incurrir en riesgos regulatorios.

### 3. Preservación Inmutable del Histórico en SQLite
* **Decisión:** Si el usuario decide eliminar un archivo `.gguf` del disco para liberar almacenamiento, el registro en la base de datos `guarida.db` no se destruye: se marca como `archivado_sin_archivo` vaciando su ruta física.
* **Justificación:** El búnker nunca olvida las métricas empíricas obtenidas: se conservan permanentemente los benchmarks de velocidad, configuraciones óptimas de capas en GPU (`n_gpu_layers`) y los motivos de descarte técnico o normativo.

### 4. Seguridad y Cifrado Preparado para la Era Postcuántica (PQC-Ready)
* **Decisión:** Proteger la configuración del búnker y los datos locales mediante:
  - Función de derivación de claves (KDF) basada en la función esponja SHAKE-256 (FIPS 202) y SHA3-512 con 256 bits de salt.
  - Cifrado simétrico autenticado (*Encrypt-then-MAC*) con 256 bits de seguridad cuántica (resistente al algoritmo de Grover).
  - Verificación de integridad de binarios y pesos con SHA3-512 y SHA-256.
* **Justificación:** Salvaguardar los datos confidenciales almacenados localmente frente a futuras amenazas criptográficas cuánticas (*harvest now, decrypt later*).

### 5. Inclusión de Modelos de Embeddings para Grafos y Árboles de Nodos
* **Decisión:** El catálogo de aprovisionamiento incluye modelos dedicados de vectorización (e.g. `nomic-embed-text-v1.5` en GGUF) además del modelo generativo.
* **Justificación:** Los futuros roles del agente (Coder, Reviewer, Tester) requieren búsqueda semántica y traversal de nodos en memoria local durante los bucles de iteración de parches.
