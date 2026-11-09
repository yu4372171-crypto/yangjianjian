"""First-run download of the pinned public Whisper data files.

No repository code, credentials, package installers or inference engine are used.
Validated files are kept between attempts, incomplete data uses a resumable
``.partial`` file, and the runtime manifest is published only after every pinned
file passes its size and SHA-256 checks.
"""
import hashlib
import importlib.util
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import threading
import sys
import urllib.error
import urllib.parse
import urllib.request

def _load_speech_runtime():
    # PyInstaller does not put the external Backend folder on sys.path. Use
    # the same explicit loader/cache identity as the editor's other adapters.
    identifier='_aive_local_speech'
    module=sys.modules.get(identifier)
    if module is None:
        path=Path(__file__).with_name('local_speech.py')
        ordinary=sys.modules.get('local_speech')
        if ordinary is not None and Path(getattr(ordinary,'__file__','')).resolve()==path.resolve():
            module=ordinary;sys.modules[identifier]=module
        else:
            spec=importlib.util.spec_from_file_location(identifier,path)
            module=importlib.util.module_from_spec(spec);sys.modules[identifier]=module
            try:spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(identifier,None);raise
    return module


local_speech=_load_speech_runtime()

_install_lock = threading.Lock()
_USER_AGENT = "Aive-local-speech-verified-installer/1"
_CHUNK_SIZE = 1024 * 1024
_MODEL_SOURCES = ("https://huggingface.co", "https://hf-mirror.com")


def _error(code, message):
    raise local_speech.LocalSpeechError(code, message)


def _allowed_download_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and (host == "huggingface.co" or host.endswith(".huggingface.co")
                     or host == "hf.co" or host.endswith(".hf.co")
                     or host == "hf-mirror.com" or host.endswith(".hf-mirror.com")))
    except (TypeError, ValueError):
        return False


class _HFRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _allowed_download_url(newurl):
            _error("LOCAL_SPEECH_DOWNLOAD_URL", "语音模型下载跳转到了不受支持的地址")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _open_url(request, timeout=20):
    if not _allowed_download_url(request.full_url):
        _error("LOCAL_SPEECH_DOWNLOAD_URL", "语音模型下载地址无效")
    return urllib.request.build_opener(_HFRedirect()).open(request, timeout=timeout)


def _network_error(error, control):
    local_speech.check_cancel(control)
    raise local_speech.LocalSpeechError(
        "LOCAL_SPEECH_DOWNLOAD_NETWORK",
        "无法从 Hugging Face 或其国内镜像下载语音模型；已完成的分段会保留，请检查网络后再次点击下载继续") from error


def get_download_details():
    """Return the fixed public model source and download size for the UI."""
    return {"model": local_speech.MODEL_NAME, "repoId": local_speech.MODEL_REPO,
            "revision": local_speech.MODEL_REVISION, "sourceUrl": local_speech.MODEL_SOURCE,
            "modelSize": sum(row["size"] for row in local_speech.MODEL_FILES),
            "files": [dict(row) for row in local_speech.MODEL_FILES],
            "downloadSources": list(_MODEL_SOURCES)}


