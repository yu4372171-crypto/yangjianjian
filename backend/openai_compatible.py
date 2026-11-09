"""Bounded, non-redirecting OpenAI chat transport using customer credentials."""
from __future__ import annotations

import base64
import io
import http.client
import json
import math
import random
import re
import select
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, quote
import sys
if "_aive_requirement_models" in sys.modules:
    _load = sys.modules["_aive_requirement_models"]._load
else:
    from requirement_models import _load


class ProviderError(RuntimeError):
    def __init__(self, code, message, status=None):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _check(control):
    if control and control.get("cancelled") and control["cancelled"].is_set():
        raise ProviderError("API_CANCELLED", "API 请求已取消")


def _key(connection):
    if "apiKey" in connection:
        return connection["apiKey"]
    return _load("api_connections").runtime_connection(
        connection["id"], connection.get("configurationRevision"))["apiKey"]


def _request(connection, endpoint, payload=None, control=None, auth="bearer"):
    _check(control)
    ac = _load("api_connections")
    # Capture address, options and decrypted key from the same stored revision.
    if "apiKey" not in connection:
        try:
            connection = ac.runtime_connection(connection["id"],
                connection.get("configurationRevision"), model=connection.get("model"))
        except ac.ConnectionError as error:
            raise ProviderError(error.code, error.message) from None
    url = ac.endpoint_url(connection, endpoint)
    key = _key(connection)
    headers = {"Accept": "application/json", "Connection": "close", **connection.get("headers", {})}
    if key:
        if auth == "anthropic":
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        elif auth == "gemini":
            headers["x-goog-api-key"] = key
        else:
            headers["Authorization"] = "Bearer " + key
    raw = None
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > 64 * 1024 * 1024:
            raise ProviderError("API_INPUT_TOO_LARGE", "本次请求内容过大，请减少采样帧或对话长度")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=raw, headers=headers)
    response = None
    stopped = threading.Event()
    limit = connection.get("timeoutSeconds", 120)
    deadline = time.monotonic() + limit
    sockets = []

    class CancellableReader(io.RawIOBase):
        def __init__(self, sock):
            self.sock = sock
            # Keep the descriptor alive after urllib closes its connection handle.
            self.keepalive = sock.makefile("rb", buffering=0)

        def readable(self):
            return True

        def readinto(self, buffer):
            while True:
                _check(control)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderError("API_TIMEOUT", "服务响应超时，请检查网络或更换模型")
                pending = isinstance(self.sock, ssl.SSLSocket) and self.sock.pending()
                if not pending and not select.select([self.sock], [], [], min(.1, remaining))[0]:
                    continue
                self.sock.settimeout(min(.2, remaining))
                try:
                    return self.sock.recv_into(buffer)
                except (socket.timeout, ssl.SSLWantReadError):
                    continue

        def close(self):
            self.keepalive.close()
            super().close()

    class ReadingSocket:
        def __init__(self, sock):
            self.sock = sock

        def __getattr__(self, name):
            return getattr(self.sock, name)

        def makefile(self, mode, buffering=None):
            if mode != "rb":
                raise ValueError("unsupported HTTP read mode")
            return io.BufferedReader(CancellableReader(self.sock))

    class TrackedHTTP(http.client.HTTPConnection):
        def connect(self):
            super().connect()
            sockets.append(self.sock)
            _check(control)
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            self.sock = ReadingSocket(self.sock)

    class TrackedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            super().connect()
            sockets.append(self.sock)
            _check(control)
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            self.sock = ReadingSocket(self.sock)

    class HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(TrackedHTTP, req)

    class HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(TrackedHTTPS, req, context=self._context)

    handlers = [_NoRedirect(), HTTPHandler(), HTTPSHandler()]
    if ac.is_loopback(urlsplit(url).hostname):
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)

    def guard():
        # Only a watchdog thread; there is no detached inference worker or retry.
        while not stopped.wait(.1):
            if ((control and control.get("cancelled") and control["cancelled"].is_set())
                    or time.monotonic() >= deadline):
                if response is not None:
                    try:
                        sockets.append(response.fp.raw._sock)
                    except AttributeError:
                        pass
                for sock in list(sockets):
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
                return

    watcher = threading.Thread(target=guard, daemon=True)
    watcher.start()
    try:
        # Connection establishment is bounded even before a response socket exists.
        response = opener.open(request, timeout=min(limit, 10))
        _check(control)
        if response.status != 200:
            raise ProviderError("API_HTTP_ERROR", "服务返回了非成功状态", response.status)
        content_length = response.headers.get("Content-Length", "")
        if content_length and not content_length.isdigit():
            raise ProviderError("API_RESPONSE_INVALID", "服务返回的响应长度无效")
        if content_length.isdigit() and int(content_length) > 4 * 1024 * 1024:
            raise ProviderError("API_RESPONSE_TOO_LARGE", "服务返回内容过大")
        chunks, size = [], 0
        while True:
            _check(control)
            if time.monotonic() > deadline:
                raise ProviderError("API_TIMEOUT", "服务响应超时，请检查网络或更换模型")
            block = response.read1(64 * 1024)
            if not block:
                break
            size += len(block)
            if size > 4 * 1024 * 1024:
                raise ProviderError("API_RESPONSE_TOO_LARGE", "服务返回内容过大")
            chunks.append(block)
        _check(control)
        if content_length and size != int(content_length):
            raise ProviderError("API_RESPONSE_INVALID", "服务返回内容不完整，请检查网络或供应商")
        try:
            return _load("local_vision").parse_response(b"".join(chunks).decode("utf-8"))
        except (RuntimeError, UnicodeError):
            raise ProviderError("API_RESPONSE_INVALID", "服务未返回有效的 JSON 响应") from None
    except urllib.error.HTTPError as error:
        _check(control)
        status = error.code
        error.close()
        messages = {401: "API 密钥无效，请重新填写", 403: "该密钥没有此模型的访问权限",
                    429: "服务限流或余额不足，请检查供应商账户",
                    404: "端点不存在，请检查 Base URL 或手动填写模型 ID",
                    400: "服务拒绝请求，请确认模型支持 OpenAI 兼容聊天与 JSON 输出",
                    302: "服务要求重定向；为保护密钥，请直接填写最终服务地址"}
        raise ProviderError("API_MODELS_UNAVAILABLE" if status in (404, 405) and endpoint == "models" else
                            "API_AUTH" if status in (401, 403) else
                            "API_RATE_LIMIT" if status == 429 else "API_HTTP_ERROR",
                            messages.get(status, "API 服务暂时不可用（HTTP %s）" % status), status) from None
    except (OSError, urllib.error.URLError, ValueError, http.client.HTTPException):
        _check(control)
        if time.monotonic() >= deadline:
            raise ProviderError("API_TIMEOUT", "服务响应超时，请检查网络或更换模型") from None
        raise ProviderError("API_NETWORK", "无法连接 API 服务，请检查地址、网络、代理和超时设置") from None
    finally:
        stopped.set()
        if response is not None:
            response.close()
        for sock in sockets:
            sock.close()
        watcher.join(timeout=1)


