"""Provider management RPCs. Customer credentials remain behind the bridge."""
import sys
import time
if "_aive_requirement_models" in sys.modules:
    _load = sys.modules["_aive_requirement_models"]._load
else:
    from requirement_models import _load


def _bridge(call):
    try:
        return call()
    except RuntimeError as error:
        from app.ui2.common import BridgeError
        raise BridgeError(getattr(error, "code", "API_ERROR"), getattr(error, "message", "API 操作失败")) from None


def delete_connection(identifier):
    for kind in ("vision", "language"):
        status = _load("ai_scheduler").get_scheduler_status(kind)
        if status["mode"] != "local" and status["connectionId"] == identifier:
            _load("api_connections").fail("此连接正在使用，请先切换为本地或其他 API", "API_CONNECTION_ACTIVE")
    return _load("api_connections").delete_connection(identifier)


def _form(data):
    ac = _load("api_connections")
    if not isinstance(data, dict):
        ac.fail("API 参数无效")
    if set(data) <= {"id", "model"} and data.get("id"):
        with ac._lock:
            row = dict(ac._read(data["id"]))
        row["_baseRevision"] = ac._fingerprint(row)
        if data.get("model"):
            if data["model"] not in row["models"]:
                ac.fail("请选择此连接中的模型")
            row["model"] = data["model"]
    else:
        row = ac.prepare_connection(data)
    return row


def _runtime(row):
    return dict(row, apiKey=_load("api_connections").secret_for(row))


def test_models(row, control=None, progress=None):
    op = _load("openai_compatible")
    test = op.test_vision if row["kind"] == "vision" else op.test_language
    results, passed = [], []
    for index, model in enumerate(row["models"]):
        op._check(control)
        if progress:
            progress(int(index * 95 / len(row["models"])), "检测模型 %s（%s/%s）" % (model, index + 1, len(row["models"])))
        try:
            started=time.monotonic()
            test(dict(_runtime(row), model=model), control=control)
            passed.append(model)
            seconds=round(time.monotonic()-started,2)
            results.append({"model": model, "success": True, "elapsedSeconds":seconds,
                            "message": f"真实推理通过 · {seconds:g} 秒"})
        except op.ProviderError as error:
            if error.code == "API_CANCELLED":
                raise
            results.append({"model": model, "success": False, "code": error.code, "message": error.message})
    return {"success": bool(passed), "models": results, "passed": passed}


def save_form(data, control=None, progress=None):
    ac = _load("api_connections")
    row = _form(data)
    if not row["models"]:
        ac.fail("请先获取模型，或直接填写模型 ID")
    result = test_models(row, control, progress)
    if not result["success"]:
        ac.fail("没有模型通过检测：" + result["models"][0]["message"], "API_TEST_FAILED")
    if row["model"] not in result["passed"]:
        row["model"] = result["passed"][0]
    _load("openai_compatible")._check(control)
    return {"connection": ac.save_tested_connection(row, result["passed"]), "test": result}


