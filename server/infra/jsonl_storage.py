"""JSONL-backed persistence layer with process-safe file locking."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


@contextmanager
def _locked_file(path: Path, mode: str, shared: bool = False) -> Iterator[Any]:
    """Open *path* and apply an OS-level file lock for the duration."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()

    fh = path.open(mode, encoding="utf-8")
    lock_start = 0
    try:
        if os.name == "nt":
            import msvcrt

            # msvcrt only supports exclusive whole-file locking in this flow.
            fh.seek(lock_start)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 0x7FFF_FFFF)
            if "a" in mode and "r" not in mode:
                fh.seek(0, os.SEEK_END)
        else:
            import fcntl

            lock_kind = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(fh.fileno(), lock_kind)

        yield fh
    finally:
        if os.name == "nt":
            import msvcrt

            fh.flush()
            fh.seek(lock_start)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 0x7FFF_FFFF)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


class JSONLStorage:
    """Simple JSON Lines storage with whole-file locking per mutation."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def read_all(self) -> List[Dict[str, Any]]:
        """Return all records in the JSONL file."""

        with _locked_file(self.path, mode="r", shared=True) as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def write_all(self, records: Iterable[Dict[str, Any]]) -> None:
        """Overwrite the file atomically with *records*."""

        data = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
        with _locked_file(self.path, mode="r+") as fh:
            fh.seek(0)
            if data:
                fh.write(f"{data}\n")
            fh.truncate()

    def append(self, record: Dict[str, Any]) -> None:
        """Append a single JSON object."""

        line = json.dumps(record, ensure_ascii=False)
        with _locked_file(self.path, mode="a") as fh:
            fh.write(f"{line}\n")

    def update_record(self, predicate: Any, updater: Any) -> Optional[Dict[str, Any]]:
        """Replace the first record satisfying *predicate* using *updater* callable.

        Returns the updated record or ``None`` if no record matched.
        """

        with _locked_file(self.path, mode="r+") as fh:
            fh.seek(0)
            records = [json.loads(line) for line in fh if line.strip()]

            for idx, record in enumerate(records):
                if predicate(record):
                    updated = updater(dict(record))
                    records[idx] = updated
                    fh.seek(0)
                    fh.write("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n")
                    fh.truncate()
                    return updated
            return None

    def find_one(self, predicate: Any) -> Optional[Dict[str, Any]]:
        """Return the first record that satisfies *predicate*."""

        with _locked_file(self.path, mode="r", shared=True) as fh:
            for line in fh:
                if not line.strip():
                    continue
                data = json.loads(line)
                if predicate(data):
                    return data
        return None

    def filter(self, predicate: Any) -> List[Dict[str, Any]]:
        """Return a list of records satisfying *predicate*."""

        results: List[Dict[str, Any]] = []
        with _locked_file(self.path, mode="r", shared=True) as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if predicate(data):
                    results.append(data)
        return results
