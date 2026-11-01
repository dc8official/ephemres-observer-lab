"""bin/go_prober and bin/rust_prober: argument checks that run before any raw socket is opened.

Skipped for an engine that has not been built (./build_workers.sh).
"""
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES = {name: os.path.join(ROOT, "bin", name) for name in ("go_prober", "rust_prober")}


def run(binary, *args):
    return subprocess.run([binary, *args], capture_output=True, text=True, timeout=20)


class EngineArgsTest(unittest.TestCase):
    def test_icmp_id_space_is_checked(self):                               # review finding 10
        for name, binary in ENGINES.items():
            if not os.access(binary, os.X_OK):
                continue
            with self.subTest(engine=name):
                # 0x1000 + 61440 endpoints + 1 warm-up id = 0x10001 > 16 bits
                p = run(binary, "--targets", "10.0.0.1", "--virtual-endpoints", "61440")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("16-bit icmp_id", p.stderr)

    def test_bad_target_is_rejected(self):
        for name, binary in ENGINES.items():
            if not os.access(binary, os.X_OK):
                continue
            with self.subTest(engine=name):
                p = run(binary, "--targets", "10.0.0.999")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("10.0.0.999", p.stderr)


if __name__ == "__main__":
    unittest.main()
