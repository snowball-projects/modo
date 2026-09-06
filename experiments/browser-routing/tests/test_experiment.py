import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthetic_build_and_worker(tmp_path):
    fixture = tmp_path / "fixture"
    output = tmp_path / "generated"
    subprocess.run(
        [
            sys.executable,
            str(EXPERIMENT / "tests" / "make_fixture.py"),
            "--directory",
            str(fixture),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(EXPERIMENT / "build.py"),
            "--source",
            str(fixture / "synthetic.npz"),
            "--cases",
            str(fixture / "cases.json"),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads((output / "build-summary.json").read_text())
    assert summary["schema"] == "modo-browser-build-v1"
    assert summary["cases"] == ["ends", "inside"]
    assert summary["tiles"] > 1
    for metadata in summary["manifests"].values():
        path = output / metadata["url"]
        assert metadata["bytes"] == path.stat().st_size
        assert metadata["sha256"] == sha256(path)

    full = json.loads((output / "full" / "manifest.json").read_text())
    assert full["schema"] == "modo-browser-csr-v1"
    assert full["directed"] is True
    assert full["vertices"] == 6
    assert full["arcs"] == 10
    for metadata in full["arrays"].values():
        path = output / "full" / metadata["url"]
        assert metadata["bytes"] == path.stat().st_size
        assert metadata["sha256"] == sha256(path)

    completed = subprocess.run(
        [
            "node",
            str(EXPERIMENT / "tests" / "verify.mjs"),
            str(output / "build-summary.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["passed"] is True
