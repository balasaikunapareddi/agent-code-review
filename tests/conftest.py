from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def load_sample(name: str) -> str:
    return (SAMPLES / f"{name}.diff").read_text()


def make_diff(path: str, added: list[str]) -> str:
    """Minimal one-file unified diff whose added lines start at line 1."""
    lines = [
        f"diff --git a/{path} b/{path}",
        f"--- a/{path}",
        f"+++ b/{path}",
        f"@@ -1,0 +1,{len(added)} @@",
    ]
    lines += [f"+{a}" for a in added]
    return "\n".join(lines) + "\n"


@pytest.fixture
def samples_dir() -> Path:
    return SAMPLES
