# 04 · Resultados de Fase 2 · Línea base GuarIdA y experimentos N0

> **Estado:** **Fase 2 cerrada (2026-11-28).** 88 mediciones ejecutadas sin errores sobre hardware doméstico real (Perfil B: APU/iGPU Intel). Datos en bruto: [2026-11-28_731271e2_llama-b12017.jsonl](resultados/2026-11-28_731271e2_llama-b12017.jsonl). Runner reproducible: [bench_estudio_f2.py](../../herramientas/bench_estudio_f2.py).

---

## 1. Entorno medido

- **CPU:** `11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz` (4 núcleos físicos / 8 hilos lógicos).
- **RAM:** `31,64 GB` (`33.971.175.424` bytes).
- **GPU integrada:** `Intel(R) Iris(R) Xe Graphics` (`Vulkan0`, `15,82 GB` GTT compartida).
- **`hash_hardware` GuarIdA:** `731271e2a58e85b04463a945ce07b2827482d386761287eaebdf6b2c18a6dc86`.
- **Motor:** `llama-server` `0.8.0-dev (build 12017, commit 5047748f1)`, Clang 20.1.8 Windows x86_64.
- **Modelo:** `qwen2.5-3b-instruct-q4_k_m.gguf` (`sha256: 626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`).
- **Configuración:** `temperature=0.0`, `seed=42`, 1 *warmup* inicial + **2 repeticiones** por prueba (88 filas totales, 0 errores).
- **Pendiente para F4 / segunda pasada:** `Qwen3-4B/8B`, `N0-5` (`-md` / MoE) y `N0-Up` (`llama.cpp v1.0.0+`) quedan listos para ejecutarse con el mismo script cuando se descarguen esos artefactos.

### Notas metodológicas
1. En el JSONL, `backend_real` quedó registrado como `"CPU/Auto"` en los perfiles GPU porque `b12017` al nivel de log por defecto no imprime `"vulkan"` en stderr; queda verificado que `-ngl 33` corrió en `Vulkan0` tanto por `llama-server --list-devices` como por la diferencia directa frente a `N0-CPU` (`-ngl 0`).
2. En pruebas individuales (`B`, `C`, `G`), la repetición 2 reutilizó parcialmente caché KV de la repetición 1 dentro de la misma instancia del servidor (reflejado en `Cache tok`).

---

## 2. Rendimiento general y comparativa Iris Xe Vulkan vs CPU

Medianas de 2 repeticiones por prueba:

| Experimento | Configuración clave | A · TTFT / Decode | B · TTFT / PP / TG | C · TTFT / PP / TG | G (Código) · TTFT / TG | RAM pico (MB) |
|---|---|---:|---:|---:|---:|---:|
| **`N0-Base`** | Perfil actual (`-ngl 33 -fa off -ctk f16`) | 750 ms / **13,18 t/s** | 5,74 s / **88,5** / **12,44 t/s** | **21,10 s** / **78,9** / **10,23 t/s** | **9,80 s** / 11,36 t/s | 2.790–3.656 |
| **`N0-1`** | `+ T6/T17` (`-tb 8`, `id_slot=0`, `cache_prompt`) | — | 6,40 s / **94,5** / 12,38 t/s | — | — | 2.806–3.092 |
| **`N0-2`** | `+ -fa on -ctk q8_0 -ctv q8_0 -lm none` | **129 ms** / 8,59 t/s | 5,93 s / 83,4 / 8,34 t/s | 33,74 s / 48,2 / 7,46 t/s | 19,54 s / 5,48 t/s | **2.447–2.804** |
| **`N0-2b`** | `+ -fa on -ctk q8_0 -ctv q4_0 -lm none` | — | 6,59 s / 75,8 / 7,24 t/s | 39,83 s / 41,5 / 8,00 t/s | 11,65 s / 8,30 t/s | **2.455–2.613** |
| **`N0-3`** | `N0-2` + **`--spec-type ngram-mod` (T9)** | — | — | 29,32 s / 55,2 / 9,79 t/s | 12,70 s / **46,33 t/s** | 2.555–2.879 |
| **`N0-CPU`** | `-ngl 0 -fa on -ctk q8_0 -ctv q8_0` | — | 6,69 s / 74,9 / 7,71 t/s | 37,20 s / 43,9 / 6,37 t/s | 13,61 s / 6,36 t/s | 2.410–2.643 |

---

## 3. Agente multiturno (`F_actual` vs `F_estable` · T6 + T17)

Simulación de 5 turnos sobre ~5.300–5.600 tokens de contexto. En `F_actual` (`N0-Base`), el turno 3 simula la mutación de `{len(docs_idx)} archivos indexados` en `prompt_sistema` al reindexar un archivo; en `F_estable`, el prefijo es inmutable, `ctx_memoria` va tras el sistema y se fija `id_slot=0` + `cache_prompt=True`.

