"""Application-owned background tasks with cooperative pause and cancel."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.ui2.common import BridgeError, json_value
from app.workers.control import CancelledError, TaskControl


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskRegistry:
    def __init__(self, emit, workers: int = 2):
        self.emit = emit
        self._lock = threading.RLock()
        self._tasks: dict[str, dict] = {}
        self._controls: dict[str, TaskControl] = {}
        self._futures: dict[str, object] = {}
        self._workers = max(1, int(workers or 1))
        self._executor = ThreadPoolExecutor(
            max_workers=self._workers,
            thread_name_prefix="yangjianjian-task",
        )

    def list(self) -> list[dict]:
        with self._lock:
            return [json_value(dict(row)) for row in self._tasks.values()]

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            row = self._tasks.get(str(task_id))
            return json_value(dict(row)) if row else None

    def active(self) -> list[dict]:
        return [
            row
            for row in self.list()
            if row["status"] in {"queued", "running", "paused", "cancelling"}
        ]

    def _emit(self, event: str, row: dict) -> None:
        try:
            self.emit(event, json_value(dict(row)))
        except Exception:
            pass

    def _update(self, task_id: str, **values) -> dict:
        with self._lock:
            row = self._tasks[task_id]
            row.update(values)
            row["updatedAt"] = _now()
            return dict(row)

    def start(self, name, work, category="other", location=None):
        task_id = uuid.uuid4().hex
        row = {
            "taskId": task_id,
            "id": task_id,
            "name": str(name or "后台任务"),
            "category": str(category or "other"),
            "status": "queued",
            "progress": 0,
            "message": "等待执行",
            "location": location or {"route": "/tasks"},
            "result": None,
            "error": "",
            "createdAt": _now(),
            "updatedAt": _now(),
        }
        control = TaskControl()
        with self._lock:
            self._tasks[task_id] = row
            self._controls[task_id] = control
        self._emit("task.progress", row)

        def progress(value, message=""):
            try:
                percent = max(0, min(100, int(float(value))))
            except (TypeError, ValueError):
                percent = 0
            with self._lock:
                current = self._tasks[task_id]
                if current["status"] in {"cancelling", "cancelled", "failed"}:
                    return
                current["status"] = "paused" if not control._running.is_set() else "running"
                current["progress"] = max(current["progress"], percent)
                if message:
                    current["message"] = str(message)
                snapshot = dict(current)
            self._emit("task.progress", snapshot)

        def run():
            with self._lock:
                if control.cancelled.is_set():
                    return
                snapshot = self._update(
                    task_id,
                    status="running",
                    message="正在执行",
                )
            self._emit("task.progress", snapshot)
            try:
                result = work(progress, control)
                if control.cancelled.is_set():
                    raise CancelledError("任务已取消")
                with self._lock:
                    snapshot = self._update(
                        task_id,
                        status="done",
                        progress=100,
                        message="已完成",
                        result=json_value(result),
                    )
                self._emit("task.completed", snapshot)
            except CancelledError:
                with self._lock:
                    snapshot = self._update(
                        task_id,
                        status="cancelled",
                        message="任务已取消",
                        error="任务已取消",
                    )
                self._emit("task.failed", snapshot)
            except Exception as error:
                with self._lock:
                    snapshot = self._update(
                        task_id,
                        status="failed",
                        message=str(error) or "任务失败",
                        error=str(error) or "任务失败",
                    )
                self._emit("task.failed", snapshot)
            finally:
                with self._lock:
                    self._futures.pop(task_id, None)

        future = self._executor.submit(run)
        with self._lock:
            self._futures[task_id] = future
        return json_value(dict(row))

    def control(self, task_id, operation):
        task_id = str(task_id)
        with self._lock:
            row = self._tasks.get(task_id)
            control = self._controls.get(task_id)
            if row is None or control is None:
                raise BridgeError("TASK_NOT_FOUND", "任务不存在或已清理")
            if operation == "pause":
                if row["status"] == "running":
                    control.pause()
                    row["status"] = "paused"
                    row["message"] = "已暂停"
            elif operation == "resume":
                if row["status"] in {"paused", "running"}:
                    control.resume()
                    row["status"] = "running"
                    row["message"] = "继续执行"
            elif operation == "cancel":
                if row["status"] not in {"done", "failed", "cancelled"}:
                    control.cancel()
                    row["status"] = "cancelling"
                    row["message"] = "正在取消"
            else:
                raise BridgeError("TASK_OPERATION", "不支持的任务操作")
            row["updatedAt"] = _now()
            snapshot = dict(row)
        self._emit("task.progress", snapshot)
        return json_value(snapshot)

    def close(self) -> None:
        with self._lock:
            for control in self._controls.values():
                control.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
