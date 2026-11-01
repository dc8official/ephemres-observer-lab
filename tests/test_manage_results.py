"""Saving and deleting selected runs. Delete MOVES a saved run's files and INDEX.md entry to .deleted/ (recoverable)."""
import asyncio
import os
import tempfile
import unittest
from unittest import mock

from server import analysis
from server.analysis import make_row

try:
    from fastapi import HTTPException
    from server import app as dash
except ImportError:                                       # pragma: no cover
    dash = None

T0 = 1_700_000_000_000_000_000
NAMES = ["20261023-100000_py-sc_1ep-burst-sem15-db3_10-0-0-1", "20261023-100100_go-sc_1ep-burst-sem15-db3_10-0-0-1"]


def rows():
    return [make_row(0, 0, 1, "10.0.0.1", [s, T0, T0 + 1000, T0 + 2000, None, 1, 1, 0]) for s in range(3)]


def save(d, base):
    r = rows()
    analysis.save_run(d, base, {"note": base}, {}, r, analysis.analyse(r, {}))


class TrashRunTest(unittest.TestCase):
    def test_moves_files_and_index_entry_only_for_that_run(self):
        with tempfile.TemporaryDirectory() as d:
            for n in NAMES:
                save(d, n)
            trash = os.path.join(d, ".deleted", "t1")
            moved = analysis.trash_run(d, NAMES[0], trash)
            self.assertEqual(sorted(moved), sorted(NAMES[0] + s for s in analysis.RUN_SUFFIXES))
            left = os.listdir(d)
            self.assertFalse(any(f.startswith(NAMES[0]) for f in left))
            self.assertTrue(all(NAMES[1] + s in left for s in analysis.RUN_SUFFIXES))   # the other run untouched
            with open(os.path.join(d, "INDEX.md"), encoding="utf-8") as f:
                index = f.read()
            self.assertNotIn(NAMES[0], index)
            self.assertIn(f"## {NAMES[1]}", index)
            with open(os.path.join(trash, "INDEX.md"), encoding="utf-8") as f:
                self.assertIn(f"## {NAMES[0]}", f.read())   # kept for restoring
            self.assertEqual(analysis.list_saved(d), [NAMES[1]])                          # .deleted/ is not loaded

    def test_heading_with_a_remark_and_neighbours(self):
        text = "# idx\n\n## a  (baseline, realistic load)\n\n- one\n\n## b\n\n- two\n"
        kept, removed = analysis._split_index_entry(text, "a")
        self.assertEqual(kept, "# idx\n\n## b\n\n- two\n")
        self.assertIn("(baseline, realistic load)", removed)
        self.assertEqual(analysis._split_index_entry(text, "ab"), (text, ""))   # whole names only

    def test_rejects_names_that_are_not_runs(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("", "../x", ".hidden", f"sub{os.sep}x"):
                with self.assertRaises(ValueError):
                    analysis.trash_run(d, bad, os.path.join(d, ".deleted"))


@unittest.skipIf(dash is None, "FastAPI not installed")
class DeleteApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(dash, "RESULTS_DIR", dash.Path(self.tmp.name)), mock.patch.object(dash, "mgr", dash.Manager())):
            p.start()
            self.addCleanup(p.stop)
        save(self.tmp.name, NAMES[0])
        dash.mgr.load_saved()
        self.disk = next(iter(dash.mgr.runs.values()))
        self.mem = dash.Run(id="run1", name=NAMES[1], cfg={"engine": "go", "virtual_endpoints": 1, "pings_per_cycle": 1},
                            status="done", rows=rows())
        dash.mgr.runs["run1"] = self.mem

    def call(self, fn, ids):
        return asyncio.run(fn(dash.IdsBody(ids=ids)))

    def test_delete_saved_and_unsaved(self):
        res = self.call(dash.api_delete, [self.disk.id, "run1"])
        self.assertEqual(res["moved_to_trash"], [NAMES[0]])
        self.assertEqual(res["discarded_unsaved"], [NAMES[1]])
        self.assertEqual(dash.mgr.runs, {})
        self.assertEqual(analysis.list_saved(self.tmp.name), [])
        trash_dirs = os.listdir(os.path.join(self.tmp.name, ".deleted"))
        self.assertEqual(len(trash_dirs), 1)
        self.assertIn(NAMES[0] + ".csv", os.listdir(os.path.join(self.tmp.name, ".deleted", trash_dirs[0])))

    def test_running_run_is_refused(self):
        self.mem.status = "running"
        with self.assertRaises(HTTPException) as cm:
            self.call(dash.api_delete, ["run1"])
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("run1", dash.mgr.runs)

    def test_save_selected(self):
        res = self.call(dash.api_save_selected, [self.disk.id, "run1"])
        self.assertEqual(res["saved"], [NAMES[1]])
        self.assertEqual(res["already_saved"], [NAMES[0]])
        self.assertIn(NAMES[1], analysis.list_saved(self.tmp.name))


@unittest.skipIf(dash is None, "FastAPI not installed")
class SavedRunDetailsTest(unittest.TestCase):
    def test_start_time_comes_from_the_name_not_the_file(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            save(d, NAMES[0])
            os.utime(os.path.join(d, NAMES[0] + ".csv"), (0, 0))      # a file time that has nothing to do with the run
            t = dash.run_start_time(NAMES[0], dash.Path(d) / (NAMES[0] + ".csv"))
        self.assertEqual(time.strftime("%Y%m%d-%H%M%S", time.localtime(t)), NAMES[0][:15])

    def test_clock_and_route_survive_save_and_reload(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dash, "RESULTS_DIR", dash.Path(d)):
            mgr = dash.Manager()
            run = dash.Run(id="run1", name=NAMES[1], cfg={"engine": "go", "virtual_endpoints": 1, "pings_per_cycle": 1},
                           status="done", rows=rows(), clock="SO_TIMESTAMPING software [go GOMAXPROCS=1]",
                           routes=[{"target": "10.0.0.1", "interface": "eth0", "src_ip": "10.0.0.2"}])
            mgr.runs["run1"] = run
            asyncio.run(mgr.save(run))
            again = dash.Manager()
            again.load_saved()
            loaded = next(iter(again.runs.values()))
        self.assertEqual(loaded.clock, run.clock)
        self.assertEqual(loaded.routes[0]["interface"], "eth0")


if __name__ == "__main__":
    unittest.main()
