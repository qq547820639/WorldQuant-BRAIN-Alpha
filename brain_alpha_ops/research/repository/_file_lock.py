"""Exclusive file-lock primitive used by the research repository."""

from __future__ import annotations

import os
import time

from brain_alpha_ops.research.repository._constants import (
    _LOCK_POLL_SECONDS,
    _LOCK_STALE_SECONDS,
)


class _RepositoryFileLock:
    def __init__(self, lock_path: str, timeout_seconds: float = 30.0):
        self.lock_path = lock_path
        self.timeout_seconds = timeout_seconds
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.time() + self.timeout_seconds
        while True:
            try:
                self.fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self.fd, f"{os.getpid()} {time.time()}".encode("ascii"))
                return self
            except FileExistsError:
                self._remove_stale_lock()
                if time.time() >= deadline:
                    raise TimeoutError(f"timed out waiting for repository lock: {self.lock_path}")
                time.sleep(_LOCK_POLL_SECONDS)

    def __exit__(self, _exc_type, _exc, _tb):
        if self.fd is not None:
            try:
                os.close(self.fd)
            finally:
                self.fd = None
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass

    def _remove_stale_lock(self) -> None:
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return
        if age > _LOCK_STALE_SECONDS:
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass
