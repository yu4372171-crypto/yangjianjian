"""Public model catalogue and verified llama.cpp vision-pair installs.

Only data files are downloaded. No repository code, pickle or installer is run.
The runtime loader recognises an installation only after manifest.json exists.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request

from app.ui2.common import BridgeError
from app.workers.control import check_control

_RUNTIME_ROOT = Path(__file__).resolve().parent / 'runtime' / 'local_vision'
_HF = 'https://huggingface.co'
_MIRROR = 'https://hf-mirror.com'
_MODEL_SOURCES = (_HF, _MIRROR)
_TASKS = ('image-text-to-text', 'image-to-text', 'visual-question-answering',
          'image-classification', 'zero-shot-image-classification', 'object-detection',
          'image-segmentation', 'depth-estimation', 'video-classification')
_REPO = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$')
_API_MODEL = re.compile(r'^/api/models/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$')
_COMMIT = re.compile(r'^[a-fA-F0-9]{40}$')
_SHA = re.compile(r'^[a-fA-F0-9]{64}$')
_MODEL_ID = re.compile(r'^[a-z0-9-]{1,80}$')
_QUANT = re.compile(r'[-_.](?:[iq]q?\d[^/]*?|bf16|f16|f32)$', re.I)
_SPLIT = re.compile(r'-\d{5}-of-\d{5}\.gguf$', re.I)
_KNOWN_ARCHITECTURES = {'qwen2vl', 'qwen3vl', 'gemma3', 'gemma4', 'qwen35', 'qwen3_5',
                        'internvl', 'internvl2', 'internvl3', 'minicpmv', 'pixtral', 'mllama'}
_LOCKS, _LOCKS_GUARD = {}, threading.Lock()
_USER_AGENT = 'AI-Auto-Editing-Model-Library/1.0'
_CURATED = (
    {'repoId':'ggml-org/Qwen3-VL-2B-Instruct-GGUF', 'name':'Qwen3-VL 2B · 推荐',
     'license':'apache-2.0', 'size':2279480352, 'memory':'建议 8GB 以上内存',
     'description':'中文画面理解，适合先体验本地视频分析。'},
    {'repoId':'ggml-org/Qwen2.5-VL-3B-Instruct-GGUF', 'name':'Qwen2.5-VL 3B',
     'license':'apache-2.0', 'size':2774658784, 'memory':'建议 8GB 以上内存',
     'description':'可选择 Q4 或 Q8 量化，较小量化占用更少内存。'},
    {'repoId':'ggml-org/gemma-3-4b-it-GGUF', 'name':'Gemma 3 4B',
     'license':'gemma', 'size':3341008960, 'memory':'建议 12GB 以上内存',
     'description':'开放权重模型，使用条件请查看 Gemma 模型许可证。'},
    {'repoId':'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'name':'SmolVLM2 500M · 轻量',
     'license':'apache-2.0', 'size':545593888, 'memory':'建议 4GB 以上内存',
     'description':'下载较小、适合入门；细微画面异常识别能力有限。'},
)


def _error(message, code='VISION_MODEL_INVALID'):
    raise BridgeError(code, message)


def _repo_id(value):
    if not isinstance(value, str) or not _REPO.fullmatch(value) or '..' in value:
        _error('模型仓库地址无效，请使用 Hugging Face 的作者/模型名')
    return value


def _file_name(value):
    if not isinstance(value, str) or not value or len(value) > 250:
        _error('模型文件名无效')
    if '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        _error('模型文件名无效')
    if any(part in ('', '.', '..') for part in value.split('/')) or not value.lower().endswith('.gguf'):
        _error('仅支持仓库内有效的 GGUF 文件')
    return value


def _allowed_download_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    return (parsed.scheme == 'https' and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
            and (host == 'huggingface.co' or host.endswith('.huggingface.co')
                 or host == 'hf.co' or host.endswith('.hf.co')
                 or host == 'hf-mirror.com' or host.endswith('.hf-mirror.com')))


class _HFRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _allowed_download_url(newurl):
            _error('模型下载跳转到了不受支持的地址', 'VISION_DOWNLOAD_FAILED')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _open_url(request, timeout=20):
    if not _allowed_download_url(request.full_url):
        _error('模型下载地址无效')
    return urllib.request.build_opener(_HFRedirect()).open(request, timeout=timeout)


def _network_error(error):
    if isinstance(error, urllib.error.HTTPError):
        if error.code in (401, 403):
            _error('该模型需要在 Hugging Face 获得访问权限或接受使用条款，当前未下载。可先选择公开可下载模型。', 'VISION_MODEL_ACCESS')
        if error.code == 404:
            _error('模型或所选文件已不存在，请刷新模型目录', 'VISION_MODEL_MISSING')
        if error.code == 429:
            _error('Hugging Face 请求较多，请稍后刷新或继续下载', 'VISION_MODEL_RATE_LIMIT')
    _error('无法连接模型下载源（已尝试 Hugging Face 与国内镜像），请检查网络或代理后重试；已有下载分段会保留。', 'VISION_MODEL_NETWORK')


def _json_request(url):
    original = _api_page_url(url)
    split = urllib.parse.urlsplit(original)
    relative = split.path + (('?' + split.query) if split.query else '')
    errors = []
    for source in _MODEL_SOURCES:
        candidate = source + relative
        try:
            with _open_url(urllib.request.Request(
                    candidate, headers={'User-Agent':_USER_AGENT, 'Accept':'application/json'})) as response:
                raw = response.read(6 * 1024 * 1024 + 1)
                if len(raw) > 6 * 1024 * 1024:
                    _error('模型目录回复过大，请缩小搜索范围')
                value = json.loads(raw)
                headers = dict(response.headers.items())
                for key, value_header in tuple(headers.items()):
                    if key.lower() == 'link' and isinstance(value_header, str):
                        headers[key] = value_header.replace(_MIRROR, _HF)
                return value, headers
        except BridgeError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError) as error:
            errors.append(error)
    _network_error(errors[-1] if errors else OSError('all model sources failed'))


def _license(info):
    value = (info.get('cardData') or {}).get('license')
    if isinstance(value, list):
        value = ', '.join(str(x) for x in value)
    if not value:
        value = next((tag[len('license:'):] for tag in info.get('tags', [])
                      if isinstance(tag, str) and tag.startswith('license:')), '')
    return str(value or '未标注，请查看模型卡')[:200]


def _safe_models_root():
    runtime = Path(_RUNTIME_ROOT).resolve()
    directory = runtime / 'models'
    if not directory.resolve().is_relative_to(runtime):
        _error('本地模型目录不在应用运行目录内')
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_destination(directory, filename):
    target = directory / filename
    if not target.resolve().is_relative_to(directory.resolve()) or target.is_symlink():
        _error('模型保存路径无效')
    return target


def installed_models():
    root = _safe_models_root()
    models = []
    for folder in root.iterdir():
        if not _MODEL_ID.fullmatch(folder.name) or not folder.is_dir() or folder.is_symlink():
            continue
        try:
            manifest = json.loads(_safe_destination(folder, 'manifest.json').read_text('utf-8'))
            if manifest.get('id') != folder.name:
                continue
            for key, size_key in (('modelFile','modelSize'), ('mmprojFile','mmprojSize')):
                name = manifest.get(key)
                if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.gguf'):
                    raise ValueError('invalid manifest filename')
                target = _safe_destination(folder, name)
                size = manifest.get(size_key)
                if not isinstance(size, int) or isinstance(size, bool) or size < 4 or target.stat().st_size != size:
                    raise ValueError('incomplete model')
                with target.open('rb') as source:
                    if source.read(4) != b'GGUF':
                        raise ValueError('invalid model')
            models.append({'id':folder.name, 'name':str(manifest.get('name') or folder.name),
                'repoId':str(manifest.get('repoId') or ''),
                'modelSourceFile':str(manifest.get('modelSourceFile') or ''),
                'size':manifest['modelSize'] + manifest['mmprojSize'],
                'license':str(manifest.get('license') or '未标注，请查看模型卡'),
                'sourceUrl':str(manifest.get('sourceUrl') or '')})
        except (ValueError, OSError, BridgeError, KeyError, TypeError):
            continue
    return sorted(models, key=lambda model:model['name'].casefold())


def _model_id(repo, model_file, projector_file):
    if (repo == 'ggml-org/Qwen3-VL-2B-Instruct-GGUF'
            and model_file == 'Qwen3-VL-2B-Instruct-Q8_0.gguf'
            and projector_file == 'mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf'):
        return 'qwen3-vl-2b-q8'
    slug = re.sub('[^a-z0-9]+', '-', repo.split('/')[-1].lower()).strip('-')[:55]
    identity = json.dumps([repo, model_file, projector_file], separators=(',', ':')).encode()
    return slug + '-' + hashlib.sha256(identity).hexdigest()[:12]


def _encode_cursor(data):
    return base64.urlsafe_b64encode(json.dumps(data, separators=(',',':')).encode()).decode().rstrip('=')


def _api_page_url(url):
    if not isinstance(url, str) or len(url) > 7000:
        _error('目录页码无效，请重新搜索')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ('huggingface.co', 'hf-mirror.com')
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)
            or not (parsed.path == '/api/models' or _API_MODEL.fullmatch(parsed.path))):
        _error('目录页码无效，请重新搜索')
    return _HF + parsed.path + (('?' + parsed.query) if parsed.query else '')


def _next_link(headers):
    value = next((v for k,v in headers.items() if k.lower() == 'link'), '')
    match = re.search(r'<([^>]+)>;\s*rel="?next"?', value)
    return _api_page_url(match.group(1)) if match else None


def _item(info, installed):
    repo = info.get('id') or info.get('modelId')
    try:
        repo = _repo_id(repo)
    except BridgeError:
        return None
    if info.get('private'):
        return None
    names = [x.get('rfilename', '') for x in info.get('siblings', []) if isinstance(x, dict)]
    gguf = any(name.lower().endswith('.gguf') and 'mmproj' not in name.lower() for name in names)
    projector = any(name.lower().endswith('.gguf') and 'mmproj' in name.lower() for name in names)
    known = any(entry['repoId'] == repo for entry in _CURATED)
    installed_for_repo = [model for model in installed if model['repoId'] == repo
                          or (repo == _CURATED[0]['repoId'] and model['id'] == 'qwen3-vl-2b-q8')]
    return {'repoId':repo, 'name':repo.split('/')[-1], 'sourceUrl':_HF+'/'+repo,
            'license':_license(info), 'pipelineTag':str(info.get('pipeline_tag') or ''),
            'downloads':max(0, int(info.get('downloads') or 0)), 'likes':max(0, int(info.get('likes') or 0)),
            'gated':bool(info.get('gated')), 'gguf':gguf or known, 'projector':projector or known,
            'compatibleCandidate':(gguf and projector) or known,
            'installed':bool(installed_for_repo), 'installedModels':installed_for_repo}


def _projectors_for(model_name, projectors):
    # A projector belongs to the same repo and model identity; quantisation can differ.
    stem = Path(model_name).stem.lower()
    identity = _QUANT.sub('', stem)
    candidates = []
    for name in projectors:
        lowered = Path(name).stem.lower()
        if lowered.startswith(('mmproj-model-', 'mmproj-model.')) or lowered in ('mmproj', 'mmproj-model'):
            candidates.append(name)
        elif identity and identity in lowered:
            candidates.append(name)
    return candidates


def _file_metadata(row):
    name = _file_name(row.get('rfilename'))
    lfs = row.get('lfs') or {}
    size = row.get('size') or lfs.get('size')
    sha = lfs.get('sha256')
    if not isinstance(size, int) or isinstance(size, bool) or size < 4 or size > 250 * 1024**3:
        return None
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return None
    return {'name':name, 'size':size, 'sha256':sha.lower()}


def _files_for_repo(repo):
    info, _ = _json_request(_HF + '/api/models/' + urllib.parse.quote(repo, safe='/') + '?blobs=true')
    if not isinstance(info, dict):
        _error('无法读取模型文件目录')
    revision = info.get('sha', '')
    if not isinstance(revision, str) or not _COMMIT.fullmatch(revision):
        _error('模型版本无效，请稍后刷新')
    architecture = str((info.get('gguf') or {}).get('architecture') or '').lower()
    name = repo.split('/')[-1].lower()
    supported = architecture in _KNOWN_ARCHITECTURES or (
        architecture in ('llama', 'mistral', 'qwen2', 'qwen3') and
        any(family in name for family in ('smolvlm', 'llava', 'moondream', 'pixtral', 'internvl', 'minicpm')))
    metadata = []
    for row in info.get('siblings', []):
        if not isinstance(row, dict) or not str(row.get('rfilename','')).lower().endswith('.gguf'):
            continue
        if _SPLIT.search(row['rfilename']):
            continue
        try:
            item = _file_metadata(row)
        except BridgeError:
            continue
        if item:
            metadata.append(item)
    projectors = [row for row in metadata if 'mmproj' in Path(row['name']).name.lower()]
    models = [row for row in metadata if row not in projectors]
    files = []
    for row in models:
        pairs = _projectors_for(row['name'], [x['name'] for x in projectors])
        if pairs:
            files.append({**row, 'projectorFiles':pairs, 'modelId':_model_id(repo,row['name'],pairs[0])})
    files.sort(key=lambda row:row['size'])
    gated = bool(info.get('gated'))
    compatible = bool(supported and files and not gated and not info.get('private'))
    if gated:
        reason = '该模型需要在 Hugging Face 获得访问权限；可先选择公开可下载模型。'
    elif not supported:
        reason = '当前本地引擎尚未确认支持此模型架构；请先选推荐模型，或在云端/本地服务设置中接入已运行的服务。'
    elif not files:
        reason = '缺少可配对的单文件 GGUF 模型、视觉投影器或校验信息；此仓库暂不能一键安装。'
    else:
        reason = ''
    return {'repoId':repo, 'name':repo.split('/')[-1], 'sourceUrl':_HF+'/'+repo,
            'revision':revision, 'architecture':architecture, 'license':_license(info),
            'compatible':compatible, 'unsupportedReason':reason, 'gated':gated,
            'files':files if supported else [], 'projectors':projectors if supported else []}


def _hash_file(path, control):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            return ''
        stream.seek(0)
        while True:
            check_control(control)
            block = stream.read(4 * 1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _download_file(repo, revision, metadata, target, completed, total, progress, control,
                   source_used=None):
    check_control(control)
    expected = metadata['size']
    if target.exists():
        if target.stat().st_size == expected and _hash_file(target, control) == metadata['sha256']:
            return
        _error('已存在的模型文件与当前版本不符，请刷新目录或选择其他量化版本', 'VISION_MODEL_CONFLICT')
    partial = _safe_destination(target.parent, target.name + '.partial')
    received = partial.stat().st_size if partial.exists() else 0
    if received > expected:
        partial.unlink()
        received = 0
    if received < expected:
        path = ('/' + urllib.parse.quote(repo, safe='/') + '/resolve/' + revision
                + '/' + urllib.parse.quote(metadata['name'], safe='/') + '?download=true')
        last_error = None
        for source in _MODEL_SOURCES:
            # Re-read the persisted partial before every source. A dropped
            # connection must move to the next source with a fresh byte
            # offset, rather than retrying the same broken response forever.
            received = partial.stat().st_size if partial.exists() else 0
            if received > expected:
                partial.unlink()
                received = 0
            if received >= expected:
                break
            candidate = source + path
            headers = {'User-Agent':_USER_AGENT, 'Accept-Encoding':'identity'}
            if received:
                headers['Range'] = 'bytes=' + str(received) + '-'
            try:
                with _open_url(urllib.request.Request(candidate, headers=headers)) as response:
                    status = getattr(response, 'status', 200)
                    actual_received = received
                    if actual_received and status == 206:
                        content_range = response.headers.get('Content-Range', '')
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range)
                        if not match or int(match[1]) != actual_received or int(match[3]) != expected:
                            _error('下载分段与所选模型不一致，请重试', 'VISION_DOWNLOAD_FAILED')
                    elif status == 200:
                        # Some mirrors ignore Range. Restart this target from
                        # byte zero so their full response cannot corrupt it.
                        actual_received = 0
                    else:
                        _error('模型下载服务器返回了无效分段', 'VISION_DOWNLOAD_FAILED')
                    with partial.open('ab' if actual_received else 'wb') as stream:
                        try:
                            while True:
                                check_control(control)
                                block = response.read(1024 * 1024)
                                if not block:
                                    break
                                if actual_received + len(block) > expected:
                                    _error('模型下载长度与目录不一致', 'VISION_DOWNLOAD_FAILED')
                                stream.write(block)
                                actual_received += len(block)
                                done = completed + actual_received
                                progress(min(94, int(done * 94 / total)),
                                         f'下载 {done/1024**2:.1f}/{total/1024**2:.1f} MB · {done*100/total:.1f}%')
                            stream.flush()
                            os.fsync(stream.fileno())
                        except (urllib.error.URLError, TimeoutError, OSError) as error:
                            stream.flush()
                            os.fsync(stream.fileno())
                            last_error = error
            except BridgeError:
                raise
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                last_error = error
            received = partial.stat().st_size if partial.exists() else 0
            if received == expected:
                if source_used is not None:
                    source_used.append((target.name, source))
                last_error = None
                break
            last_error = OSError(
                f'model source returned {received} of {expected} bytes')
        received = partial.stat().st_size if partial.exists() else 0
        if last_error is not None:
            _network_error(last_error)
    check_control(control)
    if not partial.exists() or partial.stat().st_size != expected:
        _error('模型下载未完成，已有分段已保留；请点击继续下载', 'VISION_DOWNLOAD_INCOMPLETE')
    progress(min(97, int((completed + expected)*94/total)), '正在校验 '+metadata['name'])
    if _hash_file(partial, control) != metadata['sha256']:
        partial.unlink(missing_ok=True)
        _error('模型文件校验失败，已移除损坏分段，请重新下载', 'VISION_MODEL_HASH')
    check_control(control)
    os.replace(partial, target)


class VisionCatalogMixin:
    def video_getInstalledVisionModels(self, data):
        return {'items':installed_models()}

    def video_listVisionModels(self, data):
        search = data.get('search','')
        task = data.get('task','all')
        if not isinstance(search,str) or len(search)>160 or any(ord(c)<32 for c in search):
            _error('模型搜索词无效或过长')
        search = search.strip()
        if task not in (*_TASKS, 'all', 'recommended'):
            _error('不支持的视觉任务分类')
        installed = installed_models()
        if task == 'recommended':
            items = []
            for entry in _CURATED:
                if search and search.casefold() not in (entry['repoId']+' '+entry['name']).casefold():
                    continue
                item = _item({'id':entry['repoId'], 'tags':['license:'+entry['license']]}, installed)
                items.append({**item, **entry, 'sourceUrl':_HF+'/'+entry['repoId']})
            return {'items':items, 'nextCursor':None, 'installedModels':installed, 'source':'recommended'}
        cursor = data.get('cursor')
        if cursor:
            if not isinstance(cursor,str) or len(cursor)>32000:
                _error('目录页码无效，请重新搜索')
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4)))
                if decoded['search'] != search or decoded['task'] != task:
                    raise ValueError('different search')
                urls = decoded['urls']
                if not isinstance(urls,list) or not 1 <= len(urls) <= len(_TASKS):
                    raise ValueError('invalid cursor')
                urls = [_api_page_url(url) for url in urls]
            except (ValueError, TypeError, KeyError):
                _error('目录页码无效，请重新搜索')
        else:
            tasks = _TASKS if task == 'all' else (task,)
            urls = [_HF+'/api/models?'+urllib.parse.urlencode({'pipeline_tag':category, 'sort':'downloads',
                    'direction':-1, 'limit':12 if task=='all' else 24, 'full':'true', 'config':'true',
                    **({'search':search} if search else {})}) for category in tasks]
        items, next_urls, seen = [], [], set()
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(_json_request, urls))
        for rows, headers in replies:
            if not isinstance(rows,list):
                _error('模型目录返回了无法读取的数据')
            for row in rows:
                if not isinstance(row,dict):
                    continue
                item = _item(row,installed)
                if item and item['repoId'] not in seen:
                    seen.add(item['repoId'])
                    items.append(item)
            if link := _next_link(headers):
                next_urls.append(link)
        return {'items':items, 'nextCursor':_encode_cursor({'search':search,'task':task,'urls':next_urls}) if next_urls else None,
                'installedModels':installed, 'source':'huggingface'}

    def video_getVisionModelFiles(self, data):
        return _files_for_repo(_repo_id(data.get('repoId')))

    def video_downloadVisionModel(self, data):
        repo = _repo_id(data.get('repoId'))
        model_name = _file_name(data.get('modelFile'))
        projector_name = _file_name(data.get('projectorFile'))
        detail = _files_for_repo(repo)
        if not detail['compatible']:
            _error(detail['unsupportedReason'], 'VISION_MODEL_UNSUPPORTED')
        model = next((row for row in detail['files'] if row['name']==model_name),None)
        projector = next((row for row in detail['projectors'] if row['name']==projector_name),None)
        if not model or not projector or projector_name not in model['projectorFiles']:
            _error('所选模型与视觉投影器无法配对，请重新选择模型文件')
        model_id = _model_id(repo, model_name, projector_name)
        name = str(data.get('name') or detail['name'])[:160]
        revision = detail['revision']
        total = model['size'] + projector['size']

        def work(progress, control):
            with _LOCKS_GUARD:
                lock = _LOCKS.setdefault(model_id,threading.Lock())
            if not lock.acquire(blocking=False):
                _error('这个模型正在下载，请等待现有任务完成', 'VISION_DOWNLOAD_BUSY')
            try:
                root = _safe_models_root()
                folder = _safe_destination(root,model_id)
                folder.mkdir(exist_ok=True)
                needed = sum(max(0,row['size']-(path.stat().st_size if path.exists() else
                            (path.with_name(path.name+'.partial').stat().st_size
                             if path.with_name(path.name+'.partial').exists() else 0)))
                             for row,path in ((model,folder/'model.gguf'),(projector,folder/'mmproj.gguf')))
                if shutil.disk_usage(folder).free < needed + 100*1024**2:
                    _error('可用磁盘空间不足，请至少保留模型大小加 100MB 空间', 'VISION_DOWNLOAD_SPACE')
                progress(0,'正在准备模型下载；取消后可继续下载')
                used_sources = []
                _download_file(repo,revision,model,_safe_destination(folder,'model.gguf'),0,total,progress,control,
                               used_sources)
                _download_file(repo,revision,projector,_safe_destination(folder,'mmproj.gguf'),model['size'],total,
                               progress,control,used_sources)
                check_control(control)
                manifest = {'id':model_id,'name':name,'modelFile':'model.gguf','mmprojFile':'mmproj.gguf',
                    'modelSize':model['size'],'mmprojSize':projector['size'],
                    'modelSha256':model['sha256'],'mmprojSha256':projector['sha256'],
                    'repoId':repo,'modelSourceFile':model_name,'projectorSourceFile':projector_name,
                    'sourceUrl':detail['sourceUrl'],'revision':revision,'license':detail['license'],
                    'architecture':detail['architecture'],
                    'downloadSource':used_sources[-1][1] if used_sources else '',
                    'downloadSources':dict(used_sources)}
                stage = _safe_destination(folder,'manifest.json.staging')
                stage.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
                check_control(control)
                os.replace(stage,_safe_destination(folder,'manifest.json'))
                progress(100,'模型已下载、校验并安装，可切换使用')
                return {'modelId':model_id,'name':name,'installed':True,'repoId':repo}
            finally:
                lock.release()

        return self.api.tasks.start('下载视觉模型：'+name, work, category='model',
                                    location={'route':'/editor/smart'})