def list_models(base_url, api_key, *, connection=None, control=None):
    row = dict(connection or {}, baseUrl=base_url, apiKey=api_key)
    result = _request(row, "models", control=control)
    data = result.get("data")
    if not isinstance(data, list) or len(data) > 10000:
        raise ProviderError("API_MODELS_INVALID", "此接口未提供 OpenAI 格式的模型目录，请直接填写模型 ID")
    models = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        try:
            identifier = _load("api_connections").normalize_models([item["id"]])
        except RuntimeError:
            continue
        if identifier and identifier[0] not in models:
            models.append(identifier[0])
        if len(models) == 1000:
            break
    return models


def detect_protocol(base_url, api_key, probe_model="", *, connection=None, control=None):
    row = dict(connection or {}, baseUrl=base_url, apiKey=api_key, model=probe_model)
    if probe_model:
        try:
            test_language(row, control=control)
        except ProviderError as error:
            if error.status not in (400, 404, 405, 422) and error.code != "API_RESPONSE_INVALID":
                raise
            return _detect_native(row, probe_model, control)
    else:
        try:
            models = list_models(base_url, api_key, connection=row, control=control)
        except ProviderError as error:
            if error.code == "API_MODELS_UNAVAILABLE":
                return {"protocol": "unknown", "state": "needs-model",
                        "message": "服务不提供模型目录，请填写试用模型 ID 后重新检测"}
            raise
        if not models:
            return {"protocol": "unknown", "state": "needs-model", "message": "目录为空，请直接填写模型 ID"}
        # A directory alone is a hint, not permission to execute.
        return {"protocol": "openai-compatible", "state": "needs-test",
                "message": "已读取 OpenAI 兼容模型目录；请逐项检测所选模型"}
    return {"protocol": "openai-compatible", "state": "ready", "message": "已通过 OpenAI 兼容聊天检测"}


