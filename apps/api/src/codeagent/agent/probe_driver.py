"""The probe driver: tries candidate fixes one after another inside a single sandbox run.

Starting a container per candidate would cost seconds each; this driver is copied into the
working tree and run once. For every candidate it writes the variant file, runs the failing
tests, and when they pass runs the whole suite; it restores the original file after each
try and stops at the first candidate that passes everything. It uses only the standard
library, because it runs with whatever interpreter the sandbox image provides.
"""

from __future__ import annotations

PROBE_DIR = ".codeagent/probe"
CANDIDATES_PATH = f"{PROBE_DIR}/candidates.json"
RESULTS_PATH = f"{PROBE_DIR}/results.json"
DRIVER_PATH = f"{PROBE_DIR}/driver.py"

DRIVER = """\
import json
import pathlib
import subprocess
import sys

spec = json.loads(pathlib.Path("CANDIDATES").read_text())
tests = spec["tests"]
timeout = spec["timeout_s"]
results = []


def pytest(*args):
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return False


for index, candidate in enumerate(spec["candidates"]):
    path = pathlib.Path(candidate["path"])
    original = path.read_text()
    path.write_text(candidate["content"])
    try:
        targeted = pytest("-x", *tests)
        full = pytest() if targeted else None
    finally:
        path.write_text(original)
    results.append({"index": index, "targeted": targeted, "full": full})
    if targeted and full:
        break

pathlib.Path("RESULTS").write_text(json.dumps(results))
print(f"probed {len(results)} candidate(s)")
""".replace("CANDIDATES", CANDIDATES_PATH).replace("RESULTS", RESULTS_PATH)