class ApiConnectionsMixin:
    def video_benchmarkModel(self,data):
        kind=data.get('kind')
        if kind not in ('language','vision'):
            return _bridge(lambda:_load('api_connections').fail('请选择语言或视觉模型'))
        def work(progress,control):
            return _bridge(lambda:_load('model_benchmark').run(_load,kind,control,progress))
        return self.api.tasks.start('模型实测',work,category='model',location={'route':'/settings'})

    def video_apiConnections(self, data):
        return _bridge(lambda: {"items": _load("api_connections").list_connections(data.get("kind"))})

    def video_apiConnectionSave(self, data):
        return _bridge(lambda: save_form(data))

    def video_apiConnectionSaveStart(self, data):
        # Capture only validated fields and encrypted one-use credentials.
        row = _bridge(lambda: _form(data))
        def work(progress, control):
            result = test_models(row, control, progress)
            ac = _load("api_connections")
            if not result["success"]:
                ac.fail("没有模型通过检测：" + (result["models"][0]["message"] if result["models"] else "请填写模型 ID"), "API_TEST_FAILED")
            if row["model"] not in result["passed"]:
                row["model"] = result["passed"][0]
            _load("openai_compatible")._check(control)
            return {"connection": ac.save_tested_connection(row, result["passed"]), "test": result}
        return self.api.tasks.start("检测并保存 API 连接", work, category="model", location={"route": "/settings"})

    def video_apiConnectionDelete(self, data):
        return _bridge(lambda: delete_connection(data.get("id")))

    def video_apiDetectProtocol(self, data):
        def detect():
            form = dict(data)
            probe = form.pop("probeModel", "")
            row = _form(form)
            return _load("openai_compatible").detect_protocol(row["baseUrl"],
                _load("api_connections").secret_for(row), probe, connection=row)
        return _bridge(detect)

    def video_apiModels(self, data):
        def models():
            row = _form(data)
            return {"models": _load("openai_compatible").list_models(row["baseUrl"],
                _load("api_connections").secret_for(row), connection=row), "source": "api"}
        return _bridge(models)

    def video_apiTestModel(self, data):
        def test():
            row = _form(data)
            revision = _load("api_connections")._fingerprint(row)
            if data.get("model"):
                row["models"] = [data["model"]]
            result = test_models(row)
            # Testing a saved model refreshes its verification but does not change routes.
            if set(data) <= {"id", "model"} and data.get("id") and result["passed"]:
                for model in result["passed"]:
                    _load("api_connections").mark_verified(data["id"], model, revision)
            return result
        return _bridge(test)

    def video_apiTestStart(self, data):
        # Freeze the validated draft before queuing; only the task closure holds its secret.
        row = _bridge(lambda: _form(data))
        def work(progress, control):
            return _bridge(lambda: test_models(row, control, progress))
        return self.api.tasks.start("检测 API 模型", work, category="model", location={"route": "/settings"})

    def video_apiConnectionIcon(self, data):
        return _bridge(lambda: _load("api_connections").set_icon(data.get("id"), data.get("source")))

    def video_apiWebsiteIcon(self, data):
        def fetch():
            import base64
            import io
            import urllib.request
            from urllib.parse import urlsplit
            from PIL import Image
            ac = _load("api_connections")
            base = urlsplit(ac.validate_base_url(data.get("baseUrl")))
            url = base.scheme + "://" + base.netloc + "/favicon.png"
            handlers = [_load("openai_compatible")._NoRedirect()]
            if ac.is_loopback(base.hostname):
                handlers.append(urllib.request.ProxyHandler({}))
            try:
                with urllib.request.build_opener(*handlers).open(url, timeout=10) as response:
                    raw = response.read(256 * 1024 + 1)
                if len(raw) > 256 * 1024:
                    raise ValueError()
                image = Image.open(io.BytesIO(raw))
                if image.format not in {"PNG", "JPEG", "WEBP"} or max(image.size) > 1024:
                    raise ValueError()
                image.load()
                image.thumbnail((128, 128))
                output = io.BytesIO()
                image.convert("RGBA").save(output, "PNG")
                return {"icon": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}
            except Exception:
                ac.fail("该网站没有可直接读取的 PNG 图标，请选择本地图片或内置图标", "API_ICON_UNAVAILABLE")
        return _bridge(fetch)

    def video_schedulerStatus(self, data):
        return _bridge(lambda: _load("ai_scheduler").get_scheduler_status(data.get("kind")))

    def video_schedulerSettings(self, data):
        def configure():
            if not isinstance(data, dict) or set(data) - {"kind", "mode", "connectionId", "localModelId", "model"}:
                _load("api_connections").fail("调度设置参数无效")
            result = _load("ai_scheduler").select_scheduler(data.get("kind"), data.get("mode"),
                data.get("connectionId"), data.get("localModelId"), data.get("model"))
            return result
        return _bridge(configure)
