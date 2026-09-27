"""The README's agent-facing example runs, and its local links resolve."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

pytestmark = pytest.mark.skipif(
    not README.is_file(), reason="needs a source checkout with README.md"
)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start : nxt if nxt != -1 else None]


def test_the_agent_example_runs():
    """The python block under "For AI agents" is executed as written."""
    section = _section(README.read_text(), "## For AI agents")
    (block,) = re.findall(r"```python\n(.*?)```", section, re.DOTALL)
    exec(compile(block, "README.md:For AI agents", "exec"), {})


def test_relative_links_point_at_existing_files():
    text = README.read_text()
    targets = re.findall(r"\]\(([^)#\s]+)\)", text)
    local = [t for t in targets if not re.match(r"[a-z]+:", t)]
    missing = [t for t in local if not (REPO_ROOT / t).exists()]
    assert local, "expected some relative links to check"
    assert not missing, f"README links to missing files: {missing}"


def test_in_page_anchors_match_a_heading():
    text = README.read_text()
    slugs = {
        re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")
        for h in re.findall(r"^#+ (.+)$", text, re.MULTILINE)
    }
    anchors = re.findall(r"\]\(#([^)]+)\)", text)
    assert "for-carbon-based-contributors" in anchors
    assert not [a for a in anchors if a not in slugs]
