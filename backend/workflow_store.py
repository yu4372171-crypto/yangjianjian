"""Per-project recovery journal. It never stores credentials or executable code."""
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
import threading

_active=set()
_active_lock=threading.RLock()


def _stamp(path):
    path = Path(path)
    if not path.is_absolute() or '://' in str(path) or str(path).startswith(('\\\\', '//')):
        raise ValueError('恢复任务只支持本机完整素材路径')
    stat = path.stat()
    return [str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ino]


def _safe(value):
    if isinstance(value, dict):
        if any(str(k).lower() in ('apikey', 'api_key', 'authorization', 'password', 'secret', 'token') for k in value):
            raise ValueError('恢复记录禁止保存密钥')
        for child in value.values():
            _safe(child)
    elif isinstance(value, list):
        for child in value:
            _safe(child)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()


class WorkflowStore:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.root = self.project / '.aive_workflows'
        self.root.mkdir(exist_ok=True)
        if self.root.is_symlink() or not self.root.resolve().is_relative_to(self.project):
            raise ValueError('恢复目录超出项目范围')

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise ValueError('恢复任务编号无效')
        if self.root.is_symlink() or not self.root.resolve().is_relative_to(self.project):
            raise ValueError('恢复目录已变化')
        path = self.root / (identifier + '.json')
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('恢复记录路径无效')
        return path

    def begin(self, request, configuration):
        _safe(request)
        request = copy.deepcopy(request)
        request.pop('resumeId', None)
        stamps = [_stamp(p) for p in request.get('paths', [])]
        for path in (request.get('bgmPath'),):
            if path:
                stamps.append(_stamp(path))
        data = {'schema': 1, 'id': uuid.uuid4().hex, 'request': request, 'sources': stamps,
                'configuration': fingerprint(configuration), 'status': 'running',
                'stage': 'understanding', 'stages': {}, 'created': datetime.now().isoformat(timespec='seconds')}
        run = Run(self, data)
        run.flush()
        return run

    def resume(self, identifier, configuration):
        with _active_lock:
            if (str(self.root),identifier) in _active:
                raise ValueError('此任务正在运行，请等待或取消后再继续')
        path = self.path(identifier)
        if path.stat().st_size > 16 * 1024 ** 2:
            raise ValueError('恢复记录过大')
        data = json.loads(path.read_text('utf8'))
        if data.get('schema') != 1 or data.get('id') != identifier:
            raise ValueError('恢复记录格式无效')
        _safe(data)
        if data['configuration'] != fingerprint(configuration):
            raise ValueError('模型或配置已变化，请使用新设置重新生成')
        if any(_stamp(row[0]) != row for row in data['sources']):
            raise ValueError('素材已变化，请重新生成')
        data['status'] = 'running'
        return Run(self, data)

    def list(self):
        items = []
        for path in sorted(self.root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            try:
                if path.is_symlink() or path.stat().st_size > 16 * 1024 ** 2:
                    continue
                row = json.loads(path.read_text('utf8'))
                with _active_lock:
                    # A completed job can publish its status just before the
                    # worker releases the in-process claim. Never hide a
                    # finished journal during that short, legitimate gap;
                    # only a running record is unsafe to resume concurrently.
                    if (row.get('status') == 'running'
                            and (str(self.root),row.get('id')) in _active):
                        continue
                items.append({'id': row['id'], 'text': row['request']['text'],
                    'created': row['created'], 'stage': row.get('stage', ''),
                    'completedStages': list(row.get('stages', {})),
                    'status': row['status'], 'code': row.get('code', ''),
                    'output': row.get('output', '')})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return items


class Run:
    def __init__(self, store, data):
        self.store, self.data, self.identifier = store, data, data['id']

    @property
    def request(self):
        return copy.deepcopy(self.data['request'])

    def flush(self):
        _safe(self.data)
        path = self.store.path(self.identifier)
        temporary = self.store.root / (uuid.uuid4().hex + '.partial')
        try:
            with temporary.open('x', encoding='utf8') as stream:
                json.dump(self.data, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, stage):
        return copy.deepcopy(self.data['stages'].get(stage))

    def claim(self):
        with _active_lock:
            key=(str(self.store.root),self.identifier)
            if key in _active:
                raise ValueError('此任务正在运行')
            _active.add(key)

    def release(self):
        with _active_lock:
            _active.discard((str(self.store.root),self.identifier))

    def save(self, stage, value):
        self.data['stages'][stage] = copy.deepcopy(value)
        self.data['stage'] = stage
        self.flush()

    def fail(self, code):
        self.data.update(status='failed', code=str(code)[:100])
        self.flush()

    def finish(self, path):
        self.data.update(status='done', output=str(path))
        self.data.pop('code', None)
        self.flush()
