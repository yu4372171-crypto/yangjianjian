"""Separate local/API routes, with serial local fallback and safe provenance."""
import json
import os
from pathlib import Path
import threading
import time
from contextlib import contextmanager
import sys
if "_aive_requirement_models" in sys.modules:
    _load = sys.modules["_aive_requirement_models"]._load
else:
    from requirement_models import _load

ROOT = Path(os.environ.get("AIVE_API_STATE_ROOT", Path(__file__).resolve().parent / "runtime")) / "ai_scheduler"
_lock = threading.RLock()
_execution = threading.local()


@contextmanager
def job_budget(max_calls=100):
    if type(max_calls) is not int or not 1 <= max_calls <= 500:
        _fail("单次任务 API 调用上限须为 1–500 次")
    previous=getattr(_execution,'budget',None)
    _execution.budget={'limit':max_calls,'calls':0,'started':time.monotonic()}
    try:
        yield
    finally:
        _execution.budget=previous


def budget_usage():
    budget=getattr(_execution,'budget',None)
    return ({'apiCalls':budget['calls'],'limit':budget['limit'],
             'elapsedSeconds':round(time.monotonic()-budget['started'],2),
             'costKnown':False} if budget else {'apiCalls':0,'costKnown':False})


def _fail(message):
    raise _load("api_connections").ConnectionError("AI_SCHEDULER_INVALID", message)


def _kind(kind):
    if kind not in {"vision", "language"}:
        _fail("请选择视觉或语言调度")
    return kind


