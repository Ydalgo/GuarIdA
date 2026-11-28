"""Runner reproducible y reanudable para benchmarks de Fase 2 y Fase 4 del estudio de inferencia."""

from __future__ import annotations

import argparse
import ast
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Optional


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            bloque = f.read(8 * 1024 * 1024)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def _puerto_libre(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _ram_pico_proceso_mb(pid: int) -> Optional[float]:
    """Obtiene el pico de Working Set (MB) del proceso dado en Windows o Linux."""
    if platform.system() == "Windows":
        try:
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return None
            try:
                pmc = PROCESS_MEMORY_COUNTERS()
                pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                    return round(pmc.PeakWorkingSetSize / (1024 * 1024), 2)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return None
    else:
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^VmHWM:\s+(\d+)\s+kB", status, re.MULTILINE)
            if m:
                return round(int(m.group(1)) / 1024.0, 2)
        except Exception:
            return None
    return None


def _hash_hardware_guarida() -> str:
    try:
        raiz = Path(__file__).resolve().parents[1]
        app_dir = str(raiz / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        from guarida_manager.hardware import obtener_informacion_hardware
        return obtener_informacion_hardware().hash_hardware
    except Exception:
        return "desconocido"


def _esperar_salud(base_url: str, proc: subprocess.Popen[bytes], timeout_s: float = 120.0) -> float:
    t0 = time.perf_counter()
    deadline = t0 + timeout_s
    while time.perf_counter() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server terminó prematuramente (exit={proc.returncode})")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    if data.get("status") == "ok":
                        return (time.perf_counter() - t0) * 1000.0
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"llama-server no estuvo listo tras {timeout_s}s")


def _post_json(url: str, payload: Optional[dict[str, Any]] = None, timeout_s: float = 120.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}


def _chat_stream(
    base_url: str,
    mensajes: list[dict[str, str]],
    max_tokens: int,
    id_slot: Optional[int] = None,
    cache_prompt: Optional[bool] = None,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messages": mensajes,
        "temperature": 0.0,
        "seed": 42,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if id_slot is not None:
        payload["id_slot"] = id_slot
    if cache_prompt is not None:
        payload["cache_prompt"] = cache_prompt

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t_inicio = time.perf_counter()
    t_primer_token: Optional[float] = None
    tiempos_tokens: list[float] = []
    partes_texto: list[str] = []
    usage: dict[str, Any] = {}
    timings: dict[str, Any] = {}

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw_line in resp:
            linea = raw_line.decode("utf-8", errors="replace").strip()
            if not linea.startswith("data:"):
                continue
            cuerpo = linea[5:].strip()
            if not cuerpo or cuerpo == "[DONE]":
                continue
            try:
                ev = json.loads(cuerpo)
            except json.JSONDecodeError:
                continue
            if isinstance(ev.get("usage"), dict) and ev["usage"]:
                usage = ev["usage"]
            if isinstance(ev.get("timings"), dict) and ev["timings"]:
                timings = ev["timings"]
            choices = ev.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                txt = delta.get("content") or delta.get("reasoning_content") or ""
                if txt:
                    ahora = time.perf_counter()
                    if t_primer_token is None:
                        t_primer_token = ahora
                    else:
                        tiempos_tokens.append(ahora)
                    partes_texto.append(txt)

    t_fin = time.perf_counter()
    latencia_total_ms = (t_fin - t_inicio) * 1000.0
    ttft_ms = ((t_primer_token - t_inicio) * 1000.0) if t_primer_token else latencia_total_ms
    itls_ms = [
        (tiempos_tokens[i] - (tiempos_tokens[i - 1] if i > 0 else t_primer_token)) * 1000.0
        for i in range(len(tiempos_tokens))
        if t_primer_token is not None
    ]
    itl_p50 = statistics.median(itls_ms) if itls_ms else None
    itl_p99 = sorted(itls_ms)[min(len(itls_ms) - 1, int(0.99 * len(itls_ms)))] if itls_ms else None

    texto = "".join(partes_texto)
    tok_in = timings.get("prompt_n") or usage.get("prompt_tokens")
    tok_out = timings.get("predicted_n") or usage.get("completion_tokens")
    tok_cache = timings.get("cache_n")
    pp_tps = timings.get("prompt_per_second")
    tg_tps = timings.get("predicted_per_second")

    if pp_tps is None and tok_in and ttft_ms > 0:
        pp_tps = round(tok_in / (ttft_ms / 1000.0), 2)
    if tg_tps is None and tok_out and (latencia_total_ms - ttft_ms) > 0:
        tg_tps = round(tok_out / ((latencia_total_ms - ttft_ms) / 1000.0), 2)

    return {
        "texto": texto,
        "hash_salida": hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16],
        "tokens_entrada": tok_in,
        "tokens_salida": tok_out,
        "tokens_reutilizados": tok_cache,
        "ttft_ms": round(ttft_ms, 2),
        "itl_p50_ms": round(itl_p50, 2) if itl_p50 is not None else None,
        "itl_p99_ms": round(itl_p99, 2) if itl_p99 is not None else None,
        "latencia_total_ms": round(latencia_total_ms, 2),
        "prefill_tps": round(float(pp_tps), 2) if pp_tps is not None else None,
        "decode_tps": round(float(tg_tps), 2) if tg_tps is not None else None,
    }


def _evaluar_calidad(caso: dict[str, Any], texto: str) -> str:
    limpio = texto.strip()
    if limpio.startswith("```"):
        lineas = limpio.splitlines()
        if len(lineas) >= 3:
            limpio = "\n".join(lineas[1:-1]).strip()
    if caso["tipo"] == "json":
        try:
            obj = json.loads(limpio)
            if isinstance(obj, dict) and all(k in obj for k in caso["claves_requeridas"]):
                return "ok"
            return "fail_schema"
        except Exception:
            return "fail_json"
    if caso["tipo"] == "python_ast":
        try:
            tree = ast.parse(limpio)
            nombres = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            return "ok" if caso["funcion_requerida"] in nombres else "fail_func"
        except SyntaxError:
            return "fail_syntax"
    return "ok"


def _detectar_backend_real(log_texto: str, n_gpu_layers: int) -> str:
    if n_gpu_layers == 0:
        return "CPU"
    low = log_texto.lower()
    if "vulkan" in low or "offloaded" in low:
        return "Vulkan"
    if "cuda" in low:
        return "CUDA"
    return "CPU/Auto"


def _definir_experimentos(slot_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        "N0-Base": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-fa", "off", "-ctk", "f16", "-ctv", "f16"],
            "n_gpu_layers": 33,
            "id_slot": None,
            "cache_prompt": None,
            "pruebas": ["A", "B", "C", "F_actual", "G", "Q"],
        },
        "N0-1": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "off", "-ctk", "f16", "-ctv", "f16", "--cache-reuse", "256"],
            "n_gpu_layers": 33,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["F_estable", "B", "Q"],
        },
        "N0-2": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-lm", "none", "--cache-reuse", "256"],
            "n_gpu_layers": 33,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["A", "B", "C", "F_estable", "G", "Q"],
        },
        "N0-2b": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q4_0", "-lm", "none", "--cache-reuse", "256"],
            "n_gpu_layers": 33,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["B", "C", "G", "Q"],
        },
        "N0-3": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-lm", "none", "--cache-reuse", "256", "--spec-type", "ngram-mod"],
            "n_gpu_layers": 33,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["C", "G", "F_estable", "Q"],
        },
        "N0-4": {
            "flags": ["-ngl", "33", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-lm", "none", "--cache-reuse", "256", "--slot-save-path", str(slot_dir)],
            "n_gpu_layers": 33,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["SLOT_SAVE_RESTORE"],
        },
        "N0-CPU": {
            "flags": ["-ngl", "0", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-lm", "none", "--cache-reuse", "256"],
            "n_gpu_layers": 0,
            "id_slot": 0,
            "cache_prompt": True,
            "pruebas": ["B", "C", "G", "Q"],
        },
    }


def _cargar_claves_existentes(ruta_jsonl: Path) -> set[tuple[str, str, int, int]]:
    hechas: set[tuple[str, str, int, int]] = set()
    if not ruta_jsonl.exists():
        return hechas
    for linea in ruta_jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            reg = json.loads(linea)
            if reg.get("error") is None:
                hechas.add((reg["experimento"], reg["prueba"], int(reg.get("turno", 0)), int(reg.get("repeticion", 0))))
        except Exception:
            continue
    return hechas


def _construir_mensajes_f(f_data: dict[str, Any], modo: str, turno_idx: int, historial: list[dict[str, str]]) -> list[dict[str, str]]:
    pregunta = f_data["turnos"][turno_idx]
    if modo == "F_actual":
        n_archivos = 20 if turno_idx < 2 else 21  # simula reindexación de 1 archivo en turno 3
        sys_txt = f_data["sistema_base"].replace(
            "[PROYECTO ACTIVO]: 'repositorio_estudio'.",
            f"[PROYECTO ACTIVO]: 'repositorio_estudio' ({n_archivos} archivos indexados).",
        )
        msgs = [{"role": "system", "content": sys_txt}] + list(historial)
        msgs.append({"role": "user", "content": f"{pregunta}\n\n{f_data['hechos_canonicos']}"})
        return msgs
    # F_estable: sistema inmutable + bloque canónico fijo tras sistema + historial + pregunta limpia
    msgs = [
        {"role": "system", "content": f_data["sistema_base"]},
        {"role": "user", "content": f_data["hechos_canonicos"]},
        {"role": "assistant", "content": "Entendido, mantendré esas reglas durante toda la sesión."},
    ] + list(historial)
    msgs.append({"role": "user", "content": pregunta})
    return msgs


def _imprimir_resumen(ruta_jsonl: Path) -> None:
    filas = [json.loads(l) for l in ruta_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    grupos: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for r in filas:
        if r.get("repeticion", 0) == 0 or r.get("error") is not None:
            continue
        k = (r["experimento"], r["prueba"], int(r.get("turno", 0)))
        grupos.setdefault(k, []).append(r)

    print("| Experimento | Prueba | Turno | Backend | TTFT ms | Prefill t/s | Decode t/s | Cache tok | RAM pico MB | Calidad |")
    print("|---|---|---:|---|---:|---:|---:|---:|---:|---|")
    for (exp, pr, tr), items in sorted(grupos.items()):
        med = lambda c: round(statistics.median([x[c] for x in items if x.get(c) is not None]), 2) if any(x.get(c) is not None for x in items) else None
        cal = ",".join(sorted({str(x.get("calidad")) for x in items if x.get("calidad")}))
        print(f"| {exp} | {pr} | {tr} | {items[0].get('backend_real')} | {med('ttft_ms')} | {med('prefill_tps')} | {med('decode_tps')} | {med('tokens_reutilizados')} | {med('ram_pico_mb')} | {cal or '-'} |")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark reproducible F2/F4 de GuarIdA.")
    parser.add_argument("--llama-server", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--prompts-dir", type=Path, default=Path("docs/estudio_inferencia/resultados/prompts"))
    parser.add_argument("--salida", type=Path, default=Path("docs/estudio_inferencia/resultados/2026-11-28_731271e2_llama-b12017.jsonl"))
    parser.add_argument("--experimentos", default="all", help="Lista separada por comas o 'all'")
    parser.add_argument("--repeticiones", type=int, default=3)
    parser.add_argument("--reanudar", action="store_true")
    parser.add_argument("--resumen", type=Path, help="Imprime tabla Markdown de un JSONL existente y sale")
    args = parser.parse_args()

    if args.resumen:
        _imprimir_resumen(args.resumen)
        return 0

    if not args.llama_server or not args.model:
        parser.error("--llama-server y --model son obligatorios salvo con --resumen")

    srv_bin = args.llama_server.resolve()
    modelo_path = args.model.resolve()
    if not srv_bin.is_file() or not modelo_path.is_file():
        raise FileNotFoundError("No existe el binario de llama-server o el modelo indicado")

    ver_proc = subprocess.run([str(srv_bin), "--version"], capture_output=True, text=True, check=False)
    version_motor = " ".join((ver_proc.stdout or ver_proc.stderr).splitlines()[:2]).strip()
    sha_modelo = _sha256_archivo(modelo_path)
    hash_hw = _hash_hardware_guarida()

    prompts = {
        "A": json.loads((args.prompts_dir / "A_latencia.json").read_text(encoding="utf-8")),
        "B": json.loads((args.prompts_dir / "B_mixta.json").read_text(encoding="utf-8")),
        "C": json.loads((args.prompts_dir / "C_sostenida.json").read_text(encoding="utf-8")),
        "F": json.loads((args.prompts_dir / "F_agente_multiturno.json").read_text(encoding="utf-8")),
        "G": json.loads((args.prompts_dir / "G_edicion_codigo.json").read_text(encoding="utf-8")),
        "Q": json.loads((args.prompts_dir / "Q_calidad.json").read_text(encoding="utf-8")),
    }

    hechas = _cargar_claves_existentes(args.salida) if args.reanudar else set()
    args.salida.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="guarida_f2_slots_") as tmp_slots:
        slot_dir = Path(tmp_slots)
        catalogo_exp = _definir_experimentos(slot_dir)
        seleccion = list(catalogo_exp.keys()) if args.experimentos == "all" else [e.strip() for e in args.experimentos.split(",") if e.strip()]

        with open(args.salida, "a" if args.reanudar else "w", encoding="utf-8") as f_out:
            def registrar(reg: dict[str, Any]) -> None:
                f_out.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f_out.flush()

            for exp_id in seleccion:
                cfg = catalogo_exp[exp_id]
                # Comprobar si todo el experimento ya estaba hecho en modo reanudar
                if args.reanudar:
                    pendiente = False
                    for pr in cfg["pruebas"]:
                        if pr in ("F_actual", "F_estable"):
                            for r in range(1, args.repeticiones + 1):
                                for t in range(1, len(prompts["F"]["turnos"]) + 1):
                                    if (exp_id, pr, t, r) not in hechas:
                                        pendiente = True
                        elif pr == "Q":
                            for c_idx in range(1, len(prompts["Q"]["casos"]) + 1):
                                if (exp_id, "Q", c_idx, 1) not in hechas:
                                    pendiente = True
                        elif pr == "SLOT_SAVE_RESTORE":
                            for r in range(1, args.repeticiones + 1):
                                if (exp_id, "SLOT_SAVE_RESTORE", 1, r) not in hechas:
                                    pendiente = True
                        else:
                            for r in range(1, args.repeticiones + 1):
                                if (exp_id, pr, 1, r) not in hechas:
                                    pendiente = True
                    if not pendiente:
                        print(f"[SKIP] {exp_id} ya completo en {args.salida}")
                        continue

                puerto = _puerto_libre()
                base_url = f"http://127.0.0.1:{puerto}"
                log_stderr = Path(tmp_slots) / f"{exp_id}.stderr.log"
                cmd = [str(srv_bin), "-m", str(modelo_path), "--host", "127.0.0.1", "--port", str(puerto), "--no-webui"] + cfg["flags"]
                print(f"[RUN] {exp_id} en {base_url} -> {' '.join(cfg['flags'])}")

                with open(log_stderr, "wb") as f_err:
                    proc = subprocess.Popen(cmd, stdout=f_err, stderr=subprocess.STDOUT)
                try:
                    startup_ms = _esperar_salud(base_url, proc, timeout_s=120.0)
                    txt_err = log_stderr.read_text(encoding="utf-8", errors="replace")
                    backend_real = _detectar_backend_real(txt_err, cfg["n_gpu_layers"])

                    # Warmup corto (repeticion=0)
                    _chat_stream(base_url, prompts["A"]["mensajes"], max_tokens=16, id_slot=cfg["id_slot"], cache_prompt=cfg["cache_prompt"])

                    def base_reg(prueba: str, turno: int, rep: int) -> dict[str, Any]:
                        return {
                            "origen": "medido",
                            "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                            "hash_hardware": hash_hw,
                            "perfil": "B",
                            "experimento": exp_id,
                            "motor": "llama.cpp",
                            "version_motor": version_motor,
                            "backend_real": backend_real,
                            "flags": cfg["flags"],
                            "modelo": modelo_path.name,
                            "sha256_modelo": sha_modelo,
                            "startup_ms": round(startup_ms, 2),
                            "prueba": prueba,
                            "turno": turno,
                            "repeticion": rep,
                            "ram_pico_mb": _ram_pico_proceso_mb(proc.pid),
                            "error": None,
                        }

                    for pr in cfg["pruebas"]:
                        if pr in ("A", "B", "C", "G"):
                            pdata = prompts[pr]
                            for rep in range(1, args.repeticiones + 1):
                                if (exp_id, pr, 1, rep) in hechas:
                                    continue
                                res = _chat_stream(base_url, pdata["mensajes"], pdata["max_tokens"], id_slot=cfg["id_slot"], cache_prompt=cfg["cache_prompt"])
                                reg = base_reg(pr, 1, rep)
                                reg.update({k: v for k, v in res.items() if k != "texto"})
                                registrar(reg)
                        elif pr == "Q":
                            for idx, caso in enumerate(prompts["Q"]["casos"], start=1):
                                if (exp_id, "Q", idx, 1) in hechas:
                                    continue
                                res = _chat_stream(base_url, caso["mensajes"], prompts["Q"]["max_tokens"], id_slot=cfg["id_slot"], cache_prompt=False)
                                reg = base_reg("Q", idx, 1)
                                reg.update({k: v for k, v in res.items() if k != "texto"})
                                reg["calidad"] = f"{caso['id']}:{_evaluar_calidad(caso, res['texto'])}"
                                registrar(reg)
                        elif pr in ("F_actual", "F_estable"):
                            fdata = prompts["F"]
                            for rep in range(1, args.repeticiones + 1):
                                historial: list[dict[str, str]] = []
                                for t_idx, pregunta in enumerate(fdata["turnos"]):
                                    turno_num = t_idx + 1
                                    msgs = _construir_mensajes_f(fdata, pr, t_idx, historial)
                                    res = _chat_stream(base_url, msgs, fdata["max_tokens"], id_slot=cfg["id_slot"], cache_prompt=cfg["cache_prompt"])
                                    if (exp_id, pr, turno_num, rep) not in hechas:
                                        reg = base_reg(pr, turno_num, rep)
                                        reg.update({k: v for k, v in res.items() if k != "texto"})
                                        registrar(reg)
                                    historial.append({"role": "user", "content": pregunta})
                                    historial.append({"role": "assistant", "content": res["texto"]})
                        elif pr == "SLOT_SAVE_RESTORE":
                            fdata = prompts["F"]
                            for rep in range(1, args.repeticiones + 1):
                                if (exp_id, pr, 1, rep) in hechas:
                                    continue
                                msgs_t1 = _construir_mensajes_f(fdata, "F_estable", 0, [])
                                r1 = _chat_stream(base_url, msgs_t1, fdata["max_tokens"], id_slot=0, cache_prompt=True)
                                fname = f"slot_f2_r{rep}.bin"
                                r_save = _post_json(f"{base_url}/slots/0?action=save", {"filename": fname})
                                _post_json(f"{base_url}/slots/0?action=erase", {})
                                r_rest = _post_json(f"{base_url}/slots/0?action=restore", {"filename": fname})
                                hist = [{"role": "user", "content": fdata["turnos"][0]}, {"role": "assistant", "content": r1["texto"]}]
                                msgs_t2 = _construir_mensajes_f(fdata, "F_estable", 1, hist)
                                r2 = _chat_stream(base_url, msgs_t2, fdata["max_tokens"], id_slot=0, cache_prompt=True)
                                fsize_mb = round((slot_dir / fname).stat().st_size / (1024 * 1024), 2) if (slot_dir / fname).exists() else None
                                reg = base_reg(pr, 1, rep)
                                reg.update({k: v for k, v in r2.items() if k != "texto"})
                                reg["save_ms"] = r_save.get("timings", {}).get("save_ms")
                                reg["restore_ms"] = r_rest.get("timings", {}).get("restore_ms")
                                reg["slot_file_mb"] = fsize_mb
                                registrar(reg)
                except Exception as exc:
                    registrar({
                        "origen": "medido",
                        "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                        "hash_hardware": hash_hw,
                        "experimento": exp_id,
                        "prueba": "ERROR",
                        "turno": 0,
                        "repeticion": 0,
                        "error": str(exc),
                    })
                    print(f"[ERR] {exp_id}: {exc}")
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)

    print(f"[DONE] Resultados guardados en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
