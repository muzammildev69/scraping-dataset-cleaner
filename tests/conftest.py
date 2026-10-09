"""Shared pytest fixtures."""

from collections.abc import Callable
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def write_text(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes a CSV file inside the temporary directory."""

    def _write(name: str, content: str | bytes, encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding=encoding, newline="")
        return path

    return _write
