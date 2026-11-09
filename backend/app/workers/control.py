"""Framework-independent cooperative cancellation and pause control."""

from __future__ import annotations

import threading


class CancelledError(RuntimeError):
    pass


class TaskControl:
    def __init__(self):
        self.cancelled = threading.Event()
        self._running = threading.Event()
        self._running.set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def cancel(self) -> None:
        self.cancelled.set()
        self._running.set()

    def wait_if_paused(self, timeout: float = 0.25) -> None:
        while not self._running.wait(timeout):
            if self.cancelled.is_set():
                break


def check_control(control) -> None:
    if not control:
        return
    cancel = getattr(control, "cancelled", None)
    if cancel is not None and cancel.is_set():
        raise CancelledError("任务已取消")
    if isinstance(control, dict):
        if control.get("cancelled") or control.get("canceled"):
            raise CancelledError("任务已取消")
        while control.get("paused"):
            if control.get("cancelled") or control.get("canceled"):
                raise CancelledError("任务已取消")
            threading.Event().wait(0.2)
        return
    wait_if_paused = getattr(control, "wait_if_paused", None)
    if callable(wait_if_paused):
        wait_if_paused()
    if cancel is not None and cancel.is_set():
        raise CancelledError("任务已取消")
