import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("bruin") is None, reason="bruin not installed")
def test_bruin_demo_runs_three_titled_steps_and_leaves_gitignore_alone():
    gitignore = ROOT / ".gitignore"
    before = gitignore.read_bytes() if gitignore.exists() else None
    proc = subprocess.run(["bash", str(ROOT / "bruin" / "demo.sh")], cwd=ROOT / "lab",
                          capture_output=True, text=True, timeout=60)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    titles = [ln for ln in proc.stdout.splitlines() if ln.startswith("== ")]
    assert [t[3:6] for t in titles] == ["1/3", "2/3", "3/3"], titles
    # either the miss table or the plain hint for an empty warehouse
    assert "MISS_RATE" in out or "No graded sessions" in out
    assert "learn.skill_attempts" in out and "learn.session_events" in out   # lineage
    page = ROOT / "data" / "bruin" / "docs" / "lab-rotation.html"
    assert page.exists() and "learn.bkt_mastery" in page.read_text()
    assert (gitignore.read_bytes() if gitignore.exists() else None) == before
