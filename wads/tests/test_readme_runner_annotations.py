"""README blocks run with real annotations, not ones postponed by the runner's own __future__ import."""

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).parents[1]
    / "data/skills/wads-docs-coverage/scripts/readme_runner.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_readme_runner_under_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exec_block_annotations_are_not_postponed():
    rr = _load()
    text = "```python\ndef f(x: int): ...\nassert f.__annotations__['x'] is int\n```\n"
    blocks = rr.extract_blocks(text)
    results = rr.run_blocks(blocks, "README.md", 10)
    assert [r["status"] for r in results] == ["PASS"], results