def _hash_file(path, control):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            local_speech.check_cancel(control)
            block = stream.read(4 * 1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _verified_file(path, spec, control):
    return (path.is_file() and not path.is_symlink()
            and path.stat().st_size == spec["size"]
            and _hash_file(path, control) == spec["sha256"])


def _model_path(directory, name):
    target = directory / name
    if (target.parent.resolve() != directory.resolve()
            or target.is_symlink()):
        _error("LOCAL_SPEECH_DOWNLOAD_IO", "语音模型保存路径无效")
    return target


def _download_file(spec, directory, completed, total, progress, control, sources):
    local_speech.check_cancel(control)
    target = _model_path(directory, spec["name"])
    partial = _model_path(directory, spec["name"] + ".partial")
    expected = spec["size"]
    if _verified_file(target, spec, control):
        return
    if partial.exists() and not partial.is_file():
        _error("LOCAL_SPEECH_DOWNLOAD_IO", "语音模型保存路径无效")
    if partial.exists() and partial.stat().st_size > expected:
        partial.unlink()
    if partial.exists() and partial.stat().st_size == expected:
        if _hash_file(partial, control) == spec["sha256"]:
            local_speech.check_cancel(control)
            os.replace(partial, target)
            return
        partial.unlink()

    relative = ("/" + local_speech.MODEL_REPO + "/resolve/"
                + local_speech.MODEL_REVISION + "/"
                + urllib.parse.quote(spec["name"], safe="/") + "?download=true")
    last_error = None
    hash_failed = False
    size_failed = False
    for source in _MODEL_SOURCES:
        local_speech.check_cancel(control)
        received = partial.stat().st_size if partial.exists() else 0
        if received >= expected:
            break
        headers = {"User-Agent": _USER_AGENT, "Accept-Encoding": "identity"}
        if received:
            headers["Range"] = "bytes=" + str(received) + "-"
        try:
            with _open_url(urllib.request.Request(source + relative, headers=headers)) as response:
                if not _allowed_download_url(response.geturl()):
                    _error("LOCAL_SPEECH_DOWNLOAD_URL", "语音模型下载返回了不受支持的地址")
                status = getattr(response, "status", 200)
                actual_received = received
                if actual_received and status == 206:
                    match = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+)",
                        response.headers.get("Content-Range", ""))
                    if (not match or int(match.group(1)) != actual_received
                            or int(match.group(3)) != expected):
                        size_failed = True
                        raise ValueError("语音模型分段范围与固定版本不一致")
                elif status == 200:
                    # Mirrors sometimes ignore Range. Restart this source from
                    # zero because appending its full response would corrupt the
                    # already retained segment.
                    actual_received = 0
                else:
                    size_failed = True
                    raise ValueError("语音模型服务器返回了无效分段")
                with partial.open("ab" if actual_received else "wb") as output:
                    while True:
                        local_speech.check_cancel(control)
                        block = response.read(_CHUNK_SIZE)
                        local_speech.check_cancel(control)
                        if not block:
                            break
                        if actual_received + len(block) > expected:
                            size_failed = True
                            partial.unlink(missing_ok=True)
                            raise ValueError("语音模型下载长度与固定版本不一致")
                        output.write(block)
                        actual_received += len(block)
                        done = completed + actual_received
                        progress(
                            min(94, int(done * 94 / total)),
                            f"正在下载语音模型 {done / 1024**2:.1f}/{total / 1024**2:.1f} MB；取消后可继续")
                    output.flush()
                    os.fsync(output.fileno())
        except local_speech.LocalSpeechError:
            raise
        except (urllib.error.URLError, http.client.HTTPException,
                TimeoutError, OSError, ValueError) as error:
            last_error = error
            if received == expected:
                size_failed = True
                partial.unlink(missing_ok=True)
        local_speech.check_cancel(control)
        received = partial.stat().st_size if partial.exists() else 0
        if received == expected:
            if _hash_file(partial, control) == spec["sha256"]:
                local_speech.check_cancel(control)
                os.replace(partial, target)
                sources.append((target.name, source))
                return
            partial.unlink(missing_ok=True)
            hash_failed = True
            last_error = None
        elif received:
            last_error = OSError(
                f"model source returned {received} of {expected} bytes")

    local_speech.check_cancel(control)
    received = partial.stat().st_size if partial.exists() else 0
    if received == expected and _hash_file(partial, control) == spec["sha256"]:
        local_speech.check_cancel(control)
        os.replace(partial, target)
        return
    if size_failed:
        partial.unlink(missing_ok=True)
        _error("LOCAL_SPEECH_DOWNLOAD_SIZE",
               "语音模型下载长度或分段与固定版本不一致，损坏分段已移除，请重新下载")
    if received and received < expected and last_error is not None:
        _network_error(
            last_error or OSError("speech model download is incomplete"), control)
    if hash_failed:
        _error("LOCAL_SPEECH_DOWNLOAD_HASH",
               "语音模型 SHA256 校验失败，已尝试官方源与镜像并移除损坏分段")
    _network_error(
        last_error or OSError("all speech model sources returned incomplete data"),
        control)


