"""Bounded JSON transfers for files dropped into the WebView2 editor.

Browser File objects intentionally hide their source paths. Copy their bytes
into the current project, or the persistent local video-tool import directory.
"""
from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
import uuid

from app.ui2.common import BridgeError

CHUNK_SIZE = 262144
MAX_FILE_SIZE = 4 * 1024 ** 3
IDLE_SECONDS = 600
MAX_UPLOADS = 8
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.mts',
                    '.m2ts', '.ts', '.mpeg', '.mpg', '.wmv', '.flv', '.3gp'}
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.wma'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}


def _error(message, code='UPLOAD_INVALID'):
    raise BridgeError(code, message)


def _project_identity(api):
    if getattr(api.ctx, 'project_id', None) is None:
        _error('请先打开或新建项目', 'NO_PROJECT')
    project = api.project_current()
    database = project.get('database_path') if isinstance(project, dict) else None
    if not isinstance(database, str) or not database:
        _error('当前项目路径无法读取', 'NO_PROJECT')
    path = Path(database).resolve()
    if not path.is_absolute() or not path.parent.is_dir():
        _error('当前项目目录不存在', 'NO_PROJECT')
    return getattr(api.ctx, 'project_id'), path


def _tool_import_root():
    """Persistent per-installation tool files; this app lives in the user's folder."""
    return Path(__file__).resolve().parent / 'runtime' / 'timeline'


def _tool_identity(*, create=False):
    root = Path(_tool_import_root()).absolute()
    # The helper identifies Backend/runtime/timeline. Resolve each child from
    # Backend so an existing runtime/timeline link cannot establish a new root.
    anchor = root.parent.parent.resolve()
    for directory in (root.parent, root):
        if directory.is_symlink() or directory.resolve() != directory:
            _error('视频工具导入目录已变化，请重新拖入视频')
        if create:
            directory.mkdir(exist_ok=True)
        if (not directory.is_dir() or not directory.resolve().is_relative_to(anchor)
                or directory.resolve() != directory):
            _error('视频工具导入目录已变化，请重新拖入视频')
    return 'tools', root


def _tool_directories_valid(session):
    """Do not continue or clean up through a replaced directory or junction."""
    for directory, device, inode in session.get('directories', ()):
        if directory.is_symlink() or directory.resolve() != directory:
            return False
        current = directory.stat()
        if not directory.is_dir() or (current.st_dev, current.st_ino) != (device, inode):
            return False
    return True


def _name(value, *, audio=False):
    if (not isinstance(value, str) or not value or len(value) > 240
            or value[-1] in '. ' or any(ord(c) < 32 for c in value)
            or any(c in '<>:"/\\|?*' for c in value)
            or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I)
            or Path(value).suffix.lower() not in (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS if audio else VIDEO_EXTENSIONS)):
        _error('请拖入有效的本地媒体文件，文件名不能含路径或特殊控制字符')
    return value


