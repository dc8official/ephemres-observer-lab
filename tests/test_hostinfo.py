"""server/hostinfo.py: host-condition warnings."""
import unittest

from server import hostinfo


class HostInfoTest(unittest.TestCase):
    def test_collect_on_this_machine_never_raises(self):
        info = hostinfo.collect(["lo", "?"], 0)
        self.assertIn("kernel", info)
        self.assertIsInstance(info["warnings"], list)

    def test_warnings(self):
        info = {"cpu": {"probe_core": 7, "governor": "powersave", "turbo": False, "smt_siblings": "3,7",
                        "cstates": [{"name": "C1", "exit_latency_us": 2, "enabled": True},
                                    {"name": "C10", "exit_latency_us": 890, "enabled": True},
                                    {"name": "C9", "exit_latency_us": 480, "enabled": False}]},
                "load_avg_1m": 2.5,
                "nics": [{"interface": "eth0", "irqs": [{"irq": 160, "cpus": "0-7"}], "coalescing": {"Adaptive RX": "on  TX: on"}}]}
        text = " | ".join(hostinfo.warnings(info))
        for expected in ("powersave", "C10", "890", "CPU 3", "load average is 2.5", "probe core 7", "adaptive interrupt coalescing"):
            self.assertIn(expected, text)

    def test_quiet_host_has_no_warnings(self):
        info = {"cpu": {"probe_core": 2, "governor": "performance", "turbo": False, "smt_siblings": "2",
                        "cstates": [{"name": "C1", "exit_latency_us": 2, "enabled": True}]},
                "load_avg_1m": 0.1, "nics": [{"interface": "eth0", "irqs": [{"irq": 160, "cpus": "0-1"}], "coalescing": {}}]}
        self.assertEqual(hostinfo.warnings(info), [])

    def test_cpu_list_parsing(self):
        self.assertEqual(hostinfo._expand("0-3,6"), {0, 1, 2, 3, 6})


if __name__ == "__main__":
    unittest.main()
