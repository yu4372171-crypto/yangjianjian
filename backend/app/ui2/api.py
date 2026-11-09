"""Action dispatcher used by the private desktop protocol."""

from __future__ import annotations

from pathlib import Path

from app import __version__
from app.ui2.common import BridgeError, json_value
from app.ui2.compatibility import (
    ConversationActions,
    CopywritingActions,
    EditingActions,
    HistoryActions,
    MaterialActions,
    ResourceActions,
    SpeechActions,
    VisualActions,
)
from app.ui2.licensing import LicenseActions
from app.ui2.projects import ProjectActions
from app.ui2.settings import SettingsActions
from app.ui2.tasks import TaskRegistry


class BusinessAPI:
    def __init__(self, ctx, services, emit):
        self.ctx = ctx
        self.services = services
        self.emit = emit
        self.version = __version__
        self.tasks = TaskRegistry(emit, int(ctx.settings.get("ai_concurrency", 2)))
        self.groups = {
            "project": ProjectActions(self),
            "settings": SettingsActions(self),
            "material": MaterialActions(self),
            "resource": ResourceActions(self),
            "editing": EditingActions(self),
            "copywriting": CopywritingActions(self),
            "visual": VisualActions(self),
            "conversation": ConversationActions(self),
            "speech": SpeechActions(self),
        }
        self.licensing = LicenseActions(self)
        self.groups["license"] = self.licensing
        try:
            from video_tools import VideoActions

            self.groups["video"] = VideoActions(self)
        except Exception as error:
            raise RuntimeError(f"视频剪辑引擎加载失败：{error}") from error
        self.groups["history"] = HistoryActions(self)

    def invoke(self, action, data):
        self.licensing.authorize(action)
        prefix, _, verb = action.partition(".")
        if prefix == "app":
            if verb == "getLicense":
                return self.licensing.state()
            if verb == "bootstrap":
                if self.ctx.public_project() is None:
                    self.ctx.ensure_default_project()
                return {
                    "version": self.version,
                    "name": "羊剪剪",
                    "project": self.project_current(),
                    "recent": self.groups["project"].project_getRecent({}),
                    "tasks": self.tasks.list(),
                    "settings": self.groups["settings"].get(),
                    "license": self.licensing.state(),
                    "actions": self.action_list(),
                }
            if verb == "shutdown":
                self.tasks.close()
                return True
        if prefix == "dashboard" and verb == "get":
            materials = self.groups["material"].material_getList(
                {"page": 1, "pageSize": 500}
            )["items"]
            return {
                "project": self.project_current(),
                "counts": {
                    "videos": sum(row.get("kind") == "video" for row in materials),
                    "images": sum(row.get("kind") == "image" for row in materials),
                    "scripts": len(
                        self.groups["copywriting"].copywriting_getList({})
                    ),
                    "audio": sum(row.get("kind") == "audio" for row in materials),
                    "generated": self.groups["history"].history_getList({})["total"],
                    "today": 0,
                },
                "recent": [],
                "speech": {},
            }
        if prefix == "task":
            if verb == "getList":
                return self.tasks.list()
            if verb in {"pause", "resume", "cancel"}:
                return self.tasks.control(data["taskId"], verb)
            if verb == "cancelAll":
                active = self.tasks.active()
                for row in active:
                    self.tasks.control(row["taskId"], "cancel")
                return len(active)
        group = self.groups.get(prefix)
        if group is not None:
            method = getattr(group, prefix + "_" + verb, None)
            if callable(method):
                result = method(data)
                if not verb.startswith("get") and action not in {
                    "license.login",
                    "license.logout",
                    "editing.saveEditorState",
                }:
                    self.emit("data.changed", {"category": prefix})
                return json_value(result)
        raise BridgeError("UNKNOWN_ACTION", f"尚未注册的接口：{action}")

    def project_current(self):
        return self.ctx.public_project()

    def action_list(self):
        actions = [
            "app.bootstrap",
            "app.shutdown",
            "app.getLicense",
            "dashboard.get",
            "task.getList",
            "task.pause",
            "task.resume",
            "task.cancel",
            "task.cancelAll",
        ]
        for prefix, group in self.groups.items():
            for name in dir(group):
                if name.startswith(prefix + "_") and callable(getattr(group, name)):
                    actions.append(name.replace(prefix + "_", prefix + ".", 1))
        return sorted(set(actions))