class UploadMixin:
    def _init_drop_uploads(self):
        self._drop_lock = threading.RLock()
        self._drop_uploads = {}
        self._drop_reaper = None
        self._drop_wakeup = threading.Event()

    def _drop_remove(self, upload_id):
        session = self._drop_uploads.pop(upload_id, None)
        if session is None:
            return
        try:
            session['stream'].close()
        except OSError:
            pass
        # Only remove our own partial file and its empty unique directory.
        # A changed directory link must not redirect cleanup outside the project.
        folder, root = session['folder'], session['root']
        try:
            if (folder.resolve().is_relative_to(root) and not folder.is_symlink()
                    and _tool_directories_valid(session)):
                session['part'].unlink(missing_ok=True)
                folder.rmdir()
        except OSError:
            pass

    def _abort_drop_uploads(self):
        with self._drop_lock:
            for upload_id in list(self._drop_uploads):
                self._drop_remove(upload_id)
            self._drop_wakeup.set()

    def _discard_changed_drop_uploads(self):
        with self._drop_lock:
            try:
                identity = _project_identity(self.api)
            except (BridgeError, OSError, ValueError):
                identity = None
            for upload_id, session in list(self._drop_uploads.items()):
                if session.get('scope') == 'tools':
                    try:
                        if (session['identity'] == _tool_identity()
                                and _tool_directories_valid(session)):
                            continue
                    except (BridgeError, OSError, ValueError, RuntimeError):
                        pass
                    self._drop_remove(upload_id)
                    continue
                if session['identity'] != identity:
                    self._drop_remove(upload_id)

    def _expire_drop_uploads(self):
        with self._drop_lock:
            now = time.monotonic()
            for upload_id, session in list(self._drop_uploads.items()):
                if now - session['updated'] >= IDLE_SECONDS:
                    self._drop_remove(upload_id)

    def _start_drop_reaper(self):
        if self._drop_reaper is not None and self._drop_reaper.is_alive():
            return

        def reap():
            while True:
                self._drop_wakeup.wait(30)
                self._drop_wakeup.clear()
                with self._drop_lock:
                    self._expire_drop_uploads()
                    if not self._drop_uploads:
                        self._drop_reaper = None
                        return

        self._drop_reaper = threading.Thread(target=reap, name='aive-drop-cleanup', daemon=True)
        self._drop_reaper.start()

    def _drop_session(self, data):
        upload_id = data.get('uploadId') if isinstance(data, dict) else None
        if not isinstance(upload_id, str) or not re.fullmatch('[0-9a-f]{32}', upload_id):
            _error('视频传输编号无效，请重新拖入视频')
        self._expire_drop_uploads()
        session = self._drop_uploads.get(upload_id)
        if session is None:
            _error('视频传输已取消或过期，请重新拖入视频', 'UPLOAD_EXPIRED')
        try:
            if session.get('scope') == 'tools':
                if (session['identity'] != _tool_identity()
                        or not _tool_directories_valid(session)):
                    _error('视频工具导入目录已变化，请重新拖入视频')
            elif session['identity'] != _project_identity(self.api):
                _error('项目已切换，请在当前项目重新拖入视频', 'UPLOAD_PROJECT_CHANGED')
            if (session['folder'].is_symlink()
                    or not session['folder'].resolve().is_relative_to(session['root'])):
                _error('视频导入目录已变化，请重新拖入视频')
        except BaseException:
            self._drop_remove(upload_id)
            raise
        return upload_id, session

    def video_uploadBegin(self, data):
        if not isinstance(data, dict):
            _error('素材传输信息无效')
        if 'scope' in data and data['scope'] != 'tools':
            _error('素材传输范围无效')
        scope = data.get('scope')
        name, size = _name(data.get('name'), audio=scope == 'tools'), data.get('size')
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_FILE_SIZE:
            _error('仅支持大于 0 且不超过 4 GiB 的媒体文件')
        with self._drop_lock:
            self._expire_drop_uploads()
            self._discard_changed_drop_uploads()
            identity = _tool_identity(create=True) if scope == 'tools' else _project_identity(self.api)
            root = identity[1] if scope == 'tools' else identity[1].parent
            if len(self._drop_uploads) >= MAX_UPLOADS:
                _error('正在传输的素材过多，请等待当前导入完成', 'UPLOAD_BUSY')
            pending_bytes = sum(s['size'] - s['received'] for s in self._drop_uploads.values())
            if shutil.disk_usage(root).free < size + pending_bytes + 16 * 1024**2:
                message = '导入所在磁盘空间不足，请清理空间后重试' if scope == 'tools' else '项目所在磁盘空间不足，请清理空间后重试'
                _error(message, 'UPLOAD_NO_SPACE')
            target_root = root / 'imports' / 'dropped'
            folder, stream = None, None
            try:
                # Resolve every existing/new parent before creating upload files.
                for parent in (root / 'imports', target_root):
                    if (not parent.resolve().is_relative_to(root)
                            or scope == 'tools' and parent.resolve() != parent):
                        _error('项目导入目录指向外部位置，请检查项目目录')
                    parent.mkdir(exist_ok=True)
                    if (not parent.resolve().is_relative_to(root)
                            or scope == 'tools' and parent.resolve() != parent):
                        _error('项目导入目录指向外部位置，请检查项目目录')
                upload_id = uuid.uuid4().hex
                folder = target_root / upload_id
                folder.mkdir()
                directories = ()
                if scope == 'tools':
                    paths = (root.parent, root, root / 'imports', target_root, folder)
                    directories = tuple((path, path.stat().st_dev, path.stat().st_ino) for path in paths)
                    if not _tool_directories_valid({'directories': directories}):
                        _error('视频工具导入目录已变化，请重新拖入视频')
                part = folder / 'upload.part'
                stream = open(part, 'xb')
                self._drop_uploads[upload_id] = {
                    'name': name, 'size': size, 'received': 0, 'stream': stream,
                    'identity': identity, 'root': root, 'folder': folder, 'part': part,
                    'scope': scope, 'directories': directories,
                    'updated': time.monotonic(),
                }
                self._start_drop_reaper()
                return {'uploadId': upload_id, 'chunkSize': CHUNK_SIZE}
            except BaseException:
                if folder is not None:
                    self._drop_uploads.pop(folder.name, None)
                if stream is not None:
                    stream.close()
                if folder is not None:
                    try:
                        (folder / 'upload.part').unlink(missing_ok=True)
                        folder.rmdir()
                    except OSError:
                        pass
                raise

    def video_uploadChunk(self, data):
        with self._drop_lock:
            upload_id, session = self._drop_session(data)
            try:
                offset, encoded = data.get('offset'), data.get('base64')
                if (isinstance(offset, bool) or not isinstance(offset, int)
                        or offset != session['received']):
                    _error('视频传输位置不一致，请重新拖入视频')
                if (not isinstance(encoded, str) or not encoded
                        or len(encoded) > 4 * ((CHUNK_SIZE + 2) // 3)):
                    _error('视频传输数据块大小无效')
                try:
                    chunk = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    _error('视频传输数据块无效')
                if (not 0 < len(chunk) <= CHUNK_SIZE
                        or offset + len(chunk) > session['size']):
                    _error('视频传输字节数超过预期')
                session['stream'].write(chunk)
                session['received'] += len(chunk)
                session['updated'] = time.monotonic()
                return {'received': session['received']}
            except BaseException:
                self._drop_remove(upload_id)
                raise

    def video_uploadFinish(self, data):
        with self._drop_lock:
            upload_id, session = self._drop_session(data)
            try:
                if session['received'] != session['size']:
                    _error('素材尚未完整传输，请重新拖入')
                stream = session['stream']
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                output = session['folder'] / session['name']
                # UUID folders are private; still never overwrite an appearing file.
                if os.name == 'nt':
                    os.rename(session['part'], output)
                else:
                    os.link(session['part'], output)
                    session['part'].unlink()
                self._drop_uploads.pop(upload_id)
                return {'path': str(output)}
            except BaseException:
                self._drop_remove(upload_id)
                raise

    def video_uploadAbort(self, data):
        upload_id = data.get('uploadId') if isinstance(data, dict) else None
        if not isinstance(upload_id, str) or not re.fullmatch('[0-9a-f]{32}', upload_id):
            _error('视频传输编号无效')
        with self._drop_lock:
            self._drop_remove(upload_id)
        return {}


def install_lifecycle_hook(api_class):
    """Keep the existing authorization/dispatch and clean pending copies afterward."""
    previous = getattr(api_class, 'invoke', None)
    if previous is None or getattr(previous, '_aive_drop_lifecycle', False):
        return

    def invoke(api, action, data):
        video = getattr(api, 'groups', {}).get('video')
        cleanup_action = action in ('license.logout', 'app.shutdown')
        project_action = action.startswith('project.')
        if video is None or not hasattr(video, '_drop_lock') or not (cleanup_action or project_action):
            return previous(api, action, data)
        with video._drop_lock:
            result = previous(api, action, data)
            if cleanup_action:
                video._abort_drop_uploads()
                language=sys.modules.get('_aive_language_models') or sys.modules.get('language_models')
                if language is not None:language.stop()
            else:
                video._discard_changed_drop_uploads()
            return result

    invoke._aive_drop_lifecycle = True
    api_class.invoke = invoke