| Turno | `N0-Base` (`F_actual`) · TTFT / Cache / TG | `N0-1` (`F_estable`) · TTFT / Cache / TG | `N0-2` (`F_estable`) · TTFT / Cache / TG | `N0-3` (`F_estable` + `ngram-mod`) · TTFT / Cache / TG |
|---:|---|---|---|---:|
| **1** | 36.902 ms / 0 tok / 10,57 t/s | 18.718 ms / 2.670 tok / 10,48 t/s | 23.762 ms / 2.670 tok / 8,08 t/s | 24.583 ms / 2.670 tok / **23,03 t/s** |
| **2** | 2.099 ms / 5.244 tok / 10,41 t/s | **702 ms** / 5.396 tok / 10,47 t/s | 998 ms / 5.396 tok / 7,87 t/s | 959 ms / 5.396 tok / **18,42 t/s** |
| **3** | **37.706 ms / 0 tok** / 10,43 t/s | **717 ms / 5.476 tok** / 10,41 t/s | 955 ms / 5.476 tok / 8,08 t/s | 989 ms / 5.476 tok / **23,02 t/s** |
| **4** | 2.164 ms / 5.457 tok / 10,36 t/s | 1.086 ms / 5.577 tok / 10,38 t/s | 1.061 ms / 5.577 tok / 7,61 t/s | 1.029 ms / 5.577 tok / 10,82 t/s |
| **5** | 1.575 ms / 5.584 tok / 10,36 t/s | **729 ms** / 5.629 tok / 10,38 t/s | 1.049 ms / 5.629 tok / 7,76 t/s | 1.016 ms / 5.629 tok / 9,68 t/s |

- **Impacto directo en turno 3:** estabilizar el prefijo reduce el TTFT de **37,71 s a 0,72 s (>52× más rápido)** al evitar recomputar 5.476 tokens de contexto.
- **Impacto en turnos 2–5:** fijar `id_slot=0` y mover `ctx_memoria` al prefijo recorta también el TTFT estable de `1,58–2,16 s` (`N0-Base`) a **`0,70–1,09 s`** (`N0-1`).

---

## 4. Persistencia de slot en disco (`N0-4` · `--slot-save-path`)

Medido tras el turno 1 de `F_estable` (`save` → `erase` → `restore` → turno 2):
- **`save_ms`:** `412,2 – 438,6 ms`.
- **`restore_ms`:** **`48,6 – 56,3 ms`**.
- **Tamaño en disco:** `100,86 MiB`.
- **TTFT turno 2 tras restaurar:** **`1.002,3 – 1.066,4 ms`** con **`5.396` tokens recuperados** (sin re-evaluar el prefill de ~24 s).

---

## 5. Puerta de calidad (`Q`) y paridad greedy

- **`Q_json` y `Q_python`:** **`ok` en los 7 experimentos** (`N0-Base`, `N0-1`, `N0-2`, `N0-2b`, `N0-3`, `N0-CPU`).
- **Paridad greedy en `G` (edición de código):** el hash SHA-256 de la salida generada (`db033baab52666e3`) fue **bit-idéntico en todos los experimentos** (`N0-Base`, `N0-2`, `N0-2b`, `N0-3` y `N0-CPU`), confirmando que **`--spec-type ngram-mod` es 100 % sin pérdida** mientras multiplica la velocidad **4,1×** frente a `N0-Base` (`46,33` vs `11,36 t/s`) y **8,4×** frente a `N0-2` (`46,33` vs `5,48 t/s`).

---

## 6. Conclusiones empíricas de F2

1. **Combo ganador N0 en Iris Xe cuando hay holgura de GTT:** **`N0-1` (`T6+T17`: prefijo estable + `id_slot=0` + `cache_prompt=True` + `-fa off` + KV `f16`) + `--spec-type ngram-mod` (`T9`) + `--slot-save-path` (`N0-4`)**.
2. **Compromiso real de FlashAttention + KV `q8_0` (`N0-2`) en Intel Iris Xe Vulkan:** ahorra **~600–1.000 MB** de RAM/GTT (`2,45–2,80 GB` vs `2,80–3,66 GB`), pero **penaliza el decode ~33 %** (`8,34` vs `12,44 t/s` en `B`; `7,46` vs `10,23 t/s` en `C`) y el prefill largo (`48,2` vs `78,9 t/s`). Debe usarse como **perfil de ahorro de memoria** cuando el modelo/contexto ajuste la GTT, no como valor por defecto cuando sobra memoria.
3. **`Intel Iris Xe` Vulkan compensa frente a CPU:** `N0-Base` Vulkan supera a `N0-CPU` (`12,44` vs `7,71 t/s` en `B`; `11,36` vs `6,36 t/s` en `G`; `10,23` vs `6,37 t/s` en `C`).
4. **Incompatibilidad real detectada en `engine/server.py` frente a `llama-server b12017`:** `b12017` **ya eliminó** `--no-mmap`, `--mlock`, `--draft-max` y `--draft-min` (sustituidos por `-lm/--load-mode`, `--spec-draft-n-max` y `--spec-type`), y depreca `--no-webui` en favor de `--no-ui`. Cuando se pase a implementar los quick-wins de N0 en GuarIdA habrá que actualizar `LlamaServerConfig` y `tuning/capacidades.py`.
