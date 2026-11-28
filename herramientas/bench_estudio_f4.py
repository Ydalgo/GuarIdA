"""Runner multimotor reproducible y reanudable para Fase 4 (Perfil B · Qwen3-4B Q4_K_M)."""

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
            b = f.read(8 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _puerto_libre(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _ram_pico_proceso_mb(pid: int) -> Optional[float]:
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

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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


def _esperar_http(base_url: str, proc: subprocess.Popen[bytes], timeout_s: float = 180.0) -> tuple[float, str]:
    t0 = time.perf_counter()
    deadline = t0 + timeout_s
    model_id = "default"
    while time.perf_counter() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"servidor terminó prematuramente (exit={proc.returncode})")
        for ep in ("/health", "/v1/models"):
            try:
                with urllib.request.urlopen(f"{base_url}{ep}", timeout=2.0) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8", errors="replace")
                        if ep == "/health":
                            data = json.loads(raw) if raw.strip() else {}
                            if data.get("status") not in (None, "ok"):
                                continue
                            # Intentar leer model_id de /v1/models
                            try:
                                with urllib.request.urlopen(f"{base_url}/v1/models", timeout=2.0) as rm:
                                    md = json.loads(rm.read().decode("utf-8", errors="replace"))
                                    if md.get("data"):
                                        model_id = md["data"][0].get("id") or model_id
                            except Exception:
                                pass
                            return (time.perf_counter() - t0) * 1000.0, model_id
                        else:
                            md = json.loads(raw) if raw.strip() else {}
                            if md.get("data"):
                                model_id = md["data"][0].get("id") or model_id
                            return (time.perf_counter() - t0) * 1000.0, model_id
            except Exception:
                pass
        time.sleep(0.35)
    raise TimeoutError(f"servidor no estuvo listo tras {timeout_s}s")


def _preparar_mensajes(mensajes: list[dict[str, str]]) -> list[dict[str, str]]:
    """Añade /no_think en el último mensaje de usuario para homogeneizar Qwen3 entre motores."""
    copia = [dict(m) for m in mensajes]
    for i in range(len(copia) - 1, -1, -1):
        if copia[i].get("role") == "user":
            if "/no_think" not in copia[i]["content"]:
                copia[i]["content"] = copia[i]["content"] + "\n/no_think"
            break
    return copia


def _chat_stream(
    base_url: str,
    model_id: str,
    mensajes: list[dict[str, str]],
    max_tokens: int,
    id_slot: Optional[int] = None,
    cache_prompt: Optional[bool] = None,
    soporta_seed: bool = True,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": _preparar_mensajes(mensajes),
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if soporta_seed:
        payload["seed"] = 42
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
    tok_out = timings.get("predicted_n") or usage.get("completion_tokens") or (len(tiempos_tokens) + (1 if t_primer_token else 0))
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
    # Quitar bloque <think>...</think> si Qwen3 lo emitiera
    limpio = re.sub(r"<think>.*?</think>", "", limpio, flags=re.S).strip()
    if limpio.startswith("```"):
        lineas = limpio.splitlines()
        if len(lineas) >= 3:
            limpio = "\n".join(lineas[1:-1]).strip()
    if caso["tipo"] == "json":
        try:
            obj = json.loads(limpio)
            return "ok" if (isinstance(obj, dict) and all(k in obj for k in caso["claves_requeridas"])) else "fail_schema"
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


def _construir_mensajes_f_estable(f_data: dict[str, Any], turno_idx: int, historial: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs = [
        {"role": "system", "content": f_data["sistema_base"]},
        {"role": "user", "content": f_data["hechos_canonicos"]},
        {"role": "assistant", "content": "Entendido, mantendré esas reglas durante toda la sesión."},
    ] + list(historial)
    msgs.append({"role": "user", "content": f_data["turnos"][turno_idx]})
    return msgs


def _ejecutar_ov_worker(args: argparse.Namespace) -> int:
    """Ejecuta OpenVINO GenAI LLMPipeline dentro de venv_ov y emite JSON lines por stdout."""
    os.environ["OPENVINO_TELEMETRY_OPT_OUT"] = "1"
    import openvino_genai as og

    t0 = time.perf_counter()
    pipe = og.LLMPipeline(str(args.model), args.ov_device)
    startup_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    tok = pipe.get_tokenizer()

    prompts = {
        "B": json.loads((args.prompts_dir / "B_mixta.json").read_text(encoding="utf-8")),
        "C": json.loads((args.prompts_dir / "C_sostenida.json").read_text(encoding="utf-8")),
        "F": json.loads((args.prompts_dir / "F_agente_multiturno.json").read_text(encoding="utf-8")),
        "G": json.loads((args.prompts_dir / "G_edicion_codigo.json").read_text(encoding="utf-8")),
        "Q": json.loads((args.prompts_dir / "Q_calidad.json").read_text(encoding="utf-8")),
    }

    def run_chat(msgs: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        msgs_nt = _preparar_mensajes(msgs)
        prompt_str = tok.apply_chat_template(msgs_nt, True)
        tiempos: list[float] = []
        partes: list[str] = []

        def streamer(subword: str) -> bool:
            tiempos.append(time.perf_counter())
            partes.append(subword)
            return False

        cfg = og.GenerationConfig()
        cfg.max_new_tokens = max_tokens
        cfg.do_sample = False

        t_ini = time.perf_counter()
        pipe.generate(prompt_str, cfg, streamer)
        t_fin = time.perf_counter()

        texto = "".join(partes)
        lat_ms = (t_fin - t_ini) * 1000.0
        ttft_ms = ((tiempos[0] - t_ini) * 1000.0) if tiempos else lat_ms
        itls = [(tiempos[i] - tiempos[i - 1]) * 1000.0 for i in range(1, len(tiempos))]
        n_out = len(tiempos)
        tg_tps = round(n_out / ((lat_ms - ttft_ms) / 1000.0), 2) if n_out > 1 and (lat_ms - ttft_ms) > 0 else None
        return {
            "texto": texto,
            "hash_salida": hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16],
            "tokens_entrada": None,
            "tokens_salida": n_out,
            "tokens_reutilizados": None,
            "ttft_ms": round(ttft_ms, 2),
            "itl_p50_ms": round(statistics.median(itls), 2) if itls else None,
            "itl_p99_ms": round(sorted(itls)[min(len(itls) - 1, int(0.99 * len(itls)))], 2) if itls else None,
            "latencia_total_ms": round(lat_ms, 2),
            "prefill_tps": None,
            "decode_tps": tg_tps,
            "ram_pico_mb": _ram_pico_proceso_mb(os.getpid()),
            "startup_ms": startup_ms,
        }

    # Warmup
    run_chat(prompts["Q"]["casos"][0]["mensajes"], 16)

    for pr in ("B", "C", "G"):
        pdata = prompts[pr]
        for rep in range(1, args.repeticiones + 1):
            r = run_chat(pdata["mensajes"], pdata["max_tokens"])
            r.update({"prueba": pr, "turno": 1, "repeticion": rep})
            print("OV_ROW:" + json.dumps({k: v for k, v in r.items() if k != "texto"}, ensure_ascii=False), flush=True)

    fdata = prompts["F"]
    for rep in range(1, args.repeticiones + 1):
        hist: list[dict[str, str]] = []
        for t_idx in range(3):
            msgs = _construir_mensajes_f_estable(fdata, t_idx, hist)
            r = run_chat(msgs, fdata["max_tokens"])
            r_out = {k: v for k, v in r.items() if k != "texto"}
            r_out.update({"prueba": "F_estable", "turno": t_idx + 1, "repeticion": rep})
            print("OV_ROW:" + json.dumps(r_out, ensure_ascii=False), flush=True)
            hist.append({"role": "user", "content": fdata["turnos"][t_idx]})
            hist.append({"role": "assistant", "content": r["texto"]})

    for idx, caso in enumerate(prompts["Q"]["casos"], start=1):
        r = run_chat(caso["mensajes"], prompts["Q"]["max_tokens"])
        cal = f"{caso['id']}:{_evaluar_calidad(caso, r['texto'])}"
        r_out = {k: v for k, v in r.items() if k != "texto"}
        r_out.update({"prueba": "Q", "turno": idx, "repeticion": 1, "calidad": cal})
        print("OV_ROW:" + json.dumps(r_out, ensure_ascii=False), flush=True)
    return 0


def _imprimir_resumen(ruta_jsonl: Path) -> None:
    filas = [json.loads(l) for l in ruta_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    grupos: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    errores: list[dict[str, Any]] = []
    for r in filas:
        if r.get("error") is not None:
            errores.append(r)
            continue
        k = (r["motor_id"], r["prueba"], int(r.get("turno", 0)))
        grupos.setdefault(k, []).append(r)

    print("| Motor | Prueba | Turno | Startup ms | TTFT ms | Prefill t/s | Decode t/s | Cache tok | RAM pico MB | Calidad |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for (mot, pr, tr), items in sorted(grupos.items()):
        med = lambda c: round(statistics.median([x[c] for x in items if x.get(c) is not None]), 2) if any(x.get(c) is not None for x in items) else None
        cal = ",".join(sorted({str(x.get("calidad")) for x in items if x.get("calidad")}))
        print(f"| {mot} | {pr} | {tr} | {med('startup_ms')} | {med('ttft_ms')} | {med('prefill_tps')} | {med('decode_tps')} | {med('tokens_reutilizados')} | {med('ram_pico_mb')} | {cal or '-'} |")

    if errores:
        print("\n### Errores registrados")
        for e in errores:
            print(f"- `{e.get('motor_id')}` ({e.get('prueba')}): {e.get('error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark multimotor F4 de GuarIdA.")
    parser.add_argument("--ov-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ov-device", default="GPU", help=argparse.SUPPRESS)
    parser.add_argument("--lab-dir", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--llama-b12017", type=Path)
    parser.add_argument("--prompts-dir", type=Path, default=Path("docs/estudio_inferencia/resultados/prompts"))
    parser.add_argument("--salida", type=Path, default=Path("docs/estudio_inferencia/resultados/2026-11-28_731271e2_f4_qwen3-4b.jsonl"))
    parser.add_argument("--motores", default="all", help="Lista separada por comas o 'all'")
    parser.add_argument("--repeticiones", type=int, default=2)
    parser.add_argument("--reanudar", action="store_true")
    parser.add_argument("--resumen", type=Path)
    args = parser.parse_args()

    if args.ov_worker:
        return _ejecutar_ov_worker(args)
    if args.resumen:
        _imprimir_resumen(args.resumen)
        return 0
    if not args.lab_dir or not args.model or not args.llama_b12017:
        parser.error("--lab-dir, --model y --llama-b12017 son obligatorios salvo con --resumen")

    lab = args.lab_dir.resolve()
    modelo_path = args.model.resolve()
    b12017_bin = args.llama_b12017.resolve()
    llama_latest_bin = lab / "llama_latest" / "llama-server.exe"
    dynalm_v_bin = lab / "dynalm_vulkan" / "dynalm-windows-x86_64-vulkan" / "bin" / "dynalm.exe"
    dynalm_c_bin = lab / "dynalm_cpu" / "dynalm-windows-x86_64" / "bin" / "dynalm.exe"
    mistralrs_bin = lab / "mistralrs" / "mistralrs.exe"
    ov_py = lab / "venv_ov" / "Scripts" / "python.exe"

    sha_modelo = _sha256_archivo(modelo_path)
    hash_hw = _hash_hardware_guarida()

    prompts = {
        "B": json.loads((args.prompts_dir / "B_mixta.json").read_text(encoding="utf-8")),
        "C": json.loads((args.prompts_dir / "C_sostenida.json").read_text(encoding="utf-8")),
        "F": json.loads((args.prompts_dir / "F_agente_multiturno.json").read_text(encoding="utf-8")),
        "G": json.loads((args.prompts_dir / "G_edicion_codigo.json").read_text(encoding="utf-8")),
        "Q": json.loads((args.prompts_dir / "Q_calidad.json").read_text(encoding="utf-8")),
    }

    hechas: set[tuple[str, str, int, int]] = set()
    if args.reanudar and args.salida.exists():
        for l in args.salida.read_text(encoding="utf-8", errors="replace").splitlines():
            if not l.strip():
                continue
            try:
                r = json.loads(l)
                if r.get("error") is None:
                    hechas.add((r["motor_id"], r["prueba"], int(r.get("turno", 0)), int(r.get("repeticion", 0))))
            except Exception:
                continue

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="guarida_f4_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        dyn_cache_v = tmp_path / "dyn_cache_v"
        dyn_cache_c = tmp_path / "dyn_cache_c"

        catalogo = {
            "llama-b12017-N0win": {
                "tipo": "http", "bin": b12017_bin, "backend": "Vulkan",
                "cmd_fn": lambda p: [str(b12017_bin), "-m", str(modelo_path), "--host", "127.0.0.1", "--port", str(p), "--no-webui", "-ngl", "99", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "off", "-ctk", "f16", "-ctv", "f16", "--cache-reuse", "256", "--spec-type", "ngram-mod"],
                "id_slot": 0, "cache_prompt": True, "soporta_seed": True,
            },
            "llama-latest-N0win": {
                "tipo": "http", "bin": llama_latest_bin, "backend": "Vulkan",
                "cmd_fn": lambda p: [str(llama_latest_bin), "-m", str(modelo_path), "--host", "127.0.0.1", "--port", str(p), "--no-webui", "-ngl", "99", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "off", "-ctk", "f16", "-ctv", "f16", "--cache-reuse", "256", "--spec-type", "ngram-mod"],
                "id_slot": 0, "cache_prompt": True, "soporta_seed": True,
            },
            "llama-b12017-CPU": {
                "tipo": "http", "bin": b12017_bin, "backend": "CPU",
                "cmd_fn": lambda p: [str(b12017_bin), "-m", str(modelo_path), "--host", "127.0.0.1", "--port", str(p), "--no-webui", "-ngl", "0", "-c", "8192", "-b", "512", "-ub", "512", "-t", "4", "-tb", "8", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "--cache-reuse", "256", "--spec-type", "ngram-mod"],
                "id_slot": 0, "cache_prompt": True, "soporta_seed": True,
            },
            "dynalm-vulkan": {
                "tipo": "http", "bin": dynalm_v_bin, "backend": "Vulkan",
                "cmd_fn": lambda p: [str(dynalm_v_bin), "serve", str(modelo_path), "--host", "127.0.0.1", "--port", str(p), "-t", "4", "-c", "8192", "--backend", "vulkan", "--prompt-cache", str(dyn_cache_v)],
                "id_slot": None, "cache_prompt": None, "soporta_seed": False,
            },
            "dynalm-cpu": {
                "tipo": "http", "bin": dynalm_c_bin, "backend": "CPU",
                "cmd_fn": lambda p: [str(dynalm_c_bin), "serve", str(modelo_path), "--host", "127.0.0.1", "--port", str(p), "-t", "4", "-c", "8192", "--backend", "cpu", "--prompt-cache", str(dyn_cache_c)],
                "id_slot": None, "cache_prompt": None, "soporta_seed": False,
            },
            "mistralrs-cpu": {
                "tipo": "http", "bin": mistralrs_bin, "backend": "CPU",
                "cmd_fn": lambda p: [str(mistralrs_bin), "serve", "-p", str(p), "--max-seqs", "1", "--prefix-cache-n", "8", "auto", "-m", str(modelo_path.parent), "-f", modelo_path.name],
                "id_slot": None, "cache_prompt": None, "soporta_seed": False,
            },
            "openvino-genai-gpu": {"tipo": "ov", "device": "GPU", "backend": "OpenVINO-GPU"},
            "openvino-genai-cpu": {"tipo": "ov", "device": "CPU", "backend": "OpenVINO-CPU"},
        }

        seleccion = list(catalogo.keys()) if args.motores == "all" else [m.strip() for m in args.motores.split(",") if m.strip()]

        with open(args.salida, "a" if args.reanudar else "w", encoding="utf-8") as f_out:
            def registrar(reg: dict[str, Any]) -> None:
                f_out.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f_out.flush()

            for motor_id in seleccion:
                cfg = catalogo[motor_id]
                if args.reanudar:
                    pendiente = False
                    for pr in ("B", "C", "G"):
                        for r in range(1, args.repeticiones + 1):
                            if (motor_id, pr, 1, r) not in hechas:
                                pendiente = True
                    for r in range(1, args.repeticiones + 1):
                        for t in (1, 2, 3):
                            if (motor_id, "F_estable", t, r) not in hechas:
                                pendiente = True
                    for idx in (1, 2):
                        if (motor_id, "Q", idx, 1) not in hechas:
                            pendiente = True
                    if not pendiente:
                        print(f"[SKIP] {motor_id} ya completo")
                        continue

                print(f"[RUN] {motor_id}")
                if cfg["tipo"] == "ov":
                    env = dict(os.environ)
                    env["OPENVINO_TELEMETRY_OPT_OUT"] = "1"
                    cmd = [
                        str(ov_py), "-u", str(Path(__file__).resolve()), "--ov-worker",
                        "--ov-device", cfg["device"], "--model", str(modelo_path),
                        "--prompts-dir", str(args.prompts_dir), "--repeticiones", str(args.repeticiones),
                    ]
                    proc_ov = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", env=env)
                    hubo_filas = False
                    lines_tail: list[str] = []
                    assert proc_ov.stdout is not None
                    for line in proc_ov.stdout:
                        s = line.strip()
                        if s.startswith("OV_ROW:"):
                            hubo_filas = True
                            row = json.loads(s[7:])
                            row.update({
                                "origen": "medido",
                                "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                                "hash_hardware": hash_hw,
                                "perfil": "B",
                                "motor_id": motor_id,
                                "backend_declarado": cfg["backend"],
                                "modelo": modelo_path.name,
                                "sha256_modelo": sha_modelo,
                                "error": None,
                            })
                            if (motor_id, row["prueba"], int(row["turno"]), int(row["repeticion"])) not in hechas:
                                registrar(row)
                        elif s:
                            lines_tail.append(s)
                            lines_tail = lines_tail[-15:]
                    rc = proc_ov.wait(timeout=30)
                    if not hubo_filas:
                        err = "\n".join(lines_tail)[-800:]
                        registrar({
                            "origen": "medido",
                            "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                            "hash_hardware": hash_hw,
                            "motor_id": motor_id,
                            "prueba": "ARRANQUE",
                            "turno": 0,
                            "repeticion": 0,
                            "error": f"exit={rc}: {err}",
                        })
                        print(f"[ERR] {motor_id}: {err[:200]}")
                    continue

                # Motores HTTP
                puerto = _puerto_libre()
                base_url = f"http://127.0.0.1:{puerto}"
                log_file = tmp_path / f"{motor_id}.log"
                cmd = cfg["cmd_fn"](puerto)
                with open(log_file, "wb") as f_log:
                    proc = subprocess.Popen(cmd, stdout=f_log, stderr=subprocess.STDOUT)
                try:
                    startup_ms, model_api_id = _esperar_http(base_url, proc, timeout_s=180.0)
                    # Warmup
                    _chat_stream(base_url, model_api_id, prompts["Q"]["casos"][0]["mensajes"], 16, cfg["id_slot"], cfg["cache_prompt"], cfg["soporta_seed"])

                    def base_reg(pr: str, tr: int, rep: int) -> dict[str, Any]:
                        return {
                            "origen": "medido",
                            "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                            "hash_hardware": hash_hw,
                            "perfil": "B",
                            "motor_id": motor_id,
                            "backend_declarado": cfg["backend"],
                            "modelo": modelo_path.name,
                            "sha256_modelo": sha_modelo,
                            "startup_ms": round(startup_ms, 2),
                            "prueba": pr,
                            "turno": tr,
                            "repeticion": rep,
                            "ram_pico_mb": _ram_pico_proceso_mb(proc.pid),
                            "error": None,
                        }

                    for pr in ("B", "C", "G"):
                        pdata = prompts[pr]
                        for rep in range(1, args.repeticiones + 1):
                            if (motor_id, pr, 1, rep) in hechas:
                                continue
                            res = _chat_stream(base_url, model_api_id, pdata["mensajes"], pdata["max_tokens"], cfg["id_slot"], cfg["cache_prompt"], cfg["soporta_seed"])
                            reg = base_reg(pr, 1, rep)
                            reg.update({k: v for k, v in res.items() if k != "texto"})
                            registrar(reg)

                    fdata = prompts["F"]
                    for rep in range(1, args.repeticiones + 1):
                        hist: list[dict[str, str]] = []
                        for t_idx in range(3):
                            mens = _construir_mensajes_f_estable(fdata, t_idx, hist)
                            res = _chat_stream(base_url, model_api_id, mens, fdata["max_tokens"], cfg["id_slot"], cfg["cache_prompt"], cfg["soporta_seed"])
                            if (motor_id, "F_estable", t_idx + 1, rep) not in hechas:
                                reg = base_reg("F_estable", t_idx + 1, rep)
                                reg.update({k: v for k, v in res.items() if k != "texto"})
                                registrar(reg)
                            hist.append({"role": "user", "content": fdata["turnos"][t_idx]})
                            hist.append({"role": "assistant", "content": res["texto"]})

                    for idx, caso in enumerate(prompts["Q"]["casos"], start=1):
                        if (motor_id, "Q", idx, 1) in hechas:
                            continue
                        res = _chat_stream(base_url, model_api_id, caso["mensajes"], prompts["Q"]["max_tokens"], cfg["id_slot"], False, cfg["soporta_seed"])
                        reg = base_reg("Q", idx, 1)
                        reg.update({k: v for k, v in res.items() if k != "texto"})
                        reg["calidad"] = f"{caso['id']}:{_evaluar_calidad(caso, res['texto'])}"
                        registrar(reg)
                except Exception as exc:
                    tail = log_file.read_text(encoding="utf-8", errors="replace")[-600:] if log_file.exists() else ""
                    registrar({
                        "origen": "medido",
                        "fecha": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                        "hash_hardware": hash_hw,
                        "motor_id": motor_id,
                        "prueba": "ERROR",
                        "turno": 0,
                        "repeticion": 0,
                        "error": f"{exc} | log: {tail}",
                    })
                    print(f"[ERR] {motor_id}: {exc}")
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
