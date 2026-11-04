# ADR 0004: Arquitectura Multi-Rol Especializada, Aprovisionamiento Flexible y Comparador de Cuantizaciones

## Estado
Aceptado

## Contexto
Durante el aprovisionamiento inicial (único momento en que el Búnker GuarIdA se conecta a Internet), limitar la elección a un modelo único o imponer restricciones normativas rígidas contradice la necesidad real del desarrollador:
1. **Separación de responsabilidades y lenguaje:** Un modelo de programación puro no debe gastar tokens ni memoria de contexto en mantener una conversación extensa con el usuario. Es preferible un modelo ligero con alta fluidez en español (Chat) que entienda la intención del usuario y la traduzca en especificaciones técnicas estructuradas para el modelo de código (Coder).
2. **Navegación de árboles sintácticos y grafos:** Las iteraciones en código y la búsqueda de nodos en árboles sintácticos (AST) requieren un modelo de embeddings multilingüe optimizado (ej. BGE-M3 o Nomic Embed).
3. **Libertad de investigación y modelos sin censura:** Para tareas como análisis de vulnerabilidades, auditoría de seguridad o ingeniería inversa, los modelos con filtros éticos restrictivos comerciales rechazan solicitudes legítimas de análisis. El usuario debe poder descargar modelos desalineados (*abliterated* o sin censura) bajo la exención de I+D personal.
4. **Experimentación de cuantizaciones y contexto:** En hardware modesto o con memoria compartida (APUs/iGPUs), el desarrollador necesita descargar varias cuantizaciones (ej. Q3_K_M y Q4_K_M de un 7B) en la misma sesión para medir empíricamente cuál permite alcanzar 32k tokens de contexto sin desbordar la GPU.
5. **Modelos personalizados:** El sistema debe permitir descargar cualquier archivo GGUF de cualquier repositorio de Hugging Face sin estar atado a una lista fija.

## Decisiones Arquitectónicas

### 1. Arquitectura Multi-Rol y Protocolo Inter-Modelo
* **Decisión:** Desacoplar el agente en roles especializados:
  - **Rol Conversacional / Chat:** Fluido en español, empático, traduce requerimientos a especificaciones en formato estructurado (ej. Qwen2.5-3B).
  - **Rol Coder:** Especializado en sintaxis, parches diff y llamadas a herramientas (ej. Qwen2.5-Coder-7B en Q4 o Q3).
  - **Rol Embedding / Indexador:** Especializado en búsqueda vectorial y árboles de nodos para bucles iterativos (ej. BGE-M3).
  - **Protocolo de comunicación:** Formato JSON normalizado (`MensajeInterModelo`) para que los modelos se coordinen de forma determinista sin alucinaciones de formato.

### 2. Gobernanza Informativa No Bloqueante
* **Decisión:** El motor de cumplimiento normativo (EU AI Act) emite dictámenes transparentes sobre riesgos, copyright y licencias, pero **nunca bloquea** la descarga ni la ejecución.
* **Justificación:** El búnker es soberano y de uso privado local. La responsabilidad y el control pertenecen íntegramente al usuario.

### 3. Cesta de Descarga Multirrol en Lote
* **Decisión:** Implementar una cesta de aprovisionamiento que permite seleccionar múltiples modelos en un solo paso, verificando el espacio total en disco antes de comenzar.
* **Justificación:** Asegura que todas las herramientas que el usuario desee probar queden almacenadas en el búnker antes de cortar la conexión a la red.

### 4. Comparador de Cuantizaciones y Memoria de Contexto
* **Decisión:** Incluir un analizador de trade-offs (`comparator.py`) que calcula el consumo de memoria de los pesos sumado a la memoria dinámica de KV Cache para contextos de 4k, 16k y 32k tokens frente a la VRAM/GTT real de la máquina.
* **Justificación:** Permite saber con certeza matemática y empírica si un modelo Q4 desbordará a RAM con 32k tokens o si es preferible operar con un Q3.

### 5. Soporte Universal para Modelos Personalizados
* **Decisión:** Permitir el registro dinámico de cualquier repositorio y archivo GGUF de Hugging Face directamente desde el menú o la API del paquete.
