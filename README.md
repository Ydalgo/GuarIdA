# GuarIdA

**IA local offline para desarrollo.** Un agente de programación que corre en tu máquina, sin internet, sin telemetría, con permisos por rol aplicados fuera del modelo.

## De donde viene el proyecto
El proyecto nace de otro similar [KoboldCpp](https://github.com/Ydalgo/KoboldCpp-IDE/) que lo he dejado en Stand-By porque me estaba centrando mucho en el interfaz y dejando de lado la parte más básica, por lo que decido dejarlo aparcado y volver al punto 0 con la experiencia ya adquirida.

El problema que tenemos actualmente es que la IA tras varios años se ha democratizado, creo que con un éxito muy grande, sin embargo conforme todo ha ido evolucionando y expandiéndose tanto en potencia, conocimiento, han surgido nuevos problemas, problemas que vienen sobretodo en un déficit de stock y una subida de precios en memoria RAM, discos NVME de quinta generación y sobretodo en GPUs capaces de correr IAs con soltura, por lo tanto aunque cualquier usuario doméstico o los pequeños empresario y autónomos pueden fácilmente utilizar IA por Internet, esto hace que perdamos el control y la privacidad,y este no es un problema menor.

Entonces este proyecto en concreto GuarIdA, con un nombre que de primeras parece no compartir y ocultarse debe explorarse con vista más amplia, una guarida es un sitio normalmente protegido, una guarida puede ser cualquier cosa, en nuestro caso cualquier Hardware domestico, con sus gráficas integradas, quizás luego madure de otra manera el proyecto, pero en principio esta basado en los ordenadores modernos que pueden comprarse o que con una pequeña ampliación puedan usarse para IA Local y Offline, porque nadie debe porque saber que pasa en nuestra guarida, que documentos compartimos ni que se habla en ella. 

GuarIdA, no nace con intención de ser un software, ni de ser un asistente en la Nube, en un primer momento van a ser una serie de programas y configuraciones para intentar democratizar las IAs locales offline en Hardware modesto. Quizás tarde, pero lo tendremos tarde y controlado. Quizás es lento, pero es nuestro lento, debemos llegar a obtener un producto aunque lento que sea eficaz.

El primer enfoque que va a tener va a ser dedicado a la programación, cualquier modelo basado en la Nube por supuesto va a tener mejores resultados y mucho más rápido, no es mi deseo competir en esos parámetros, solo quiero competir en seguridad, privacidad, capacidad de usarse en cualquier situación, aun cuando no tengamos conexión, solo necesitaremos nuestra Sistema Operativo, el Hardware y un punto de luz que alimente ese PC modesto.

El momento actual en el que se encuentra la Primera fase.

## 🧠 Stack actual (Fase 1 cerrada)
- **Backend de inferencia:** `llama-server` con Vulkan (build `b11707`), servicio systemd de usuario en el puerto `8083`.
- ***Se han estando comparando ollama, lmstudio, koboldcpp, y aunque koboldcpp dió un excelente resultado en contexto largo era más lento.
- **Modelo:** `Qwen2.5-Coder-32k` (GGUF, cuantización Q4).
- ***Se selecciona este porque es el más adecuado para el Hardware con el que inicializo el proyecto.
- **Contexto:** 16 384 tokens. **Atención:** el GTT de la APU está al ~93 % con esta configuración; no se sube a 32k sin reducir `--n-gpu-layers` o el KV cache.
- **KoboldCpp** (puerto `5001`) se mantiene solo como referencia, no como backend del stack.