def _detect_native(row, model, control):
    """Detect only at the explicitly entered origin; no native execution is enabled."""
    base = _load("api_connections").validate_base_url(row["baseUrl"])
    probes = [
        ("openai-responses", "/responses", "bearer",
         {"model": model, "input": 'Reply {"ready":true}', "max_output_tokens": 64}),
        ("anthropic", "/messages", "anthropic",
         {"model": model, "max_tokens": 64, "messages": [{"role": "user", "content": 'Reply {"ready":true}'}]}),
        ("gemini", "/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent", "gemini",
         {"contents": [{"parts": [{"text": 'Reply {"ready":true}'}]}], "generationConfig": {"maxOutputTokens": 64}}),
    ]
    for protocol, path, auth, payload in probes:
        _check(control)
        candidate = dict(row, endpoints={"chat": base + path})
        try:
            response = _request(candidate, "chat", payload, control, auth)
        except ProviderError as error:
            if error.code in {"API_AUTH", "API_RATE_LIMIT", "API_CANCELLED", "API_NETWORK", "API_TIMEOUT"}:
                raise
            continue
        recognized = ((protocol == "openai-responses" and response.get("object") == "response" and isinstance(response.get("output"), list))
                      or (protocol == "anthropic" and response.get("type") == "message" and isinstance(response.get("content"), list))
                      or (protocol == "gemini" and isinstance(response.get("candidates"), list)))
        if recognized:
            return {"protocol": protocol, "state": "adaptation-required",
                    "message": "已识别 " + protocol + " 原生协议；此版本尚未适配执行，请改填供应商的 OpenAI 兼容地址"}
    return {"protocol": "unknown", "state": "unsupported",
            "message": "尚未识别可执行协议，请核对完整的 OpenAI 兼容地址和模型 ID"}

def _matches(value, schema, depth=0):
    """Validate the bounded application schemas without a new runtime dependency."""
    if depth > 40 or not isinstance(schema, dict):
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if "anyOf" in schema and not any(_matches(value, item, depth + 1) for item in schema["anyOf"]):
        return False
    if "oneOf" in schema and sum(_matches(value, item, depth + 1) for item in schema["oneOf"]) != 1:
        return False
    if "allOf" in schema and not all(_matches(value, item, depth + 1) for item in schema["allOf"]):
        return False
    kind = schema.get("type")
    allowed = kind if isinstance(kind, list) else [kind] if kind else []
    checks = {"object": isinstance(value, dict), "array": isinstance(value, list),
              "string": isinstance(value, str), "boolean": type(value) is bool,
              "number": type(value) in (int, float) and math.isfinite(value),
              "integer": type(value) is int, "null": value is None}
    if allowed and not any(checks.get(item, False) for item in allowed):
        return False
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        for key, item in value.items():
            subschema = properties.get(key, schema.get("additionalProperties", {}))
            if isinstance(subschema, dict) and not _matches(item, subschema, depth + 1):
                return False
    elif isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            return False
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            return False
        if "items" in schema and not all(_matches(item, schema["items"], depth + 1) for item in value):
            return False
    elif isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 200000):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    elif type(value) in (int, float):
        if not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            return False
    return True


