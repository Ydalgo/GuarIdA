import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Generator, Optional

from guarida_manager.logger import obtener_logger

logger = obtener_logger("tensors_engine")


class MotorTensoresLocales:
    """Motor de inferencia y gestión de modelos con tensores y pesos nativos (Safetensors / PyTorch)."""

    def __init__(self, ruta_modelo: Optional[Path | str] = None, dispositivo: Optional[str] = None) -> None:
        self.ruta_modelo = Path(ruta_modelo) if ruta_modelo else None
        self._dispositivo = dispositivo
        self._modelo = None
        self._tokenizador = None

    @staticmethod
    def es_modelo_tensores(ruta: Path) -> bool:
        """Determina si una ruta corresponde a un archivo o carpeta con tensores y pesos (safetensors/bin/pt)."""
        if not ruta.exists():
            return False
        if ruta.is_file():
            return ruta.suffix.lower() in (".safetensors", ".bin", ".pt")
        if ruta.is_dir():
            archivos = [f.name.lower() for f in ruta.iterdir()]
            return any(
                f.endswith(".safetensors") or f.endswith(".bin") for f in archivos
            ) or "config.json" in archivos
        return False

    @staticmethod
    def inspeccionar_tensores(ruta: Path) -> dict[str, Any]:
        """Lee metadatos y tensores de un archivo safetensors sin cargar todos los pesos a RAM."""
        resultado = {
            "valido": False,
            "tipo": "desconocido",
            "parametros_aprox": 0,
            "tamano_bytes": 0,
            "tamano_mb": 0.0,
            "tensores": [],
            "metadatos": {},
            "error": None,
        }
        if not ruta.exists():
            resultado["error"] = f"La ruta no existe: {ruta}"
            return resultado

        try:
            archivo_safetensor = ruta if ruta.is_file() else None
            if ruta.is_dir():
                candidatos = list(ruta.glob("*.safetensors"))
                if candidatos:
                    archivo_safetensor = candidatos[0]

            if archivo_safetensor and archivo_safetensor.suffix.lower() == ".safetensors":
                resultado["tipo"] = "safetensors"
                resultado["tamano_bytes"] = archivo_safetensor.stat().st_size
                resultado["tamano_mb"] = round(resultado["tamano_bytes"] / (1024 * 1024), 2)

                try:
                    import safetensors
                    with safetensors.safe_open(str(archivo_safetensor), framework="pt", device="cpu") as f:
                        resultado["metadatos"] = f.metadata() or {}
                        nombres = f.keys()
                        resultado["tensores"] = nombres[:50]
                        total_params = 0
                        for k in nombres:
                            slice_t = f.get_slice(k)
                            shape = slice_t.get_shape()
                            p = 1
                            for s in shape:
                                p *= s
                            total_params += p
                        resultado["parametros_aprox"] = total_params
                        resultado["valido"] = True
                except Exception as e_st:
                    resultado["error"] = f"Inspección safetensors falló: {e_st}"
                    resultado["valido"] = True
            elif ruta.is_file():
                resultado["tipo"] = "pytorch_bin"
                resultado["tamano_bytes"] = ruta.stat().st_size
                resultado["tamano_mb"] = round(resultado["tamano_bytes"] / (1024 * 1024), 2)
                resultado["valido"] = True
            elif ruta.is_dir():
                resultado["tipo"] = "directorio_pesos"
                total_b = sum(f.stat().st_size for f in ruta.iterdir() if f.is_file())
                resultado["tamano_bytes"] = total_b
                resultado["tamano_mb"] = round(total_b / (1024 * 1024), 2)
                resultado["valido"] = True
        except Exception as e:
            resultado["error"] = str(e)
            logger.error(f"Error inspeccionando tensores: {e}", exc_info=True)

        return resultado

    def resolver_dispositivo(self) -> str:
        if self._dispositivo:
            return self._dispositivo
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def cargar_modelo(self) -> bool:
        """Carga el modelo y tokenizador en memoria mediante transformers y torch."""
        if not self.ruta_modelo or not self.ruta_modelo.exists():
            raise FileNotFoundError(f"Ruta de modelo no encontrada: {self.ruta_modelo}")

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            dispositivo = self.resolver_dispositivo()
            logger.info(f"Cargando modelo de tensores desde '{self.ruta_modelo}' en dispositivo '{dispositivo}'...")

            ruta_dir = self.ruta_modelo.parent if self.ruta_modelo.is_file() else self.ruta_modelo
            self._tokenizador = AutoTokenizer.from_pretrained(str(ruta_dir), trust_remote_code=True)
            self._modelo = AutoModelForCausalLM.from_pretrained(
                str(ruta_dir),
                torch_dtype=torch.float16 if dispositivo == "cuda" else torch.float32,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            self._modelo.to(dispositivo)
            self._modelo.eval()
            return True
        except Exception as e:
            logger.error(f"Error cargando modelo de tensores: {e}", exc_info=True)
            raise RuntimeError(f"Fallo cargando tensores con transformers/torch: {e}") from e

    def completar_texto(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperatura: float = 0.2,
        callback_token: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        """Ejecuta inferencia generativa sobre el modelo de tensores."""
        if self._modelo is None or self._tokenizador is None:
            self.cargar_modelo()

        import torch

        dispositivo = self.resolver_dispositivo()
        t_ini = time.perf_counter()

        inputs = self._tokenizador(prompt, return_tensors="pt").to(dispositivo)
        prompt_tokens = inputs.input_ids.shape[1]

        with torch.no_grad():
            gen_kwargs: dict[str, Any] = {
                **inputs,
                "max_new_tokens": max_tokens,
                "do_sample": temperatura > 0.0,
                "pad_token_id": self._tokenizador.eos_token_id,
            }
            if temperatura > 0.0:
                gen_kwargs["temperature"] = temperatura
                gen_kwargs["top_p"] = 0.9

            salida_tokens = self._modelo.generate(**gen_kwargs)

        latencia_total_s = time.perf_counter() - t_ini
        nuevos_tokens = salida_tokens[0][prompt_tokens:]
        texto_generado = self._tokenizador.decode(nuevos_tokens, skip_special_tokens=True)
        pred_n = len(nuevos_tokens)
        tok_s = round(pred_n / max(latencia_total_s, 0.001), 2)

        return {
            "content": texto_generado,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": pred_n,
            "tok_per_second": tok_s,
            "latencia_ms": round(latencia_total_s * 1000.0, 2),
            "dispositivo": dispositivo,
        }

    def liberar_memoria(self) -> None:
        """Descarga el modelo de la memoria RAM/VRAM."""
        import gc
        self._modelo = None
        self._tokenizador = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
