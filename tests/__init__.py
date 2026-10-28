"""Unit tests.  Run from the project root:   .venv/bin/python -m unittest -v

Everything here runs without root and without a network: raw sockets, the NIC
ioctl and the probe subprocess are replaced by small fakes.  Tests that need
FastAPI (the dashboard) skip themselves when it is not installed, so plain
``python3 -m unittest`` works too.
"""

# Every test runs against a throwaway results folder: nothing a test does (e.g. the dashboard's auto-save of a fake
# run) can ever write into the real test_results/. Set before any server module is imported.
import os as _os
import tempfile as _tempfile

_os.environ["OBSERVER_RESULTS_DIR"] = _tempfile.mkdtemp(prefix="observer-lab-tests-")