def complete_json(connection, messages, schema, *, control=None, progress=None, reasoning=False):
    _check(control)
    if (not isinstance(messages, list) or not 1 <= len(messages) <= 40 or
            not isinstance(schema, dict) or not isinstance(connection.get("model"), str) or not connection["model"]):
        raise ProviderError("API_INPUT_INVALID", "API 模型或对话参数无效")
    for message in messages:
        if (not isinstance(message, dict) or set(message) - {"role", "content"} or
                message.get("role") not in {"system", "user", "assistant"} or
                not isinstance(message.get("content"), (str, list))):
            raise ProviderError("API_INPUT_INVALID", "对话格式无效")
    payload = {"model": connection["model"], "messages": [
        {"role": "system", "content": "Return only a complete JSON object matching this schema. No tools or markdown.\n" +
         json.dumps(schema, ensure_ascii=False)}, *messages],
        "temperature": .1, "max_tokens": connection.get("maxOutputTokens", 4096),
        "response_format": {"type": "json_object"}, "stream": False}
    if progress:
        progress("正在请求所选 API 模型")
    result = _request(connection, "chat", payload, control)
    try:
        choices = result.get("choices")
        if (not isinstance(choices, list) or len(choices) != 1 or
                choices[0].get("finish_reason") != "stop" or
                choices[0].get("message", {}).get("tool_calls") or
                choices[0].get("message", {}).get("refusal")):
            raise ValueError()
        parsed = _load("local_vision").parse_response(choices[0]["message"]["content"])
        if not _matches(parsed, schema):
            raise ValueError()
        return parsed
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        raise ProviderError("API_RESPONSE_INVALID", "模型未返回完整、有效的 JSON 结果；未采用该结果，请更换模型或增加输出长度") from None


def analyze_images(connection, frames, prompt, schema, *, control=None, progress=None):
    engine = _load("local_vision")
    engine._validate_prompt(prompt)
    validated = engine.validate_frames(frames)
    content = [{"type": "text", "text": prompt}]
    for frame in validated:
        content += [{"type": "text", "text": f"Frame index={frame['index']}; time={frame['time']:.3f} seconds"},
                    {"type": "image_url", "image_url": {"url": frame["dataUrl"]}}]
    return complete_json(connection, [{"role": "user", "content": content}], schema,
                         control=control, progress=progress)


def test_language(connection, *, control=None):
    result = complete_json(connection, [{"role": "user", "content": 'Return exactly {"ready":true}.'}],
                           {"type": "object", "properties": {"ready": {"type": "boolean"}},
                            "required": ["ready"], "additionalProperties": False}, control=control)
    if result != {"ready": True}:
        raise ProviderError("API_TEST_FAILED", "模型没有按要求返回检测结果，请更换模型")
    return {"success": True, "message": "语言 JSON 输出检测通过"}


def test_vision(connection, *, control=None):
    from PIL import Image, ImageDraw
    choices = ["red", "green", "blue"]
    random.SystemRandom().shuffle(choices)
    rgb = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}
    image = Image.new("RGB", (192, 64))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(choices):
        draw.rectangle((index * 64, 0, (index + 1) * 64 - 1, 63), fill=rgb[color])
    output = io.BytesIO()
    image.save(output, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
    result = complete_json(connection, [{"role": "user", "content": [
        {"type": "text", "text": "Read the image. Report the three color panels from left to right as colors, "
         "using lowercase English red, green or blue. Return JSON only."},
        {"type": "image_url", "image_url": {"url": data_url}}]}],
        {"type": "object", "required": ["colors"], "additionalProperties": False,
         "properties": {"colors": {"type": "array", "minItems": 3, "maxItems": 3,
                                  "items": {"type": "string", "enum": ["red", "green", "blue"]}}}}, control=control)
    if result != {"colors": choices}:
        raise ProviderError("API_VISION_UNSUPPORTED", "图片内容检测未通过；请确认该模型支持图片输入并能正确识别画面")
    return {"success": True, "message": "真实图片内容与 JSON 输出检测通过"}