def _state():
    path = _load("api_connections")._safe_path(ROOT / "routes.json")
    try:
        state = json.loads(path.read_text("utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def _local_status(kind):
    return _load("local_vision" if kind == "vision" else "language_models").get_status()


def get_scheduler_status(kind):
    _kind(kind)
    with _lock:
        route = _state().get(kind, {})
    mode = route.get("mode", "local")
    if mode not in {"local", "api", "auto"}:
        mode = "local"
    local = _local_status(kind)
    local_id = route.get("localModelId") or local.get("selectedModel") or ""
    local_ready = bool(local.get("ready") and any(m["id"] == local_id for m in local.get("models", [])))
    connection, error = None, ""
    if route.get("connectionId"):
        try:
            connection = _load("api_connections").get_connection(route["connectionId"])
        except RuntimeError:
            error = "原 API 连接不存在，请重新选择"
    model = route.get("model") or (connection or {}).get("model") or ""
    api_ready = bool(connection and connection["kind"] == kind and model in connection["testedModels"])
    ready = local_ready if mode == "local" else api_ready if mode == "api" else api_ready or local_ready
    return {"kind": kind, "mode": mode, "connectionId": route.get("connectionId", ""),
            "model": model, "localModelId": local_id, "localReady": local_ready, "apiReady": api_ready,
            "ready": ready, "connection": connection,
            "message": ("本地模型已准备好" if local_ready else "请下载本地模型或添加 API 连接") if mode == "local" else
            (("自动：优先 " if mode == "auto" else "API：") + connection["name"] + " / " + model)
            if api_ready else "自动：当前将使用可用本地模型" if mode == "auto" and local_ready else
            error or "请添加并检测对应类别的 API 模型"}


def select_scheduler(kind, mode, connection_id=None, local_model_id=None, model=None):
    _kind(kind)
    if mode not in {"local", "api", "auto"}:
        _fail("调度方式必须是本地、API 或自动")
    with _lock:
        state = _state()
        old = state.get(kind, {})
        row = dict(old, mode=mode)
        if connection_id is not None:
            row["connectionId"] = connection_id
        if model is not None:
            row["model"] = model
        if mode in {"api", "auto"}:
            connection = None
            if row.get("connectionId"):
                connection = _load("api_connections").get_connection(row["connectionId"])
            selected = model or (old.get("model") if connection and old.get("connectionId") == connection["id"] else None) or (connection or {}).get("model", "")
            verified = connection and connection["kind"] == kind and selected in connection["testedModels"]
            if connection and connection["kind"] != kind:
                _fail("请选择同类别的 API 连接")
            if not verified and (mode == "api" or not _local_status(kind).get("ready")):
                _fail("请选择同类别中已通过检测的 API 模型，或准备可用的本地模型")
            row["model"] = selected
        if local_model_id is not None:
            local = _local_status(kind)
            if local_model_id and local_model_id not in {m["id"] for m in local["models"]}:
                _fail("所选本地模型尚未安装")
            row["localModelId"] = local_model_id
        state[kind] = row
        ac = _load("api_connections")
        path = ac._safe_path(ROOT / "routes.json")
        ROOT.mkdir(parents=True, exist_ok=True)
        temporary = ac._safe_path(ROOT / "routes.json.partial")
        temporary.write_text(json.dumps(state), "utf-8")
        os.replace(temporary, path)
    return get_scheduler_status(kind)


def last_execution(kind):
    return dict(getattr(_execution, kind, {}))


def clear_execution(kind):
    setattr(_execution, _kind(kind), {})


def freeze_route(kind, mode=None):
    """Private immutable-by-convention snapshot for an entire turn/video job."""
    status = get_scheduler_status(kind)
    status["mode"] = mode or status["mode"]
    if status["mode"] in {"api", "auto"} and status["apiReady"]:
        ac = _load("api_connections")
        try:
            status["connection"] = ac.runtime_connection(status["connectionId"],
                status["connection"]["configurationRevision"], model=status["model"], require_verified=True)
        except ac.ConnectionError:
            if status["mode"] == "api":
                raise
            status.update(apiReady=False, connection=None)
    return status


@contextmanager
def execution_session(kind, mode=None):
    sessions = dict(getattr(_execution, "sessions", {}))
    previous = sessions.get(kind)
    sessions[kind] = freeze_route(kind, mode)
    _execution.sessions = sessions
    try:
        yield
    finally:
        if previous is None:
            sessions.pop(kind, None)
        else:
            sessions[kind] = previous
        _execution.sessions = sessions


def _run(kind, api_call, local_call, control, mode=None, route=None):
    provider = _load("openai_compatible")
    provider._check(control)
    setattr(_execution, kind, {})
    status = route or getattr(_execution, "sessions", {}).get(kind) or freeze_route(kind, mode)
    mode = status["mode"]
    failure = ""
    if mode in {"api", "auto"} and status["apiReady"]:
        budget=getattr(_execution,'budget',None)
        if budget is not None:
            if budget['calls'] >= budget['limit']:
                raise provider.ProviderError('API_BUDGET_EXCEEDED','已达到本次任务 API 调用上限；已保存完成阶段，可调整上限后重新生成。')
            budget['calls']+=1
        connection = dict(status["connection"], model=status["model"])
        try:
            result = api_call(connection)
            metadata = {"executedProvider": "api", "connectionId": connection["id"],
                        "connectionName": connection["name"], "model": status["model"],
                        "localFallbackUsed": False, "failureCode": ""}
            setattr(_execution, kind, metadata)
            return result, metadata
        except provider.ProviderError as error:
            provider._check(control)
            if mode == "api" or error.code == "API_CANCELLED":
                raise
            failure = error.code
    elif mode == "api":
        _fail(status["message"])
    elif mode == "auto":
        failure = "API_UNAVAILABLE"
    provider._check(control)
    if mode != "local" and not status["localReady"]:
        _fail("API 不可用，且本地模型未准备好；请检测 API 或下载本地模型")
    result = local_call(status["localModelId"])
    provider._check(control)
    metadata = {"executedProvider": "local", "connectionId": "", "connectionName": "本地模型",
                "model": status["localModelId"], "localFallbackUsed": mode == "auto", "failureCode": failure}
    setattr(_execution, kind, metadata)
    return result, metadata


def run_language(messages, schema, *, control=None, progress=None, reasoning=False, local_call, mode=None, route=None):
    return _run("language", lambda c: _load("openai_compatible").complete_json(
        c, messages, schema, control=control, progress=progress, reasoning=reasoning), local_call, control, mode, route)


def run_vision(frames, prompt, schema, *, control=None, progress=None, local_call, mode=None, route=None):
    return _run("vision", lambda c: _load("openai_compatible").analyze_images(
        c, frames, prompt, schema, control=control, progress=progress), local_call, control, mode, route)
