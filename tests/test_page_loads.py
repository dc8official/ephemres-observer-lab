"""server/static/index.html: the page's script must run from top to bottom without an error.

A syntax check is not enough: e.g. a table definition that uses a helper declared further down
("Cannot access 'x' before initialization") parses fine but stops the whole page at load.  This test
executes the real script in Node with a stand-in DOM (every element, style and browser API answers
with a harmless dummy) and fails if anything at load time throws.  Skipped when node is missing.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUB = r"""
const dummy = () => new Proxy(function () {}, {
  get(t, k) {
    if (k === Symbol.iterator) return function* () {};
    if (k === Symbol.toPrimitive) return () => "";
    if (k === "then") return undefined;                  // not a promise
    if (k in t) return t[k];
    return dummy();
  },
  apply() { return dummy(); }, construct() { return dummy(); }, set() { return true; },
});
globalThis.document = dummy(); globalThis.window = globalThis; globalThis.location = {hash: "", host: "x", protocol: "http:"};
globalThis.history = dummy(); globalThis.localStorage = {getItem: () => null, setItem() {}};
globalThis.matchMedia = () => ({addEventListener() {}, matches: false});
globalThis.getComputedStyle = () => ({getPropertyValue: () => "#123456"});
globalThis.requestAnimationFrame = () => 0; globalThis.cancelAnimationFrame = () => {};
globalThis.WebSocket = function () { return dummy(); }; globalThis.fetch = async () => dummy();
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageScriptTest(unittest.TestCase):
    def test_script_runs_at_load(self):
        with open(os.path.join(ROOT, "server", "static", "index.html")) as f:
            html = f.read()
        script = re.search(r"<script>\n(.*?)</script>", html, re.S).group(1)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as js:
            js.write(STUB + script + '\nconsole.log("PAGE-SCRIPT-OK");\n')
        try:
            p = subprocess.run(["node", js.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(js.name)
        self.assertIn("PAGE-SCRIPT-OK", p.stdout, p.stderr[-1500:])


class NoBuiltInTargetTest(unittest.TestCase):
    def test_targets_field_has_no_address_built_in(self):
        # A lab's own IP must never ship as the page's default; the last target used is remembered per browser.
        with open(os.path.join(ROOT, "server", "static", "index.html")) as f:
            html = f.read()
        tag = re.search(r'<input[^>]*\bid="targets"[^>]*>', html).group(0)
        self.assertRegex(tag, r'\bvalue=""')             # empty by default (a placeholder example is fine)


if __name__ == "__main__":
    unittest.main()
