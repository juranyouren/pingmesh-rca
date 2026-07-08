from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_baseline_entrypoints_respect_pingmesh_results_env():
    files = [
        ROOT / "Baseline" / "TraceRCA" / "TraceRCAnalyzer.py",
        ROOT / "Baseline" / "NetEventCause" / "NECAnalyzer.py",
        ROOT / "Baseline" / "BiAn" / "BiAnalyzer.py",
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert 'os.environ.get("PINGMESH_RESULTS"' in text


def test_bian_entrypoint_reads_npu_argument():
    text = (ROOT / "Baseline" / "BiAn" / "BiAnalyzer.py").read_text(encoding="utf-8")

    assert "sys.argv[2]" in text
    assert "available_npus =" in text