def _publish(directory, sources):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    if directory.is_symlink() or manifest.is_symlink():
        _error("LOCAL_SPEECH_DOWNLOAD_IO", "语音模型保存路径无效")
    for row in local_speech.MODEL_FILES:
        target = _model_path(directory, row["name"])
        if not target.is_file() or target.is_symlink():
            _error("LOCAL_SPEECH_DOWNLOAD_VERIFY", "语音模型文件尚未完整下载")
    metadata = {
        "id": local_speech.MODEL_NAME,
        "repo": local_speech.MODEL_REPO,
        "revision": local_speech.MODEL_REVISION,
        "sourceUrl": local_speech.MODEL_SOURCE,
        "files": list(local_speech.MODEL_FILES),
        "downloadSources": dict(sources),
        "verified": True,
    }
    temporary = directory / (".manifest-" + os.urandom(6).hex() + ".partial")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            output.write(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        # Keep any previous manifest in place until every data file has been
        # verified, then atomically make the new installation discoverable.
        os.replace(temporary, manifest)
    finally:
        temporary.unlink(missing_ok=True)
    local_speech._verified_signature = None


def install_model(progress, control):
    """Task-center worker: install resumable, verified model data.

    Cancellation and transient network failures retain only fixed-name
    ``.partial`` data. Existing valid files are reused. The manifest is always
    published last, so the runtime never treats an incomplete set as ready.
    """
    local_speech.check_cancel(control)
    if not _install_lock.acquire(blocking=False):
        _error("LOCAL_SPEECH_DOWNLOAD_BUSY", "语音模型正在下载，请等待现有任务完成")
    try:
        progress(0, "正在检查本地语音模型")
        status = local_speech.get_status()
        local_speech.check_cancel(control)
        if status["ready"]:
            progress(100, "本地语音模型已就绪")
            return status
        directory = Path(local_speech.MODEL_DIR)
        if directory.is_symlink():
            _error("LOCAL_SPEECH_DOWNLOAD_IO", "语音模型保存路径无效")
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir(parents=True, exist_ok=True)
        total = sum(row["size"] for row in local_speech.MODEL_FILES)
        needed = sum(
            max(0, row["size"] - (
                _model_path(directory, row["name"] + ".partial").stat().st_size
                if _model_path(directory, row["name"] + ".partial").is_file()
                else 0))
            for row in local_speech.MODEL_FILES)
        if shutil.disk_usage(directory).free < needed + 16 * 1024**2:
            _error("LOCAL_SPEECH_DOWNLOAD_SPACE",
                   "可用磁盘空间不足，请至少保留剩余下载大小加 16MB 空间")
        completed = 0
        used_sources = []
        for spec in local_speech.MODEL_FILES:
            _download_file(
                spec, directory, completed, total, progress, control, used_sources)
            completed += spec["size"]
        progress(96, "全部文件校验通过，正在安装语音模型")
        local_speech.check_cancel(control)
        # Another application process may have finished the same fixed model.
        status = local_speech.get_status()
        local_speech.check_cancel(control)
        if not status["ready"]:
            _publish(directory, used_sources)
            status = local_speech.get_status()
            if not status["ready"]:
                _error("LOCAL_SPEECH_DOWNLOAD_VERIFY",
                       "语音模型安装后校验失败，请重新下载")
        progress(100, "语音模型已下载、校验并安装")
        return status
    except OSError as error:
        local_speech.check_cancel(control)
        raise local_speech.LocalSpeechError(
            "LOCAL_SPEECH_DOWNLOAD_IO",
            "无法保存语音模型，请检查应用目录权限和磁盘空间") from error
    finally:
        _install_lock.release()
