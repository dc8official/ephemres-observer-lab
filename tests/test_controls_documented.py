"""Every control on the dashboard is documented, and docs/09-replication.md matches the dashboard's own reference.

The dashboard keeps one list, CONTROLS (server/static/index.html), that feeds both the Research tab's controls
reference and the hover tooltips. This test fails when a control is added to the page without an entry there, and
when the copy in docs/09-replication.md no longer matches it. To regenerate that copy after changing CONTROLS:
    .venv/bin/python -m tests.test_controls_documented --print
and paste the output over section 7's tables.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "server", "static", "index.html")
GUIDE = os.path.join(ROOT, "docs", "09-replication.md")
# Elements documented together with a sibling (one entry covers the group).
COVERED_BY = {"alt_go": "alt_python", "alt_rust": "alt_python", "savenote": "focusnote"}

# Prints the controls table in the guide's Markdown layout (same code as used to write the guide).
RENDER = r'''
const cell = t => String(t).replace(/\|/g, "\\|");
const out = [];
for (const sec of [...new Set(CONTROLS.map(c => c.section))]) {
  out.push(`### ${sec}`, "", "| Control | What it does | Default | Range | Ephemres | When comparing runs |", "|---|---|---|---|---|---|");
  for (const c of CONTROLS.filter(c => c.section === sec))
    out.push(`| **${cell(c.name)}** | ${cell(c.what)} | ${cell(c.def)} | ${cell(c.range)} | ${cell(c.eph)} | ${cell(c.role)} |`);
  out.push("");
}
out.push("### Terms used above", "");
for (const [n, t] of CONCEPT_HELP) out.push(`* **${n}**: ${t}`);
console.log(out.join("\n"));
'''


def page() -> str:
    with open(PAGE) as f:
        return f.read()


def controls_table() -> str:
    """The controls reference rendered from CONTROLS in index.html, in the guide's Markdown layout."""
    html = page()
    src = html[html.index("const CONTROLS = ["):html.index("const METRIC_HELP = [")] + RENDER
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as js:
        js.write(src)
    try:
        return subprocess.run(["node", js.name], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    finally:
        os.unlink(js.name)


class ControlsDocumentedTest(unittest.TestCase):
    def test_every_control_on_the_page_has_an_entry(self):
        html = page()
        lab = html[html.index('<main id="view-lab">'):html.index("</main>", html.index('<main id="view-lab">'))]
        header = html[html.index("<header>"):html.index("</header>")]
        ids = set(re.findall(r'<(?:input|select|button|a)\b[^>]*\bid="([^"]+)"', lab + header))
        ids -= {"tab-lab", "tab-docs"}                       # the two tab buttons switch pages; nothing to configure
        documented = set(re.findall(r'\{id: "([^"]+)"', html[html.index("const CONTROLS = ["):html.index("const CONCEPT_HELP")]))
        missing = sorted(i for i in ids if COVERED_BY.get(i, i) not in documented)
        self.assertEqual(missing, [], "controls without an entry in CONTROLS (index.html)")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_replication_guide_matches_the_dashboard(self):
        table = controls_table()
        with open(GUIDE) as f:
            guide = f.read()
        self.assertIn(table, guide, "docs/09-replication.md section 7 is out of date with CONTROLS in index.html")


if __name__ == "__main__":
    import sys
    if "--print" in sys.argv:            # python -m tests.test_controls_documented --print > table.md
        print(controls_table())
    else:
        unittest.main()
