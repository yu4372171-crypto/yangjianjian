"""Independent, data-only text GGUF library and loopback JSON inference.

Weights and settings never share the vision-model directory or selection. Only
the already bundled llama-server executable and verified downloader are reused.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

if '_aive_requirement_models' in sys.modules:
    _load = sys.modules['_aive_requirement_models']._load
else:
    from requirement_models import _load

ROOT = Path(__file__).resolve().parent / 'runtime' / 'language_models'
_lock = threading.RLock()
_inference_lock = threading.Lock()
_install_locks = {}
_process = _job = _log = _running_model = _port = _api_key = None
_last_error = ''
_ID = re.compile(r'^text-[a-z0-9][a-z0-9-]{0,73}$')
_SHA = re.compile(r'^[a-f0-9]{64}$')
_COMMIT = re.compile(r'^[a-fA-F0-9]{40}$')
_PROVIDERS = {'text-ollama': 'ollama', 'text-openai-compatible': 'openai-compatible'}
_CURATED = (
    ('0.6B', 650_000_000, '轻量体验；官方 Q8_0，复杂多轮建议选择 4B 或 8B'),
    ('1.7B', 1_900_000_000, '官方 Q8_0，适合基本中文需求'),
    ('4B', 2_500_000_000, '推荐；中文、多轮需求与结构化剪辑规划'),
    ('8B', 5_100_000_000, '更强的语义理解；需要更多内存和显存'),
)


class LanguageModelError(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _error(message, code='LANGUAGE_MODEL_INVALID'):
    raise LanguageModelError(code, message)


def _check(control=None):
    _load('local_vision').check_cancel(control)


def _progress(progress, message):
    if progress:
        progress(message)


def _safe_root():
    root = Path(os.path.abspath(ROOT))
    if root.is_symlink() or root.resolve() != root:
        _error('语言模型目录不能是链接')
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_path(parent, name):
    path = parent / name
    if path.is_symlink() or not path.resolve().is_relative_to(parent.resolve()):
        _error('语言模型文件路径无效')
    return path


def _atomic_json(target, value):
    stage = _safe_path(target.parent, target.name + '.partial')
    if target.is_symlink():
        _error('语言模型设置路径无效')
    with stage.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stage, target)


def get_catalog():
    items = []
    for size, estimate, description in _CURATED:
        quantization = 'Q8_0' if size in ('0.6B', '1.7B') else 'Q4_K_M'
        identifier = 'text-qwen3-' + size.lower().replace('.', '-') + '-' + quantization.lower().replace('_', '-')
        repo = 'Qwen/Qwen3-' + size + '-GGUF'
        items.append({'id': identifier, 'name': 'Qwen3 ' + size,
            'repoId': repo, 'license': 'apache-2.0', 'sourceUrl': 'https://huggingface.co/' + repo,
            'description': description, 'recommended': size == '4B',
            'variants': [{'id': identifier, 'repoId': repo,
                'filename': 'Qwen3-' + size + '-' + quantization + '.gguf', 'quantization': quantization,
                'estimatedBytes': estimate}]})
    return {'items': items, 'source': 'Qwen official / Hugging Face'}


def _variant(identifier):
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        _error('请选择目录中的语言模型')
    for item in get_catalog()['items']:
        for variant in item['variants']:
            if variant['id'] == identifier:
                return {**item, **variant}
    _error('所选语言模型不在受支持的官方目录中')


def _installed_models():
    models = []
    root = Path(ROOT)
    if not root.is_dir() or root.is_symlink() or root.resolve() != Path(os.path.abspath(root)):
        return models
    for manifest in sorted(root.glob('text-*/manifest.json')):
        try:
            if manifest.is_symlink() or manifest.parent.is_symlink():
                continue
            data = json.loads(manifest.read_text('utf-8'))
            identifier = data['id']
            variant = _variant(identifier)
            if manifest.parent.name != identifier or data['repoId'] != variant['repoId']:
                continue
            if data['modelFile'] != 'model.gguf' or not _SHA.fullmatch(data['modelSha256']) or not _COMMIT.fullmatch(data['revision']):
                continue
            path = _safe_path(manifest.parent, 'model.gguf')
            if type(data['modelSize']) is not int or path.stat().st_size != data['modelSize']:
                continue
            with path.open('rb') as stream:
                if stream.read(4) != b'GGUF':
                    continue
            models.append({'id': identifier, 'name': data['name'], 'provider': 'gguf',
                'status': 'installed', 'installed': True, 'size': data['modelSize'], 'bytes': data['modelSize'],
                'filename': data.get('modelSourceFile', variant['filename']), 'model': path,
                'repoId': data['repoId'], 'license': 'apache-2.0',
                'sourceUrl': variant['sourceUrl'], 'revision': data['revision']})
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            continue
    return models


def validate_base_url(value):
    if not isinstance(value, str) or len(value) > 300 or any(ord(c) < 32 for c in value):
        _error('本地服务地址无效')
    try:
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'http' or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError()
        if host not in ('127.0.0.1', 'localhost', '::1') or parsed.port is None or not 1 <= parsed.port <= 65535:
            raise ValueError()
        if parsed.path.rstrip('/') not in ('', '/v1'):
            raise ValueError()
    except ValueError:
        _error('只支持 http://127.0.0.1:端口、localhost 或 [::1] 的本机模型服务')
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


def _settings():
    try:
        value = json.loads((Path(ROOT) / 'settings.json').read_text('utf-8'))
        if not isinstance(value, dict) or set(value) - {'modelId', 'provider', 'baseUrl', 'model'}:
            return {}
        if not value:
            return {}
        identifier, provider = value.get('modelId'), value.get('provider')
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or not isinstance(provider, str):
            return {}
        if provider in ('ollama', 'openai-compatible'):
            if _PROVIDERS.get(identifier) != provider:
                return {}
            value['baseUrl'] = validate_base_url(value['baseUrl'])
            model = value.get('model')
            if not isinstance(model, str) or not model.strip() or len(model) > 160 or any(ord(c) < 32 for c in model):
                return {}
        elif provider != 'gguf':
            return {}
        return value
    except (OSError, ValueError, KeyError, RuntimeError):
        return {}


def get_status():
    models, settings = _installed_models(), _settings()
    installed = {row['id'] for row in models}
    saved = settings.get('modelId')
    selected = saved if saved in installed | set(_PROVIDERS) else (
        'text-qwen3-4b-q4-k-m' if 'text-qwen3-4b-q4-k-m' in installed else next(iter(sorted(installed)), None))
    command = _load('local_vision')._engine_command()
    for identifier, provider in _PROVIDERS.items():
        configured = saved == identifier and bool(settings.get('baseUrl') and settings.get('model'))
        models.append({'id': identifier, 'name': '本机 Ollama' if provider == 'ollama' else '本机兼容服务',
            'provider': provider, 'installed': configured, 'status': 'configured' if configured else 'configure',
            'bytes': 0, 'size': 0, 'filename': ''})
    running = _process is not None and _process.poll() is None
    ready = bool((selected in installed and command) or (selected in _PROVIDERS and settings.get('baseUrl') and settings.get('model')))
    return {'models': [{**{key: value for key, value in row.items() if key != 'model'}, 'selected': row['id'] == selected} for row in models],
        'selectedModel': selected, 'runningModel': _running_model if running else None,
        'engine': 'llama.cpp / Vulkan' if command else '未安装', 'ready': ready, 'settings': settings,
        'message': '独立语言模型负责完整多轮需求理解' if ready else '请下载语言模型或配置本机模型服务',
        'error': _last_error}


def configure(data):
    if not isinstance(data, dict) or set(data) - {'modelId', 'provider', 'baseUrl', 'model'}:
        _error('语言模型设置无效')
    identifier = data.get('modelId')
    if identifier in _PROVIDERS:
        old = _settings()
        provider = _PROVIDERS[identifier]
        if data.get('provider', provider) != provider:
            _error('模型类型与服务类型不一致')
        base = validate_base_url(data.get('baseUrl', old.get('baseUrl') or ('http://127.0.0.1:11434' if provider == 'ollama' else 'http://127.0.0.1:8080/v1')))
        model = data.get('model', old.get('model', ''))
        if not isinstance(model, str) or not model.strip() or len(model) > 160 or any(ord(c) < 32 for c in model):
            _error('请填写本机服务中的模型名称')
        settings = {'modelId': identifier, 'provider': provider, 'baseUrl': base, 'model': model.strip()}
    else:
        _variant(identifier)
        if not any(row['id'] == identifier for row in _installed_models()):
            _error('所选语言模型尚未下载完成', 'LANGUAGE_MODEL_MISSING')
        settings = {'modelId': identifier, 'provider': 'gguf'}
    with _lock:
        if identifier != _running_model:
            stop()
        _atomic_json(_safe_root() / 'settings.json', settings)
    return get_status()


def resolve_model_id(identifier=None):
    status = get_status()
    selected = identifier if identifier else status['selectedModel']
    if selected in _PROVIDERS:
        if status['settings'].get('modelId') != selected or not status['settings'].get('model'):
            _error('请先配置本机语言模型服务', 'LANGUAGE_MODEL_MISSING')
    elif not any(row['id'] == selected for row in _installed_models()):
        _error('语言模型尚未就绪，请先在语言模型库下载或选择本机服务', 'LANGUAGE_MODEL_MISSING')
    return selected


def _resolve_metadata(identifier):
    variant = _variant(identifier)
    catalog = _load('vision_catalog')
    info, _ = catalog._json_request(catalog._HF + '/api/models/' + variant['repoId'] + '?blobs=true')
    if not isinstance(info, dict) or not _COMMIT.fullmatch(str(info.get('sha', ''))):
        _error('官方模型目录缺少固定版本，未开始下载')
    for row in info.get('siblings', []):
        if isinstance(row, dict) and str(row.get('rfilename', '')).lower() == variant['filename'].lower():
            metadata = catalog._file_metadata(row)
            if metadata:
                return variant, info['sha'], metadata
    _error('官方目录未提供该量化文件的可信 SHA-256 与大小，未开始下载')


def install(identifier, progress=None, control=None):
    """Fixed commit, resumable partial, full SHA-256, manifest published last."""
    _variant(identifier)
    report = progress or (lambda *_: None)
    with _lock:
        lock = _install_locks.setdefault(identifier, threading.Lock())
    if not lock.acquire(blocking=False):
        _error('这个语言模型正在下载，请等待现有任务', 'LANGUAGE_MODEL_BUSY')
    try:
        _check(control)
        report(0, '正在读取官方固定版本与文件校验信息')
        variant, revision, metadata = _resolve_metadata(identifier)
        _check(control)
        folder = _safe_path(_safe_root(), identifier)
        folder.mkdir(exist_ok=True)
        partial = _safe_path(folder, 'model.gguf.partial')
        target = _safe_path(folder, 'model.gguf')
        needed = max(0, metadata['size'] - (target.stat().st_size if target.exists() else partial.stat().st_size if partial.exists() else 0))
        if shutil.disk_usage(folder).free < needed + 100 * 1024**2:
            _error('语言模型安装磁盘空间不足，请保留模型大小加 100MB')
        sources = []
        _load('vision_catalog')._download_file(variant['repoId'], revision, metadata, target,
            0, metadata['size'], report, control, sources)
        _check(control)
        manifest = {'id': identifier, 'name': variant['name'] + ' · ' + variant['quantization'], 'modelFile': 'model.gguf',
            'modelSize': metadata['size'], 'modelSha256': metadata['sha256'], 'revision': revision,
            'repoId': variant['repoId'], 'modelSourceFile': metadata['name'],
            'sourceUrl': variant['sourceUrl'], 'license': 'apache-2.0', 'architecture': 'qwen3',
            'downloadSource': sources[-1][1] if sources else '',
            'downloadSources': dict(sources)}
        stage = _safe_path(folder, 'manifest.json.staging')
        with stage.open('w', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _check(control)
        os.replace(stage, _safe_path(folder, 'manifest.json'))
        report(100, '语言模型已校验并安装；可独立切换使用')
        return {'modelId': identifier, 'installed': True, 'name': manifest['name'], 'revision': revision}
    finally:
        lock.release()


def remove(identifier):
    _variant(identifier)
    with _lock:
        lock = _install_locks.setdefault(identifier, threading.Lock())
        if not lock.acquire(blocking=False):
            _error('语言模型仍在下载，请先取消任务')
        try:
            if _running_model == identifier:
                stop()
            folder = _safe_path(_safe_root(), identifier)
            if folder.exists():
                # Remove only owned files, never recursively traverse arbitrary content.
                for name in ('manifest.json', 'manifest.json.staging', 'model.gguf', 'model.gguf.partial'):
                    _safe_path(folder, name).unlink(missing_ok=True)
                if not any(folder.iterdir()):
                    folder.rmdir()
            if _settings().get('modelId') == identifier:
                _atomic_json(_safe_root() / 'settings.json', {})
            return {'removed': True, 'modelId': identifier}
        finally:
            lock.release()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _error('本机语言模型服务不允许重定向', 'LANGUAGE_MODEL_NETWORK')


def _open_local(request, timeout=180):
    # Do not forward local prompts through machine-wide proxy settings.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


def stop():
    global _process, _job, _log, _running_model, _port, _api_key
    with _lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
            try:
                _process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _process.kill()
                _process.wait(timeout=5)
        if _job:
            _job[0].CloseHandle(_job[1])
        if _log:
            _log.close()
        _process = _job = _log = _running_model = _port = _api_key = None


def _start(identifier, control=None, progress=None):
    global _process, _job, _log, _running_model, _port, _api_key, _last_error
    _check(control)
    with _lock:
        if _process is not None and _process.poll() is None and _running_model == identifier:
            return
        model = next((row for row in _installed_models() if row['id'] == identifier), None)
        command = _load('local_vision')._engine_command()
        if not model or not command:
            _error('语言模型或本地推理引擎未就绪，请完成下载', 'LANGUAGE_MODEL_MISSING')
        stop()
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            _port = probe.getsockname()[1]
        _api_key, _running_model = secrets.token_urlsafe(32), identifier
        logs = _safe_root() / 'logs'
        logs.mkdir(exist_ok=True)
        _log = _safe_path(logs, 'engine.log').open('wb')
        args = command + ['-m', str(model['model']), '--host', '127.0.0.1', '--port', str(_port),
            '--api-key', _api_key, '--alias', identifier, '-ngl', '99', '-c', '16384', '-np', '1',
            '-b', '512', '-ub', '256', '--no-webui']
        try:
            _process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=_log, stderr=_log,
                cwd=str(Path(command[0]).parent), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            _job = _load('local_vision')._assign_kill_job(_process)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                _check(control)
                if _process.poll() is not None:
                    _error('独立语言引擎启动失败，请检查内存或选择较小模型', 'LANGUAGE_MODEL_START')
                try:
                    request = urllib.request.Request(f'http://127.0.0.1:{_port}/health', headers={'Authorization': 'Bearer ' + _api_key})
                    with _open_local(request, timeout=1) as response:
                        if response.status == 200:
                            _last_error = ''
                            return
                except (OSError, urllib.error.URLError):
                    pass
                _progress(progress, '正在加载独立语言模型')
                time.sleep(.25)
            _error('语言模型加载超时，请选择较小模型后重试', 'LANGUAGE_MODEL_START')
        except BaseException as error:
            _last_error = str(error)
            stop()
            raise


def _request_json(url, payload, key=None):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers=headers)
    with _open_local(request) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        _error('语言模型回复过长，未采用该计划', 'LANGUAGE_MODEL_RESPONSE')
    return _load('local_vision').parse_response(raw.decode('utf-8'))


def complete_json(messages, schema, model_id=None, control=None, progress=None, reasoning=False):
    """Return only complete, finite, unique-key JSON from a real local model."""
    if not isinstance(messages, list) or not messages or len(messages) > 28:
        _error('模型消息格式无效')
    total = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != {'role', 'content'} or message.get('role') not in ('system', 'user', 'assistant'):
            _error('模型消息格式无效')
        if message['role'] == 'system' and index != 0:
            _error('仅允许一个由应用提供的系统消息')
        if not isinstance(message['content'], str):
            _error('语言模型只接收纯文本消息')
        total += len(message['content'])
    if total > 60000 or not isinstance(schema, dict):
        _error('完整对话过长，请保留当前计划并开始新的对话')
    if model_id in ('text-api', 'text-auto'):
        scheduler = _load('ai_scheduler')
        result, _ = scheduler.run_language(messages, schema, control=control, progress=progress, reasoning=reasoning,
            mode='api' if model_id == 'text-api' else 'auto',
            local_call=lambda identifier: complete_json(messages, schema, identifier, control, progress, reasoning=reasoning))
        return result
    identifier = resolve_model_id(model_id)
    _check(control)
    while not _inference_lock.acquire(timeout=.2):
        _check(control)
    try:
        settings = _settings()
        provider = _PROVIDERS.get(identifier, 'gguf')
        if provider == 'gguf':
            _start(identifier, control, progress)
            base, service_model, key = f'http://127.0.0.1:{_port}', identifier, _api_key
        else:
            base, service_model, key = validate_base_url(settings['baseUrl']), settings['model'], None
        _progress(progress, '正在理解完整对话并核对剪辑能力')
        if provider == 'ollama':
            url = base.removesuffix('/v1') + '/api/chat'
            payload = {'model': service_model, 'messages': messages, 'format': schema,
                'stream': False, 'think': reasoning, 'options': {'temperature': 0, 'num_predict': 8192 if reasoning else 4096, 'num_ctx': 16384}}
        else:
            url = base.rstrip('/') + ('/chat/completions' if base.endswith('/v1') else '/v1/chat/completions')
            payload = {'model': service_model, 'messages': messages, 'temperature': 0,
                'max_tokens': 8192 if reasoning else 4096, 'stream': False, 'chat_template_kwargs': {'enable_thinking': reasoning},
                'response_format': {'type': 'json_object', 'schema': schema}}
        finished, outcome = threading.Event(), {}
        def infer():
            try:
                try:
                    response = _request_json(url, payload, key)
                except urllib.error.HTTPError as error:
                    if provider == 'openai-compatible' and error.code in (400, 422):
                        # Some local compatible servers only implement json_object.
                        payload['response_format'] = {'type': 'json_object'}
                        payload.pop('chat_template_kwargs', None)
                        response = _request_json(url, payload, key)
                    else:
                        raise
                if provider == 'ollama':
                    if response.get('done') is not True or response.get('done_reason') not in (None, 'stop'):
                        _error('本机语言模型回复未完整结束，未采用计划', 'LANGUAGE_MODEL_RESPONSE')
                    message = response.get('message')
                    if not isinstance(message, dict) or message.get('tool_calls'):
                        _error('本机语言模型回复无效', 'LANGUAGE_MODEL_RESPONSE')
                    outcome['result'] = _load('local_vision').parse_response(message.get('content'))
                else:
                    outcome['result'] = _load('local_vision')._completion_result(response)
            except Exception as error:
                outcome['error'] = error
            finally:
                finished.set()
        threading.Thread(target=infer, name='language-model-request', daemon=True).start()
        try:
            while not finished.wait(.2):
                _check(control)
            _check(control)
        except BaseException:
            if provider == 'gguf':
                stop()
            raise
        if 'error' in outcome:
            error = outcome['error']
            if isinstance(error, RuntimeError):
                raise error
            _error('无法连接本机语言模型或推理超时，请检查服务并重试', 'LANGUAGE_MODEL_INFER')
        return outcome['result']
    finally:
        _inference_lock.release()


def test_model(identifier=None, control=None, progress=None):
    identifier = resolve_model_id(identifier)
    result = complete_json([{'role': 'system', 'content': 'Return exactly {"ready":true}. /no_think'},
        {'role': 'user', 'content': '请确认本地文本推理可用，只返回JSON。'}],
        {'type': 'object', 'properties': {'ready': {'type': 'boolean'}}, 'required': ['ready'], 'additionalProperties': False},
        identifier, control, progress)
    if result != {'ready': True}:
        _error('模型已响应，但未通过结构化文本推理测试', 'LANGUAGE_MODEL_RESPONSE')
    return {'ready': True, 'message': '已通过真实本地文本推理测试', 'modelId': identifier}


atexit.register(stop)
