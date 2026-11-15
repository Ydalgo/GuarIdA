import tempfile
import unittest
from pathlib import Path

from guarida_manager.engine.tensors_engine import MotorTensoresLocales


class TestTensorsEngine(unittest.TestCase):
    def test_es_modelo_tensores(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p_dir = Path(tmp_dir)
            fake_safetensors = p_dir / "model.safetensors"
            fake_safetensors.write_bytes(b"dummy")
            fake_bin = p_dir / "pytorch_model.bin"
            fake_bin.write_bytes(b"dummy")
            fake_txt = p_dir / "readme.txt"
            fake_txt.write_bytes(b"dummy")

            self.assertTrue(MotorTensoresLocales.es_modelo_tensores(fake_safetensors))
            self.assertTrue(MotorTensoresLocales.es_modelo_tensores(fake_bin))
            self.assertFalse(MotorTensoresLocales.es_modelo_tensores(fake_txt))
            self.assertTrue(MotorTensoresLocales.es_modelo_tensores(p_dir))

    def test_inspeccionar_tensores(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p_dir = Path(tmp_dir)
            f_bin = p_dir / "weights.bin"
            f_bin.write_bytes(b"0" * 1024)

            info = MotorTensoresLocales.inspeccionar_tensores(f_bin)
            self.assertTrue(info["valido"])
            self.assertEqual(info["tipo"], "pytorch_bin")
            self.assertGreater(info["tamano_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
