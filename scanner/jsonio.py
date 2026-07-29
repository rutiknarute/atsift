"""Atomic JSON reads and writes for the on-disk stores."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return default


def write_json(path: Path, payload) -> None:
    """
    Write via a temp file and rename.

    A scan writes stores while the API reads them; a half-written file would be
    served as corrupt JSON. Rename on the same filesystem is atomic.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name,
        suffix=".tmp",
        delete=False,
    )

    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass

        raise
