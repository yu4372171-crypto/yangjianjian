"""Customer-owned API connections. Only DPAPI ciphertext is persisted."""
from __future__ import annotations

import base64
import ctypes
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(os.environ.get("AIVE_API_STATE_ROOT", Path(__file__).resolve().parent / "runtime")) / "api_connections"
_lock = threading.RLock()
_ID = re.compile(r"^conn-[a-f0-9]{32}$")
_ephemeral = {}
_FIELDS = {"id", "kind", "name", "preset", "baseUrl", "models", "model", "apiKey",
           "protocol", "timeoutSeconds", "maxOutputTokens", "endpoints", "headers"}


class ConnectionError(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def fail(message, code="API_CONNECTION_INVALID"):
    raise ConnectionError(code, message)


def now():
    return datetime.now(timezone.utc).isoformat()


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_base_url(value):
    if (not isinstance(value, str) or not value or len(value) > 2048 or
            re.search(r"[\s\\\x00-\x1f\x7f]", value)):
        fail("服务地址无效，请填写完整的 https 地址")
    try:
        p = urlsplit(value)
        port = p.port
        if (p.scheme not in {"https", "http"} or not p.hostname or p.username is not None or
                p.password is not None or p.query or p.fragment or "%" in p.netloc or
                (p.scheme == "http" and not is_loopback(p.hostname))):
            fail("公网服务必须使用 HTTPS，且地址不能包含账号、查询参数或片段")
        if p.path and any(s in {".", ".."} for s in p.path.split("/")):
            fail("服务地址不能包含相对路径")
        host = p.hostname.lower()
        netloc = "[" + host + "]" if ":" in host else host
        if port:
            netloc += ":" + str(port)
        return urlunsplit((p.scheme, netloc, p.path.rstrip("/"), "", ""))
    except (ValueError, UnicodeError):
        fail("服务地址或端口无效")


def endpoint_url(connection, key):
    base = validate_base_url(connection["baseUrl"])
    path = connection.get("endpoints", {}).get(key, "")
    if not path:
        return base + ("/models" if key == "models" else "/chat/completions")
    target = validate_base_url(base + path if path.startswith("/") else path)
    a, b = urlsplit(base), urlsplit(target)
    if (a.scheme, a.hostname, a.port) != (b.scheme, b.hostname, b.port):
        fail("额外端点必须与服务地址使用相同的协议、主机和端口")
    return target


def normalize_models(value):
    if isinstance(value, str):
        value = re.split(r"[,，\n]", value)
    if not isinstance(value, list) or len(value) > 64:
        fail("最多选择 64 个模型")
    models = []
    for item in value:
        if not isinstance(item, str):
            fail("模型 ID 必须是文字")
        item = item.strip()
        if not item:
            continue
        if len(item) > 200 or not re.fullmatch(r"[A-Za-z0-9_./:@+~-]+", item):
            fail("模型 ID 包含无效字符")
        if item not in models:
            models.append(item)
    return models


def _safe_path(path):
    # Reject junctions as well as symlinks, including the configured root.
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
                fail("API 配置目录不能是目录链接", "API_STORAGE_INVALID")
    return path


def _path(identifier):
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        fail("连接编号无效")
    return _safe_path(ROOT / (identifier + ".json"))


def _read(identifier):
    path = _path(identifier)
    try:
        if path.stat().st_size > 512 * 1024:
            fail("连接文件过大", "API_STORAGE_INVALID")
        row = json.loads(path.read_text("utf-8"))
        if row["id"] != identifier:
            fail("连接文件无效", "API_STORAGE_INVALID")
        return row
    except (OSError, ValueError, KeyError, TypeError):
        fail("连接不存在或文件已损坏", "API_CONNECTION_MISSING")


def _write(row):
    row = {k: v for k, v in row.items() if not k.startswith("_")}
    target = _path(row["id"])
    ROOT.mkdir(parents=True, exist_ok=True)
    temporary = _safe_path(ROOT / (row["id"] + "." + secrets.token_hex(8) + ".partial"))
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False))
            stream.flush()
            os.fsync(stream.fileno())
        _safe_path(target)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(value, decrypt=False):
    if os.name != "nt":
        # Development-only, process-bound storage; never persist plaintext.
        if decrypt:
            if value not in _ephemeral:
                fail("该系统的临时密钥已失效，请重新填写", "API_KEY_UNAVAILABLE")
            return _ephemeral[value]
        token = secrets.token_hex(32)
        _ephemeral[token] = value
        return token
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    source = _Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        fail("Windows 无法读取或保护此账号的 API 密钥，请重新填写", "API_KEY_UNAVAILABLE")
    try:
        result = ctypes.string_at(output.pbData, output.cbData)
        return result.decode("utf-8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _fingerprint(row):
    data = {k: row.get(k) for k in ("kind", "baseUrl", "models", "protocol", "secret",
                                   "endpoints", "headers", "timeoutSeconds", "maxOutputTokens")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _public(row):
    result = {k: v for k, v in row.items() if k not in {"secret", "tests"} and not k.startswith("_")}
    fingerprint = _fingerprint(row)
    result["configurationRevision"] = fingerprint
    result["testedModels"] = [m for m in row["models"] if row.get("tests", {}).get(m, {}).get("fingerprint") == fingerprint]
    result["verified"] = bool(result["testedModels"])
    result["hasKey"] = bool(row.get("secret"))
    result["verifiedAt"] = max((row["tests"][m]["at"] for m in result["testedModels"]), default="")
    result["detectedProtocol"] = row["protocol"]
    result["protocolState"] = "ready" if result["verified"] else "untested"
    return result


def prepare_connection(form):
    """Validate a one-use form; its secret is never returned through RPC."""
    with _lock:
        return _prepare_connection(form)


def _prepare_connection(form):
    if not isinstance(form, dict) or set(form) - _FIELDS:
        fail("连接参数包含不支持的字段")
    old = _read(form["id"]) if form.get("id") else {}
    kind = form.get("kind", old.get("kind"))
    if kind not in {"vision", "language"}:
        fail("请选择视觉或语言用途")
    name = form.get("name", old.get("name", ""))
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        fail("请填写供应商名称（100 字以内）")
    protocol = form.get("protocol", old.get("protocol", "openai-compatible"))
    if protocol != "openai-compatible":
        fail("此版本可执行 OpenAI 兼容协议；请填写兼容接口地址")
    row = dict(old, id=old.get("id") or "conn-" + secrets.token_hex(16), kind=kind,
               name=name.strip(), preset=str(form.get("preset", old.get("preset", "custom")))[:60],
               baseUrl=validate_base_url(form.get("baseUrl", old.get("baseUrl", ""))),
               models=normalize_models(form.get("models", old.get("models", []))), protocol=protocol)
    row["model"] = form.get("model", row["models"][0] if row["models"] else "")
    if row["model"] and row["model"] not in row["models"]:
        fail("当前模型必须在所选模型列表中")
    for key, default, low, high in (("timeoutSeconds", 120, 5, 300), ("maxOutputTokens", 4096, 128, 16384)):
        value = form.get(key, old.get(key, default))
        if type(value) is not int or not low <= value <= high:
            fail("超时或最大输出长度超出允许范围")
        row[key] = value
    row["endpoints"] = form.get("endpoints", old.get("endpoints", {}))
    if not isinstance(row["endpoints"], dict) or set(row["endpoints"]) - {"models", "chat"}:
        fail("额外端点参数无效")
    for key in ("models", "chat"):
        if not isinstance(row["endpoints"].get(key, ""), str):
            fail("额外端点参数无效")
        endpoint_url(row, key)
    headers = form.get("headers", old.get("headers", {}))
    if (not isinstance(headers, dict) or set(headers) - {"OpenAI-Organization", "OpenAI-Project"} or
            any(not isinstance(v, str) or len(v) > 200 or re.search(r"[\r\n\x00]", v) for v in headers.values())):
        fail("额外请求头仅支持 OpenAI-Organization 与 OpenAI-Project")
    row["headers"] = headers
    key = form.get("apiKey", "")
    if not isinstance(key, str) or len(key) > 8192 or re.search(r"[\x00-\x20\x7f]", key):
        fail("API 密钥格式无效，请去掉空格和换行")
    if key:
        row["secret"] = _dpapi(key)
    elif not row.get("secret") and not is_loopback(urlsplit(row["baseUrl"]).hostname):
        fail("请填写 API 密钥")
    row.setdefault("secret", "")
    row.setdefault("tests", {})
    row.setdefault("icon", "builtin:" + kind)
    row["updatedAt"] = now()
    row["_baseRevision"] = _fingerprint(old) if old else None
    return row


def save_connection(form):
    with _lock:
        row = prepare_connection(form)
        _write(row)
        return _public(row)


def save_tested_connection(row, models):
    """Internal commit after inference tests, never accepts client verification."""
    with _lock:
        row = dict(row)
        expected = row.get("_baseRevision", _fingerprint(row))
        path = _path(row["id"])
        current = _read(row["id"]) if path.exists() else None
        if (expected is None and current is not None or
                expected is not None and (current is None or _fingerprint(current) != expected)):
            fail("检测期间连接已被修改或删除，请重新检测后保存", "API_CONTEXT_CHANGED")
        fingerprint = _fingerprint(row)
        row["tests"] = dict(row.get("tests", {}))
        for model in models:
            if model in row["models"]:
                row["tests"][model] = {"fingerprint": fingerprint, "at": now()}
        _write(row)
        return _public(row)


def list_connections(kind=None):
    if kind is not None and kind not in {"vision", "language"}:
        fail("连接类别无效")
    with _lock:
        _safe_path(ROOT)
        rows = []
        if ROOT.exists():
            for path in sorted(ROOT.glob("conn-*.json")):
                try:
                    row = _read(path.stem)
                    if kind is None or row["kind"] == kind:
                        rows.append(_public(row))
                except (ConnectionError, KeyError, TypeError):
                    continue
        return rows


def get_connection(identifier):
    with _lock:
        return _public(_read(identifier))


def get_secret(identifier):
    with _lock:
        return secret_for(_read(identifier))


def runtime_connection(identifier, expected_revision, *, model=None, require_verified=False):
    """Return one private, version-bound configuration/secret snapshot."""
    with _lock:
        row = _read(identifier)
        if not expected_revision or _fingerprint(row) != expected_revision:
            fail("API 配置已变化，请重新选择或重新检测", "API_CONTEXT_CHANGED")
        public = _public(row)
        if require_verified and model not in public["testedModels"]:
            fail("此模型尚未通过当前配置的检测", "API_MODEL_UNVERIFIED")
        return dict(public, model=model or row["model"], apiKey=secret_for(row))


def secret_for(row):
    return _dpapi(row["secret"], decrypt=True) if row.get("secret") else ""


def mark_verified(identifier, model, expected_revision=None):
    with _lock:
        row = _read(identifier)
        if expected_revision is not None and _fingerprint(row) != expected_revision:
            fail("检测期间连接已变化，请重新检测", "API_CONTEXT_CHANGED")
        if model not in row["models"]:
            fail("检测的模型不在此连接中")
        return save_tested_connection(row, [model])


def delete_connection(identifier):
    with _lock:
        _read(identifier)
        _path(identifier).unlink()
        return {"removed": True}


def set_icon(identifier, source):
    import io
    with _lock:
        row = _read(identifier)
        if isinstance(source, str) and source.startswith("builtin:"):
            if source not in {"builtin:vision", "builtin:language", "builtin:provider"}:
                fail("内置图标无效")
            row["icon"] = source
        else:
            try:
                from PIL import Image
                if isinstance(source, str) and source.startswith("data:image/"):
                    prefix, encoded = source.split(",", 1)
                    if prefix not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
                        fail("图标只支持 PNG、JPEG 和 WEBP")
                    raw = base64.b64decode(encoded, validate=True)
                else:
                    path = _safe_path(Path(source))
                    if not path.is_file() or path.stat().st_size > 256 * 1024:
                        fail("图标不能超过 256KB")
                    raw = path.read_bytes()
                if len(raw) > 256 * 1024:
                    fail("图标不能超过 256KB")
                image = Image.open(io.BytesIO(raw))
                if image.format not in {"PNG", "JPEG", "WEBP"} or max(image.size) > 1024:
                    fail("图标格式或尺寸不支持（最大 1024 像素）")
                image.load()
                image.thumbnail((128, 128))
                output = io.BytesIO()
                image.convert("RGBA").save(output, "PNG")
                row["icon"] = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
            except ConnectionError:
                raise
            except Exception:
                fail("无法读取此图片，请选择有效的 PNG、JPEG 或 WEBP")
        _write(row)
        return _public(row)
