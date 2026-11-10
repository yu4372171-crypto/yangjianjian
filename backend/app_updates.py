"""Signed release discovery, verified downloads and a detached Windows installer."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.ui2.common import BridgeError
from app.workers.control import check_control

APP = Path(__file__).resolve().parent.parent
PRODUCT = 'yangyu-autoedit'
MAX_PACKAGE = 2 * 1024 ** 3
MAX_JSON = 1024 * 1024
DEFAULT_PRODUCT_CODE = 'VIDEO_EDITOR'
DEFAULT_APPLICATION_ID = 'VIDEO_EDITOR'
DEFAULT_PACKAGE_ID = 'VIDEO_EDITOR-Windows-x64'
UPDATER_VERSION = '1.0.0'


def fail(message, code='UPDATE_INVALID'):
    raise BridgeError(code, message)


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,5}(?:\.\d{1,5}){3}', value):
        fail('更新版本号格式无效')
    return tuple(int(part) for part in value.split('.'))


def validate_url(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 33 for c in value):
        fail('更新地址格式无效')
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        fail('更新地址格式无效')
    local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if (not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.fragment or '\\' in value or parsed.scheme not in ('https', 'http')
            or (parsed.scheme == 'http' and not local) or port == 0):
        fail('更新地址需要 HTTPS；本机测试可使用回环 HTTP 地址')
    return value


def same_origin(first, second):
    """Keep the signed installer on the feed's HTTPS origin."""
    left, right = urllib.parse.urlsplit(first), urllib.parse.urlsplit(second)
    left_port = left.port or (443 if left.scheme == 'https' else 80)
    right_port = right.port or (443 if right.scheme == 'https' else 80)
    return (left.scheme, left.hostname, left_port) == (right.scheme, right.hostname, right_port)


def service_base_url(value):
    """Validate the fixed account/update service; customers never choose it."""
    if not isinstance(value, str) or not value or len(value) > 512:
        return ''
    try:
        validate_url(value)
        parsed = urllib.parse.urlsplit(value)
    except (BridgeError, ValueError):
        return ''
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        return ''
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


class OnlineHTTPError(Exception):
    def __init__(self, status, message, code=''):
        super().__init__(message)
        self.status = status
        self.code = code


def _server_message(value, status):
    if isinstance(value, dict):
        candidate = value.get('message') or value.get('detail') or value.get('error_description')
        data = value.get('data')
        if not candidate and isinstance(data, dict):
            candidate = data.get('message') or data.get('detail')
        if isinstance(candidate, str) and candidate.strip():
            cleaned = re.sub(r'[\r\n\t]+', ' ', candidate).strip()
            return cleaned[:240]
    if status == 401:
        return '在线账号会话已失效，请重新登录'
    if status == 403:
        return '当前账号没有使用此更新服务的权限'
    if status == 404:
        return '在线更新服务没有找到可用版本'
    if status == 429:
        return '更新请求过于频繁，请稍后重试'
    if status >= 500:
        return '在线更新服务暂时不可用，请稍后重试'
    return f'在线更新服务返回 HTTP {status}'


def _normal_key(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())


def _walk_mappings(value, depth=0):
    if depth > 8:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child, depth + 1)
    elif isinstance(value, list):
        for child in value[:100]:
            yield from _walk_mappings(child, depth + 1)


def _first_value(value, keys):
    wanted = {_normal_key(key) for key in keys}
    for mapping in _walk_mappings(value):
        for key, item in mapping.items():
            if _normal_key(key) in wanted and item is not None:
                return item
    return None


def _first_text(value, keys):
    item = _first_value(value, keys)
    if isinstance(item, (str, int)) and not isinstance(item, bool):
        return str(item).strip()
    return ''


def _find_prefixed_token(value, prefix):
    for mapping in _walk_mappings(value):
        for item in mapping.values():
            if isinstance(item, str) and item.startswith(prefix) and len(item) <= 4096:
                return item
    return ''


_BLOCK_TAGS = frozenset({'br', 'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'})
_HIDDEN_TAGS = frozenset({'script', 'style', 'template', 'noscript'})


def _tag_token(value, start):
    """Return (end, lower-name, closing, self-closing) for a real tag token."""
    index = start + 1
    length = len(value)
    if index >= length or not value[index].isascii():
        return None
    closing = value[index] == '/'
    if closing:
        index += 1
    if index >= length or not (value[index].isalpha() and value[index].isascii()):
        return None
    name_start = index
    while index < length and (
            (value[index].isascii() and value[index].isalnum())
            or value[index] in ':-'):
        index += 1
    name = value[name_start:index].casefold()
    quote = ''
    while index < length:
        character = value[index]
        if quote:
            if character == quote:
                quote = ''
        elif character in ('"', "'"):
            quote = character
        elif character == '>':
            before = value[name_start:index].rstrip()
            return index + 1, name, closing, before.endswith('/')
        index += 1
    return None


def _find_closing_tag(value, start, name):
    index = start
    while index < len(value):
        index = value.find('<', index)
        if index < 0:
            return None
        token = _tag_token(value, index)
        if token and token[1] == name and token[2]:
            return token[0]
        index += 1
    return None


def _plain_notes(value):
    if isinstance(value, list):
        value = '\n'.join(str(item) for item in value[:200])
    if not isinstance(value, str):
        return ''
    if '<' in value and '>' in value:
        # The frozen app includes html.entities but not html.parser. This small
        # scanner handles release-note markup without executing or rendering it.
        parts = []
        index = 0
        while index < len(value):
            opening = value.find('<', index)
            if opening < 0:
                parts.append(value[index:])
                break
            parts.append(value[index:opening])
            if value.startswith('<!--', opening):
                closing = value.find('-->', opening + 4)
                if closing < 0:
                    break
                index = closing + 3
                continue
            token = _tag_token(value, opening)
            if token is None:
                parts.append('<')
                index = opening + 1
                continue
            end, name, closing, self_closing = token
            if name in _BLOCK_TAGS:
                parts.append('\n')
            if name in _HIDDEN_TAGS and not closing and not self_closing:
                hidden_end = _find_closing_tag(value, end, name)
                if hidden_end is None:
                    break
                parts.append('\n')
                index = hidden_end
                continue
            index = end
        value = unescape(''.join(parts))
    value = value.replace('\u00a0', ' ')
    value = re.sub(r'[ \t\f\v]+', ' ', value)
    value = re.sub(r'\n\s*\n+', '\n', value)
    return value.strip()[:16000]

def _notes_text(data, release):
    for source in (release, data):
        for key, value in source.items():
            if _normal_key(key) in {'notes', 'noteshtml', 'releasenotes', 'releasenoteshtml',
                                     'changelog', 'description'}:
                text = _plain_notes(value)
                if text:
                    return text
    return ''


class UpdateRedirect(urllib.request.HTTPRedirectHandler):
    """Keep authenticated calls on their origin and never downgrade HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if old.scheme == 'https' and new.scheme != 'https':
            fail('更新下载不允许转到不安全的地址')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        # urllib copies caller-supplied headers across an origin boundary.
        # Follow a signed CDN redirect only without credentials or custom
        # signature headers; a signature URL in the redirect target is enough.
        if not same_origin(req.full_url, newurl):
            safe_headers = {'user-agent', 'accept', 'accept-encoding',
                            'cache-control', 'range'}
            names = set(redirected.headers) | set(redirected.unredirected_hdrs)
            for name in names:
                if name.casefold() in safe_headers:
                    continue
                redirected.remove_header(name)
                redirected.unredirected_hdrs.pop(name, None)
                redirected.unredirected_hdrs.pop(name.lower(), None)
        return redirected


class StrictUpdateRedirect(UpdateRedirect):
    """Reject a service API redirect to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not same_origin(req.full_url, newurl):
            fail('在线更新服务返回了不安全的重定向地址', 'UPDATE_PROTOCOL')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, offset=0, bearer='', headers=None):
    validate_url(url)
    if type(offset) is not int or offset < 0:
        fail('更新续传位置无效')
    request_headers = {'User-Agent': 'YangyuAutoEdit-Updater/1',
                       'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'}
    if headers:
        if not isinstance(headers, dict) or len(headers) > 20:
            fail('更新下载请求头无效', 'UPDATE_PROTOCOL')
        for name, value in headers.items():
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,80}', name)
                    or not isinstance(value, str) or len(value) > 1024
                    or any(ord(char) < 32 for char in value)
                    or name.casefold() in ('authorization', 'cookie', 'proxy-authorization',
                                           'range', 'host', 'content-length')):
                continue
            request_headers[name] = value
    if bearer:
        if not isinstance(bearer, str) or len(bearer) > 4096 or any(ord(c) < 33 for c in bearer):
            fail('在线更新凭证无效', 'UPDATE_AUTH')
        request_headers['Authorization'] = 'Bearer ' + bearer
    if offset:
        request_headers['Range'] = f'bytes={offset}-'
    request = urllib.request.Request(url, headers=request_headers)
    return urllib.request.build_opener(UpdateRedirect()).open(request, timeout=20)


def service_json(base_url, path, *, method='GET', payload=None, bearer='', timeout=20):
    base_url = service_base_url(base_url)
    if not base_url:
        fail('在线更新服务地址无效', 'UPDATE_CONFIG')
    url = base_url + path
    validate_url(url)
    headers = {
        'User-Agent': 'Yangjianjian-Updater/1',
        'Accept': 'application/json',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    }
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf8')
        headers['Content-Type'] = 'application/json'
    if bearer:
        if not isinstance(bearer, str) or len(bearer) > 4096 or any(ord(c) < 33 for c in bearer):
            fail('在线更新凭证无效', 'UPDATE_AUTH')
        headers['Authorization'] = 'Bearer ' + bearer
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(StrictUpdateRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(MAX_JSON + 1)
    except urllib.error.HTTPError as error:
        try:
            raw = error.read(MAX_JSON + 1)
            try:
                detail = json.loads(raw.decode('utf-8-sig'))
            except (ValueError, UnicodeError):
                detail = {}
            message = _server_message(detail, error.code)
            code = _first_text(detail, ('code', 'errorCode', 'error_code'))
        finally:
            error.close()
        raise OnlineHTTPError(error.code, message, code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OnlineHTTPError(0, '无法连接在线更新服务，请检查网络后重试') from None
    if len(raw) > MAX_JSON:
        fail('在线更新服务返回的数据过大', 'UPDATE_PROTOCOL')
    try:
        value = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError):
        fail('在线更新服务返回的数据格式无效', 'UPDATE_PROTOCOL')
    if not isinstance(value, dict):
        fail('在线更新服务返回的数据格式无效', 'UPDATE_PROTOCOL')
    if value.get('ok') is False or value.get('success') is False:
        status = 401 if _normal_key(value.get('code', '')) in ('unauthorized', 'authenticationrequired') else 400
        raise OnlineHTTPError(status, _server_message(value, status),
                              _first_text(value, ('code', 'errorCode', 'error_code')))
    return value


def read_json(path, limit=131072):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        fail('更新记录过大')
    return json.loads(data.decode('utf-8-sig'))


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        with temporary.open('x', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


class UpdateService:
    def __init__(self, app=APP):
        self.app = Path(app).resolve()
        self.cache = self.app / 'Backend/runtime/app_updates'
        self.lock = threading.RLock()
        self.phase, self.error, self.progress = 'idle', '', 0
        self.latest, self.envelope = None, None
        self.package = None
        self.last_check = ''
        self.current = read_json(self.app / 'app-version.json')['version']
        version_tuple(self.current)
        try:
            self.channel = read_json(self.app / 'update-channel.json')
        except (OSError, ValueError, KeyError):
            self.channel = {'schema': 1, 'channel': 'stable', 'manifestUrl': '', 'publicKey': ''}
        if not isinstance(self.channel, dict):
            self.channel = {'schema': 1, 'channel': 'stable', 'manifestUrl': '', 'publicKey': ''}
        self.online_url = service_base_url(self.channel.get('accountServiceUrl', ''))
        self.product_code = self.channel.get('softwareProductCode', DEFAULT_PRODUCT_CODE)
        self.application_id = self.channel.get('applicationId', DEFAULT_APPLICATION_ID)
        self.package_id = self.channel.get('packageId', DEFAULT_PACKAGE_ID)
        if not all(isinstance(value, str) and value and len(value) <= 100
                   for value in (self.product_code, self.application_id, self.package_id)):
            self.online_url = ''
        self.online = {}
        self.session_generation = 0
        self.download_control = None
        self.online_identity = self._device_identity()
        self.application_instance_id = uuid.uuid4().hex
        self._safe_cache()
        try:
            settings = read_json(self.cache / 'settings.json')
        except (OSError, ValueError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        # Older public builds saved an empty source. It must not mask the
        # publisher's newly configured channel after an upgrade. Auto-check
        # remains a separate customer preference and is preserved below.
        self.url = settings.get('manifestUrl') or self.channel.get('manifestUrl', '')
        self.auto_check = settings.get('autoCheck', True) is True
        try:
            if self.url != '':
                validate_url(self.url)
        except BridgeError:
            self.url = self.channel.get('manifestUrl', '')
        if self.url and not self.channel.get('publicKey'):
            self.url = ''
        try:
            if self.url != '':
                validate_url(self.url)
        except BridgeError:
            self.url = ''
        if not self.url and not self.online_url:
            self.phase = 'unconfigured'
        elif self.online_url and not self.online:
            self.phase = 'login_required'
        self._online_changed()
        self._recover()

    def _device_identity(self):
        """Derive a stable pseudonymous device ID without persisting tokens."""
        raw = ''
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'SOFTWARE\Microsoft\Cryptography',
                    0,
                    winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0),
            ) as key:
                raw = str(winreg.QueryValueEx(key, 'MachineGuid')[0])
        except (ImportError, OSError, ValueError):
            raw = ''
        if not raw:
            raw = socket.gethostname() + '|' + str(self.app).casefold()
        machine_hash = hashlib.sha256(('yangjianjian|' + raw).encode('utf8')).hexdigest()
        return {
            'deviceId': machine_hash[:32],
            'machineCodeHash': hashlib.sha256(raw.encode('utf8')).hexdigest(),
            'deviceName': socket.gethostname()[:100],
        }

    def _online_changed(self):
        self.latest = self.envelope = self.package = None
        self.progress = 0
        self.online_artifact = None
        self.online_package_url = ''
        self.online_package_path = ''
        self.online_package_headers = {}
        self.online_package_artifact = ''
        self.online_package_sha = ''
        if not self.online and not self.url:
            self.phase = 'login_required' if self.online_url else 'unconfigured'

    @staticmethod
    def _response_data(response):
        if not isinstance(response, dict):
            return {}
        data = response.get('data')
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _artifact_id(row):
        if not isinstance(row, dict):
            return ''
        wanted = {_normal_key(key) for key in ('artifact_id', 'artifactId', 'id')}
        for key, value in row.items():
            if _normal_key(key) in wanted and isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value).strip()[:100]
        return ''

    @staticmethod
    def _artifact_kind(row):
        if not isinstance(row, dict):
            return ''
        wanted = {_normal_key(key) for key in ('kind', 'type', 'artifact_type', 'artifactType')}
        for key, value in row.items():
            if _normal_key(key) in wanted and isinstance(value, str):
                return value.strip()[:30]
        return ''

    @staticmethod
    def _artifact_text(row, keys):
        if not isinstance(row, dict):
            return ''
        wanted = {_normal_key(key) for key in keys}
        for key, value in row.items():
            if _normal_key(key) in wanted and isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value).strip()
        return ''

    def _choose_artifact(self, rows):
        normalized = []
        for row in rows[:100]:
            if not isinstance(row, dict):
                continue
            kind = self._artifact_kind(row)
            artifact_id = self._artifact_id(row)
            filename = self._artifact_text(row, ('filename', 'name'))
            size = self._artifact_text(row, ('size', 'size_bytes', 'sizeBytes'))
            sha = self._artifact_text(row, ('sha256', 'sha_256', 'checksum')).casefold()
            try:
                size = int(size)
            except (TypeError, ValueError):
                continue
            if not artifact_id or kind.casefold() not in ('setup', 'full'):
                continue
            if not 2 <= size <= MAX_PACKAGE:
                continue
            # This is a display name, never the local cache path. Permit the
            # product's Chinese release names while rejecting path syntax.
            if filename and (len(filename) > 180 or filename in ('.', '..')
                             or re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
                             or filename.endswith(('.', ' '))):
                continue
            if not re.fullmatch(r'[a-f0-9]{64}', sha):
                continue
            normalized.append({
                'artifactId': artifact_id, 'kind': kind, 'filename': filename,
                'size': size, 'sha256': sha, 'url': '',
            })
        if not normalized:
            fail('在线更新没有可安全安装的 Setup 或 Full 安装包', 'UPDATE_PROTOCOL')
        normalized.sort(key=lambda item: (
            0 if item['kind'].casefold() == 'setup' else 1,
            item['filename'].casefold(), item['artifactId'],
        ))
        return normalized[0]

    def _load_online_artifacts(self):
        if self.online_artifact:
            return copy.deepcopy(self.online_artifact)
        grant = self.online.get('grantId', '')
        if not grant:
            fail('在线更新没有返回下载授权', 'UPDATE_AUTH')
        path = f'/api/software-update/grants/{urllib.parse.quote(grant, safe="")}/artifacts'
        response = self._online_get(path)
        data = self._response_data(response)
        candidate_lists = []
        for container in (data, _first_value(data, ('release', 'update'))):
            if isinstance(container, dict):
                for key, value in container.items():
                    if _normal_key(key) in ('artifacts', 'files', 'assets') and isinstance(value, list):
                        candidate_lists.append(value)
        artifact = self._choose_artifact(candidate_lists[0] if candidate_lists else [])
        current_offer = self.latest or {}
        version = version_tuple(current_offer.get('version', self.current))
        if version <= version_tuple(self.current):
            fail('在线更新授权指向的版本不是新版本', 'UPDATE_PROTOCOL')
        payload = {
            'schema': 1, 'product': PRODUCT,
            'channel': self.channel.get('channel', 'stable'),
            'version': current_offer['version'], 'url': '',
            'size': artifact['size'], 'sha256': artifact['sha256'],
            'notes': str(current_offer.get('notes', ''))[:16000],
            'publishedAt': str(current_offer.get('publishedAt', ''))[:64],
        }
        with self.lock:
            self.online_artifact = artifact
            self.online['artifactId'] = artifact['artifactId']
            self.online['filename'] = artifact['filename']
            self.latest = payload
            self.envelope = {'online': True, 'offer': {
                'version': payload['version'], 'grantId': self.online.get('grantId', ''),
                'updateToken': self.online.get('updateToken', ''), 'artifact': artifact,
                'payload': payload,
            }}
        return copy.deepcopy(artifact)

    def _authorize_download(self, artifact):
        grant = self.online.get('grantId', '')
        artifact_id = artifact.get('artifactId', '')
        if not grant or not artifact_id:
            fail('在线更新下载授权不完整', 'UPDATE_AUTH')
        response = self._online_post('/api/software-update/download-authorization', {
            'grant_id': grant, 'artifact_id': artifact_id,
        })
        data = self._response_data(response)
        url = _first_text(data, ('url', 'download_url', 'downloadUrl', 'signed_url', 'signedUrl'))
        if not url:
            fail('在线更新服务没有返回下载地址', 'UPDATE_PROTOCOL')
        url = validate_url(url)
        filename = _first_text(data, ('filename', 'name'))
        size = _first_value(data, ('size', 'size_bytes', 'sizeBytes'))
        sha = _first_text(data, ('sha256', 'checksum')).casefold()
        if size is not None:
            try:
                size = int(size)
            except (TypeError, ValueError):
                fail('在线更新下载地址的大小无效', 'UPDATE_PROTOCOL')
            if size != artifact['size']:
                fail('在线更新服务返回的文件大小不一致', 'UPDATE_PROTOCOL')
        if sha and sha != artifact['sha256']:
            fail('在线更新服务返回的文件校验值不一致', 'UPDATE_PROTOCOL')
        if filename and artifact['filename'] and filename != artifact['filename']:
            fail('在线更新服务返回的文件名不一致', 'UPDATE_PROTOCOL')
        headers = {}
        for key, value in data.items():
            if _normal_key(key) == 'headers' and isinstance(value, dict):
                for header, item in value.items():
                    name = str(header)
                    if (name.casefold() in ('authorization', 'cookie', 'proxy-authorization')
                            or not re.fullmatch(r'[A-Za-z0-9-]{1,80}', name)
                            or not isinstance(item, str) or len(item) > 1024
                            or any(ord(char) < 32 for char in item)):
                        continue
                    headers[name] = item
        expires_in = _first_value(data, ('expires_in', 'expiresIn'))
        try:
            expires_in = int(expires_in or 240)
        except (TypeError, ValueError):
            expires_in = 240
        return {'url': url, 'headers': headers,
                'expiresAt': time.monotonic() + max(30, min(300, expires_in))}

    def establish_session(self, username, password):
        if not self.online_url:
            return self.status()
        if (not isinstance(username, str) or not isinstance(password, str)
                or not username.strip() or not password or len(username) > 128 or len(password) > 256):
            fail('账号信息无效，无法建立在线更新会话', 'UPDATE_LOGIN')
        with self.lock:
            self.clear_session()
            generation = self.session_generation
        device_id = self.online_identity['deviceId']
        os_version = platform.platform()[:80]
        modern = {
            'username': username.strip(), 'password': password,
            'product_id': self.product_code, 'device_id': device_id,
            'device_name': self.online_identity['deviceName'],
            'platform': 'Windows', 'os_version': os_version,
            'app_version': self.current, 'machine_id': self.online_identity['machineCodeHash'][:64],
        }
        try:
            response = service_json(
                self.online_url, '/api/v1/auth/login', method='POST', payload=modern
            )
        except OnlineHTTPError as error:
            if error.status != 422:
                raise BridgeError('UPDATE_LOGIN', error.args[0]) from None
            legacy = {
                'username': username.strip(), 'password': password,
                'product_id': self.product_code, 'machine_id': self.online_identity['machineCodeHash'][:64],
                'app_version': self.current, 'os_type': 'Windows',
                'os_version': os_version, 'device_install_id': device_id,
            }
            try:
                response = service_json(
                    self.online_url, '/api/v1/auth/login', method='POST', payload=legacy
                )
            except OnlineHTTPError as fallback:
                raise BridgeError('UPDATE_LOGIN', fallback.args[0]) from None
        data = response.get('data')
        if not isinstance(data, dict):
            fail('在线账号登录响应缺少授权信息', 'UPDATE_LOGIN')
        access = data.get('access_token') or data.get('accessToken')
        refresh = data.get('refresh_token') or data.get('refreshToken')
        if not isinstance(access, str) or len(access) < 8 or any(ord(c) < 33 for c in access):
            fail('在线账号未返回更新访问凭证', 'UPDATE_LOGIN')
        if refresh is not None and (not isinstance(refresh, str) or len(refresh) > 4096):
            fail('在线账号刷新凭证无效', 'UPDATE_LOGIN')
        expires_in = data.get('expires_in', data.get('expiresIn', 0))
        try:
            expires_at = time.monotonic() + max(60, min(86400, int(expires_in or 3600)))
        except (TypeError, ValueError):
            expires_at = time.monotonic() + 3600
        with self.lock:
            self._require_session_generation(generation)
            self.online = {
                'username': username.strip(), 'accessToken': access,
                'refreshToken': refresh or '', 'accessExpiresAt': expires_at,
                'sessionId': str(data.get('session_id') or data.get('sessionId') or '')[:100],
                'licenseId': str(data.get('license_id') or data.get('licenseId') or '')[:100],
                'updateToken': '', 'updateExpiresAt': 0,
                'grantId': '', 'artifactId': '', 'filename': '',
            }
            self._online_changed()
            self.phase, self.error = 'idle', ''
        return self.status()

    def clear_session(self):
        with self.lock:
            self.session_generation += 1
            if self.download_control:
                self.download_control['cancelled'].set()
            self.online = {}
            self._online_changed()
            self.phase = 'login_required' if self.online_url else ('idle' if self.url else 'unconfigured')
            self.error = ''
        return self.status()

    def _require_session_generation(self, generation):
        if generation != self.session_generation:
            fail('账号会话已变更，请重新检查更新', 'UPDATE_SESSION_CHANGED')

    def _refresh_access(self):
        generation = self.session_generation
        refresh = self.online.get('refreshToken', '')
        if not refresh:
            raise BridgeError('UPDATE_AUTH_EXPIRED', '在线登录已失效，请退出后重新登录')
        try:
            response = service_json(
                self.online_url, '/api/v1/auth/refresh', method='POST',
                payload={'refresh_token': refresh},
            )
        except OnlineHTTPError as error:
            with self.lock:
                self._require_session_generation(generation)
                self.clear_session()
            raise BridgeError('UPDATE_AUTH_EXPIRED', error.args[0]) from None
        self._require_session_generation(generation)
        data = response.get('data')
        access = data.get('access_token') if isinstance(data, dict) else None
        access = access or (data.get('accessToken') if isinstance(data, dict) else None)
        rotated = data.get('refresh_token') if isinstance(data, dict) else None
        rotated = rotated or (data.get('refreshToken') if isinstance(data, dict) else None)
        if (not isinstance(access, str) or not 8 <= len(access) <= 4096
                or any(ord(char) < 33 for char in access)):
            with self.lock:
                self._require_session_generation(generation)
                self.clear_session()
            raise BridgeError('UPDATE_AUTH_EXPIRED', '在线登录刷新失败，请重新登录')
        expires_in = data.get('expires_in', data.get('expiresIn', 3600))
        try:
            expires_at = time.monotonic() + max(60, min(86400, int(expires_in)))
        except (TypeError, ValueError):
            expires_at = time.monotonic() + 3600
        with self.lock:
            self._require_session_generation(generation)
            self.online['accessToken'] = access
            if isinstance(rotated, str) and rotated:
                self.online['refreshToken'] = rotated
            self.online['accessExpiresAt'] = expires_at
            self.online['updateToken'] = ''
            self.online['updateExpiresAt'] = 0
        return access

    def _online_check_request(self):
        generation = self.session_generation
        if not self.online:
            raise BridgeError('UPDATE_LOGIN_REQUIRED', '请先登录账号，再检查在线更新')
        for attempt in range(2):
            self._require_session_generation(generation)
            access = self.online.get('accessToken', '')
            if not access or (attempt == 0 and self.online.get('accessExpiresAt', 0) <= time.monotonic() + 30):
                access = self._refresh_access()
            granted = self.online.get('licenseId') or self.online.get('sessionId') or self.online['username']
            body = {
                'softwareProductCode': self.product_code,
                'installedApplicationId': self.application_id,
                'installedPackageId': self.package_id,
                'installedVersion': self.current,
                'platform': 'windows',
                'architecture': 'x64',
                'releaseChannel': self.channel.get('channel', 'stable'),
                'clientId': self.online_identity['deviceId'],
                'machineCodeHash': self.online_identity['machineCodeHash'],
                'activationIdentifier': str(granted)[:100],
                'licenseProof': '',
                'clientUpdaterVersion': UPDATER_VERSION,
                'applicationInstanceId': self.application_instance_id,
            }
            try:
                response = service_json(
                    self.online_url, '/api/software-update/check', method='POST',
                    payload=body, bearer=access,
                )
                self._require_session_generation(generation)
                if isinstance(response.get('data'), dict):
                    return response['data']
                fail('在线更新服务返回的数据格式无效', 'UPDATE_PROTOCOL')
            except OnlineHTTPError as error:
                self._require_session_generation(generation)
                if error.status in (401, 403) and attempt == 0:
                    self._refresh_access()
                    continue
                if error.status in (401, 403):
                    self.phase = 'login_required'
                    raise BridgeError('UPDATE_AUTH_EXPIRED', error.args[0]) from None
                raise
        raise BridgeError('UPDATE_AUTH_EXPIRED', '在线账号会话已失效，请重新登录')

    def _online_release(self, data):
        """Translate the open software-update response into a safe UI offer."""
        if not isinstance(data, dict):
            fail('在线更新服务没有返回有效的更新信息', 'UPDATE_PROTOCOL')

        release = data.get('release')
        if not isinstance(release, dict):
            release = data.get('update')
        if not isinstance(release, dict):
            release = data
        candidate = data.get('candidate')
        if isinstance(candidate, dict):
            release = candidate

        version = _first_text(release, ('version', 'targetVersion', 'target_version'))
        if not version:
            return None
        version_tuple(version)

        grant = (_first_text(data, ('grant_id', 'grantId'))
                 or _first_text(release, ('grant_id', 'grantId')))
        update_token = _find_prefixed_token(data, 'ypu_')
        if not update_token:
            candidate_token = _first_text(data, ('update_token', 'updateToken'))
            if candidate_token.startswith('ypu_'):
                update_token = candidate_token
        artifact = _first_value(release, ('artifacts', 'files'))
        root_artifacts = _first_value(data, ('artifacts', 'files'))
        artifacts = artifact if isinstance(artifact, list) else root_artifacts
        artifacts = artifacts if isinstance(artifacts, list) else []

        def artifact_value(row, keys):
            if not isinstance(row, dict):
                return None
            wanted = {_normal_key(key) for key in keys}
            for key, value in row.items():
                if _normal_key(key) in wanted and value is not None:
                    return value
            return None

        candidates = []
        for row in artifacts[:20]:
            if not isinstance(row, dict):
                continue
            kind = str(artifact_value(row, ('kind', 'type', 'artifact_type')) or '').strip()
            filename = str(artifact_value(row, ('filename', 'name')) or '').strip()
            artifact_id = str(artifact_value(row, ('artifact_id', 'artifactId', 'id')) or '').strip()
            size = artifact_value(row, ('size', 'size_bytes', 'sizeBytes'))
            sha = artifact_value(row, ('sha256', 'sha_256', 'checksum'))
            url = artifact_value(row, ('url', 'download_url', 'downloadUrl'))
            candidate = {
                'kind': kind, 'filename': filename, 'artifactId': artifact_id,
                'size': size, 'sha256': sha, 'url': url,
            }
            rank = {'setup': 0, 'full': 1}.get(kind.casefold(), 2)
            if kind.casefold() in ('setup', 'full'):
                candidates.append((rank, filename.casefold(), candidate))

        chosen = None
        root_url = artifact_value(data, ('download_url', 'downloadUrl', 'url'))
        root_size = artifact_value(data, ('size', 'size_bytes'))
        root_sha = artifact_value(data, ('sha256', 'checksum'))
        if candidates:
            chosen = self._choose_artifact(artifacts)
        elif root_url or root_size or root_sha:
            chosen = {'kind': '', 'filename': '', 'artifactId': '',
                      'size': root_size, 'sha256': root_sha, 'url': root_url}
        if not isinstance(chosen, dict):
            return {'version': version, 'grantId': grant, 'updateToken': update_token,
                    'artifact': None, 'payload': {
                        'schema': 1, 'product': PRODUCT,
                        'channel': self.channel.get('channel', 'stable'),
                        'version': version, 'url': '', 'size': 0, 'sha256': '',
                        'notes': _notes_text(data, release),
                        'publishedAt': _first_text(
                            release, ('published_at', 'publishedAt', 'created_at'))[:64],
                    }}

        artifact_id = str(chosen.get('artifactId') or '').strip()[:100]
        if artifact_id and not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', artifact_id):
            fail('在线更新文件标识无效', 'UPDATE_PROTOCOL')
        filename = str(chosen.get('filename') or '').strip()[:180]
        if filename and (re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
                         or filename.endswith(('.', ' '))):
            filename = ''
        size = chosen.get('size')
        if size is not None:
            try:
                size = int(size)
            except (TypeError, ValueError):
                fail('在线更新文件大小无效', 'UPDATE_PROTOCOL')
            if not 2 <= size <= MAX_PACKAGE:
                fail('在线更新文件大小超出允许范围', 'UPDATE_PROTOCOL')
        sha = chosen.get('sha256')
        sha = sha.casefold() if isinstance(sha, str) else ''
        if sha and not re.fullmatch(r'[a-f0-9]{64}', sha):
            fail('在线更新文件校验值无效', 'UPDATE_PROTOCOL')
        # A URL carried by the check response is not trusted as the package
        # source. The artifact's short-lived download authorization provides
        # the URL after the exact grant and artifact have been selected.
        url = ''
        normalized = {
            'version': version, 'grantId': grant, 'updateToken': update_token,
            'artifact': {
                'artifactId': artifact_id, 'filename': filename, 'kind': str(chosen.get('kind') or '')[:30],
                'size': size, 'sha256': sha, 'url': url,
            },
            'payload': None,
        }
        if size is not None and sha:
            normalized['payload'] = {
                'schema': 1, 'product': PRODUCT, 'channel': self.channel.get('channel', 'stable'),
                'version': version, 'url': url or '', 'size': size, 'sha256': sha,
                'notes': _notes_text(data, release), 'publishedAt': _first_text(
                    data, ('published_at', 'publishedAt', 'server_time', 'created_at'))[:64],
            }
        return normalized

    def _online_get(self, path, *, timeout=20):
        token = self.online.get('updateToken', '')
        if not token:
            raise BridgeError('UPDATE_LOGIN_REQUIRED', '请重新检查更新以建立下载授权')
        try:
            return service_json(self.online_url, path, bearer=token, timeout=timeout)
        except OnlineHTTPError as error:
            if error.status in (401, 403):
                self.online['updateToken'] = ''
                self.online['updateExpiresAt'] = 0
                raise BridgeError('UPDATE_AUTH_EXPIRED', '更新授权已过期，请重新检查更新') from None
            raise BridgeError('UPDATE_NETWORK', error.args[0]) from None

    def _online_post(self, path, payload, *, timeout=20):
        token = self.online.get('updateToken', '')
        if not token:
            raise BridgeError('UPDATE_LOGIN_REQUIRED', '请重新检查更新以建立下载授权')
        try:
            return service_json(
                self.online_url, path, method='POST', payload=payload,
                bearer=token, timeout=timeout,
            )
        except OnlineHTTPError as error:
            if error.status in (401, 403):
                self.online['updateToken'] = ''
                self.online['updateExpiresAt'] = 0
                raise BridgeError('UPDATE_AUTH_EXPIRED', '更新授权已过期，请重新检查更新') from None
            raise BridgeError('UPDATE_NETWORK', error.args[0]) from None

    def _report(self, stage, *, downloaded=0, error_code=''):
        grant = self.online.get('grantId', '')
        if not grant or not self.online.get('updateToken'):
            return
        try:
            self._online_post('/api/software-update/report', {
                'event_id': uuid.uuid4().hex,
                'task_id': ('download-' + str(self.latest.get('version', self.current)))[:100],
                'grant_id': grant,
                'stage': stage,
                'target_version': str(self.latest.get('version', ''))[:80],
                'actual_version': self.current,
                'application_instance_id': self.application_instance_id,
                'downloaded_bytes': max(0, min(34359738368, int(downloaded))),
                'error_code': re.sub(r'[^A-Za-z0-9_.-]', '', str(error_code))[:60],
            }, timeout=8)
        except Exception:
            # Telemetry must never make a verified update unavailable.
            pass

    def _safe_cache(self):
        if not self.cache.resolve().is_relative_to(self.app):
            fail('更新缓存目录已变化')
        self.cache.mkdir(parents=True, exist_ok=True)
        if not self.cache.resolve().is_relative_to(self.app):
            fail('更新缓存目录已变化')

    def _cache_file(self, name):
        self._safe_cache()
        path = self.cache / name
        if path.is_symlink() or not path.resolve().is_relative_to(self.cache.resolve()):
            fail('更新缓存文件路径无效')
        return path

    def _verified_manifest(self, envelope):
        if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
            fail('更新清单格式无效')
        payload = envelope['payload']
        try:
            raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(self.channel['publicKey'], validate=True))
            key.verify(base64.b64decode(envelope['signature'], validate=True), raw)
        except Exception:
            fail('更新签名校验失败，未采用此更新', 'UPDATE_SIGNATURE')
        required = {'schema', 'product', 'channel', 'version', 'url', 'size', 'sha256', 'notes', 'publishedAt'}
        if not isinstance(payload, dict) or set(payload) != required:
            fail('更新清单内容无效')
        if (type(payload['schema']) is not int or payload['schema'] != 1
                or payload['product'] != PRODUCT or payload['channel'] != self.channel.get('channel', 'stable')):
            fail('更新清单不属于当前产品或更新通道')
        version_tuple(payload['version'])
        validate_url(payload['url'])
        if not same_origin(self.url, payload['url']):
            fail('更新包地址必须与发布清单来自同一可信站点')
        if type(payload['size']) is not int or not 2 <= payload['size'] <= MAX_PACKAGE:
            fail('更新包大小无效')
        if not isinstance(payload['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', payload['sha256']):
            fail('更新包校验值无效')
        if not isinstance(payload['notes'], str) or len(payload['notes']) > 16000:
            fail('更新说明无效')
        if not isinstance(payload['publishedAt'], str) or len(payload['publishedAt']) > 64:
            fail('更新发布日期无效')
        return copy.deepcopy(payload)

    def _package_path(self, payload):
        return self._cache_file(f'{payload["version"]}-{payload["sha256"][:16]}.exe')

    def _partial_path(self, payload):
        return self._cache_file(f'{payload["version"]}-{payload["sha256"][:16]}.exe.partial')

    def _partial_bytes(self, payload):
        path = self._partial_path(payload)
        try:
            size = path.stat().st_size
        except OSError:
            return 0
        if path.is_symlink() or not path.is_file() or size > payload['size']:
            path.unlink(missing_ok=True)
            return 0
        return size

    def _verify_package(self, path, payload):
        self._safe_cache()
        if path.is_symlink() or not path.resolve().is_relative_to(self.cache.resolve()):
            fail('更新包路径已变化')
        if (not path.is_file() or path.stat().st_size != payload['size']
                or digest(path) != payload['sha256']):
            fail('更新包校验失败，请重新下载', 'UPDATE_INTEGRITY')
        with path.open('rb') as stream:
            if stream.read(2) != b'MZ':
                fail('下载的文件不是 Windows 安装程序')

    def _recover(self, expected=None):
        try:
            saved = read_json(self._cache_file('downloaded.json'))
            envelope = saved.get('envelope')
            if isinstance(envelope, dict) and envelope.get('online') is True:
                if not expected or not self.online.get('accessToken'):
                    return
                payload = self._online_envelope_payload(envelope)
            else:
                if saved.get('manifestUrl') != self.url:
                    return
                payload = self._verified_manifest(envelope)
            if version_tuple(payload['version']) <= version_tuple(self.current):
                return
            if expected and any(payload.get(key) != expected.get(key)
                                for key in ('version', 'size', 'sha256', 'channel')):
                raise ValueError('Cached package belongs to a different release')
            path = self._package_path(payload)
            if path.is_file():
                self._verify_package(path, payload)
                self.latest = copy.deepcopy(expected or payload)
                self.envelope = self.envelope if expected else envelope
                self.package = path
                self.phase = 'ready'
                return
        except (OSError, ValueError, KeyError, BridgeError):
            pass
        try:
            saved = read_json(self._cache_file('pending.json'))
            envelope = saved.get('envelope')
            if isinstance(envelope, dict) and envelope.get('online') is True:
                if not expected or not self.online.get('accessToken'):
                    return
                payload = self._online_envelope_payload(envelope)
            else:
                if saved.get('manifestUrl') != self.url:
                    return
                payload = self._verified_manifest(envelope)
            if version_tuple(payload['version']) <= version_tuple(self.current):
                return
            if expected and any(payload.get(key) != expected.get(key)
                                for key in ('version', 'size', 'sha256', 'channel')):
                return
            received = self._partial_bytes(payload)
            if received:
                self.latest = copy.deepcopy(expected or payload)
                self.envelope = self.envelope if expected else envelope
                self.phase = 'available'
                self.progress = min(99, int(received * 100 / payload['size']))
        except (OSError, ValueError, KeyError, BridgeError):
            pass

    @staticmethod
    def _online_envelope_payload(envelope):
        offer = envelope.get('offer') if isinstance(envelope, dict) else None
        payload = offer.get('payload') if isinstance(offer, dict) else None
        if not isinstance(payload, dict):
            fail('缓存在线更新记录无效', 'UPDATE_PROTOCOL')
        required = {'schema', 'product', 'channel', 'version', 'url', 'size',
                    'sha256', 'notes', 'publishedAt'}
        if set(payload) != required:
            fail('缓存在线更新记录无效', 'UPDATE_PROTOCOL')
        version_tuple(payload['version'])
        if (payload['schema'] != 1 or payload['product'] != PRODUCT
                or type(payload['size']) is not int or not 2 <= payload['size'] <= MAX_PACKAGE
                or not isinstance(payload['sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', payload['sha256'])
                or not isinstance(payload['notes'], str)
                or not isinstance(payload['publishedAt'], str)):
            fail('缓存在线更新记录无效', 'UPDATE_PROTOCOL')
        return copy.deepcopy(payload)

    def status(self):
        with self.lock:
            complete = bool(self.latest and self.latest.get('size') and self.latest.get('sha256'))
            partial = self._partial_bytes(self.latest) if complete else 0
            result = {'currentVersion': self.current, 'channel': self.channel.get('channel', 'stable'),
                      'manifestUrl': self.url, 'configured': bool(self.url or self.online_url),
                      'autoCheck': self.auto_check,
                      'onlineConfigured': bool(self.online_url),
                      'onlineSignedIn': bool(self.online.get('accessToken')),
                      'onlineUsername': self.online.get('username', ''),
                      'phase': self.phase, 'error': self.error, 'progress': self.progress,
                      'partialBytes': partial,
                      'resumable': bool(partial and complete and
                                        version_tuple(self.latest['version']) > version_tuple(self.current)),
                      'available': bool(self.latest and version_tuple(self.latest['version']) > version_tuple(self.current)),
                      'latest': copy.deepcopy(self.latest), 'lastCheck': self.last_check}
            try:
                outcome = read_json(self._cache_file('last-install.json'))
                if isinstance(outcome, dict):
                    last = {key: outcome.get(key) for key in ('status', 'version', 'message')}
                    restart = outcome.get('restart')
                    if isinstance(restart, dict):
                        last['restart'] = {
                            key: restart.get(key) for key in ('status', 'message')
                        }
                    result['lastInstall'] = last
            except (OSError, ValueError, BridgeError):
                pass
            return result

    def _idle(self):
        if self.phase in ('checking', 'downloading', 'installing'):
            fail('更新操作正在进行，请稍候', 'UPDATE_BUSY')

    def configure(self, data):
        url = data.get('manifestUrl', self.url)
        auto = data.get('autoCheck', self.auto_check)
        if url:
            validate_url(url)
        elif url != '':
            fail('更新地址格式无效')
        if type(auto) is not bool:
            fail('自动检查设置无效')
        with self.lock:
            self._idle()
            atomic_json(self._cache_file('settings.json'), {'manifestUrl': url, 'autoCheck': auto})
            if url != self.url:
                self.latest = self.envelope = self.package = None
                if url:
                    self.phase = 'idle'
                elif self.online_url:
                    self.phase = 'idle' if self.online else 'login_required'
                else:
                    self.phase = 'unconfigured'
                self.error = ''
            self.url, self.auto_check = url, auto
        return self.status()

    def check(self):
        with self.lock:
            self._idle()
            online = bool(self.online_url)
            generation = self.session_generation
            if not online and not self.url:
                self.phase = 'unconfigured'
                return self.status()
            if online and not self.online:
                self.phase, self.error = 'login_required', '请重新登录账号后检查在线更新'
                return self.status()
            self.latest = self.envelope = self.package = None
            self.online_artifact, self.online_package_url, self.online_package_path = None, '', ''
            self.phase, self.error = 'checking', ''
        try:
            if online:
                data = self._online_check_request()
                with self.lock:
                    self._require_session_generation(generation)
                    offer = self._online_release(data)
                    self.online['grantId'] = offer['grantId'] if offer else ''
                    self.online['updateToken'] = ((offer['updateToken'] or self.online.get('accessToken', ''))
                                                  if offer else '')
                    if offer and offer['artifact'] and offer['artifact']['artifactId']:
                        self.online['artifactId'] = offer['artifact']['artifactId']
                    if offer and offer['artifact'] and offer['artifact']['filename']:
                        self.online['filename'] = offer['artifact']['filename']
                payload = offer.get('payload') if offer else None
                if offer and not payload:
                    payload = {
                        'schema': 1, 'product': PRODUCT,
                        'channel': self.channel.get('channel', 'stable'),
                        'version': offer['version'], 'url': '', 'size': 0,
                        'sha256': '', 'notes': '', 'publishedAt': '',
                    }
                envelope = {'online': True, 'offer': copy.deepcopy(offer)} if offer else None
            else:
                with fetch(self.url) as response:
                    raw = response.read(131073)
                if len(raw) > 131072:
                    fail('更新清单过大')
                envelope = json.loads(raw.decode('utf-8-sig'))
                payload = self._verified_manifest(envelope)
            with self.lock:
                self._require_session_generation(generation)
                self.last_check = datetime.now(timezone.utc).isoformat()
                self.latest, self.envelope = payload, envelope
                if not payload:
                    self.phase = 'up_to_date'
                elif version_tuple(payload['version']) > version_tuple(self.current):
                    if online and not self.online_artifact and not (
                            self.online.get('updateToken') and self.online.get('grantId')):
                        fail('在线更新没有返回可校验的安装文件，请重新检查或联系发布者',
                             'UPDATE_PROTOCOL')
                    self.phase = 'available'
                    if payload['size'] and payload['sha256']:
                        self._recover(expected=payload)
                else:
                    self.phase = 'up_to_date'
                if (self.phase == 'available' and online and not self.online_artifact
                        and self.online.get('updateToken') and self.online.get('grantId')):
                    try:
                        self.online_artifact = self._load_online_artifacts()
                        self._recover(expected=self.latest)
                    except BridgeError as error:
                        self.phase, self.error = 'error', str(error)
                        self.latest = self.envelope = self.package = None
                        raise
            return self.status()
        except Exception as error:
            with self.lock:
                if generation == self.session_generation:
                    self.phase, self.error = 'error', str(error)
                    self.latest = self.envelope = self.package = None
            if isinstance(error, BridgeError):
                raise
            if isinstance(error, OnlineHTTPError):
                fail(error.args[0], 'UPDATE_NETWORK')
            fail('无法检查更新，请检查网络后重试', 'UPDATE_NETWORK')

    def download(self, progress, control):
        with self.lock:
            self._idle()
            generation = self.session_generation
            if not self.latest or version_tuple(self.latest['version']) <= version_tuple(self.current):
                fail('请先检查并选择可用的新版本')
            payload, envelope = copy.deepcopy(self.latest), copy.deepcopy(self.envelope)
            online = bool(self.online_url)
            artifact = None
            authorization = None
            if online:
                artifact = self.online_artifact or self._load_online_artifacts()
                payload['size'] = artifact['size']
                payload['sha256'] = artifact['sha256']
                self.latest = copy.deepcopy(payload)
                if (not self.online_package_url
                        or self.online.get('downloadExpiresAt', 0) <= time.monotonic() + 20):
                    authorization = self._authorize_download(artifact)
                    self.online_package_url = authorization['url']
                    self.online_package_headers = authorization['headers']
                    self.online_package_artifact = artifact['artifactId']
                    self.online_package_sha = artifact['sha256']
                    self.online['downloadExpiresAt'] = authorization['expiresAt']
                elif self.online_package_artifact != artifact['artifactId']:
                    fail('在线更新下载授权与安装包不一致', 'UPDATE_AUTH')
                payload['url'] = self.online_package_url
                envelope = {'online': True, 'offer': {
                    # Expiring signed URLs are credentials, not recovery data.
                    # A new session obtains a fresh URL for the same hash.
                    'payload': {**copy.deepcopy(payload), 'url': ''},
                    'artifact': copy.deepcopy(artifact),
                }}
            atomic_json(self._cache_file('pending.json'), {'manifestUrl': self.url, 'envelope': envelope})
            temporary = self._partial_path(payload)
            received = self._partial_bytes(payload)
            self.phase, self.error = 'downloading', ''
            self.download_control = control
            self.progress = min(99, int(received * 100 / payload['size'])) if received else 0
        append = received > 0
        hasher = hashlib.sha256()
        incomplete = True
        try:
            if append:
                with temporary.open('rb') as existing:
                    for block in iter(lambda: existing.read(1024 * 1024), b''):
                        check_control(control)
                        hasher.update(block)
            check_control(control)
            if online:
                self._report('started')
            path = self._package_path(payload)
            request_headers = self.online_package_headers if online else None
            response = fetch(payload['url'], offset=received if append else 0,
                             headers=request_headers)
            try:
                response_status = getattr(response, 'status', None)
                if append and response_status == 206:
                    content_range = response.headers.get('Content-Range', '')
                    match = re.fullmatch(r'bytes\s+' + str(received) + r'-\d+/(\d+)', content_range)
                    if not match or int(match.group(1)) != payload['size']:
                        fail('更新下载的续传范围无效', 'UPDATE_INTEGRITY')
                elif append:
                    # A server may ignore Range and send the complete package.
                    received, hasher, append = 0, hashlib.sha256(), False
                    incomplete = False
                declared = response.headers.get('Content-Length')
                if declared is not None:
                    try:
                        declared_length = int(declared)
                    except (TypeError, ValueError):
                        fail('更新下载的响应大小无效', 'UPDATE_INTEGRITY')
                    if declared_length != payload['size'] - received:
                        fail('更新下载大小与发布清单不一致', 'UPDATE_INTEGRITY')
                with temporary.open('ab' if append else 'wb') as stream:
                    while True:
                        check_control(control)
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > payload['size']:
                            fail('更新下载超过发布大小', 'UPDATE_INTEGRITY')
                        hasher.update(block)
                        stream.write(block)
                        self.progress = min(99, int(received * 100 / payload['size']))
                        progress(self.progress, f'正在下载应用更新 {received / 1024 ** 2:.1f} / {payload["size"] / 1024 ** 2:.1f} MB')
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                response.close()
            if received != payload['size'] or hasher.hexdigest() != payload['sha256']:
                temporary.unlink(missing_ok=True)
                fail('更新包不完整或校验失败，请重试', 'UPDATE_INTEGRITY')
            incomplete = False
            self._verify_package(temporary, payload)
            check_control(control)
            with self.lock:
                self._require_session_generation(generation)
                check_control(control)
                os.replace(temporary, path)
                atomic_json(self._cache_file('downloaded.json'), {'manifestUrl': self.url, 'envelope': envelope})
                self.package, self.phase, self.progress = path, 'ready', 100
            if online:
                self._report('downloaded', downloaded=payload['size'])
            progress(100, '更新已下载并通过校验，可以安装')
            return {'path': str(path), 'version': payload['version'], 'sha256': payload['sha256']}
        except BaseException as error:
            if not incomplete:
                temporary.unlink(missing_ok=True)
            with self.lock:
                if generation == self.session_generation:
                    self.phase, self.error = 'available', str(error)
                    self.progress = min(99, int(self._partial_bytes(payload) * 100 / payload['size']))
            if online and generation == self.session_generation:
                cancelled = getattr(error, 'args', ('',)) and bool(control['cancelled'].is_set())
                self._report('cancelled' if cancelled else 'failed',
                             downloaded=self._partial_bytes(payload),
                             error_code='CANCELLED' if cancelled else getattr(error, 'code', 'UPDATE_ERROR'))
            raise
        finally:
            with self.lock:
                if self.download_control is control:
                    self.download_control = None

    def prepare_install(self, tasks):
        with self.lock:
            self._idle()
            if any(row.get('status') in ('queued', 'running', 'paused', 'pending', 'cancelling') for row in tasks):
                fail('请等待剪辑和下载任务完成，再安装更新', 'UPDATE_TASKS_ACTIVE')
            if self.phase != 'ready' or not self.package:
                fail('请先下载并校验更新')
            if isinstance(self.envelope, dict) and self.envelope.get('online') is True:
                offer = self.envelope.get('offer')
                artifact = offer.get('artifact') if isinstance(offer, dict) else None
                if (not isinstance(artifact, dict)
                        or str(artifact.get('kind') or '').casefold() != 'setup'):
                    fail('在线更新只提供了完整目录包，请发布可静默安装的 Setup 安装程序后再更新',
                         'UPDATE_PROTOCOL')
                payload = self._online_envelope_payload(self.envelope)
            else:
                payload = self._verified_manifest(self.envelope)
            if version_tuple(payload['version']) <= version_tuple(self.current):
                fail('不能安装相同或更旧的版本')
            self._verify_package(self.package, payload)
            exe = self.app / 'AI全自动剪辑_云湃科技.exe'
            if not exe.is_file():
                fail('未找到当前应用的启动程序')
            job = {'installDir': str(self.app), 'package': str(self.package), 'sha256': payload['sha256'],
                   'size': payload['size'], 'version': payload['version'], 'backendPid': os.getpid(),
                   'exes': [str(exe), str(self.app / 'Aive.UI2.exe'), str(self.app / 'Backend/aive-business.exe')],
                   'resultPath': str(self._cache_file('last-install.json'))}
            job_path = self._cache_file('install-' + uuid.uuid4().hex + '.json')
            atomic_json(job_path, job)
            return job_path

    def install(self, tasks):
        job = self.prepare_install(tasks)
        script = self._cache_file(job.stem + '.ps1')
        shutil.copyfile(self.app / 'Backend/install_update.ps1', script)
        powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        try:
            process = subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                        '-File', str(script), '-JobFile', str(job)],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                                       | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                                       cwd=str(self.cache))
            signal = job.with_suffix('.started')
            deadline = time.monotonic() + 10
            while not signal.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    fail('安装助手未就绪，应用仍保持打开，请重试', 'UPDATE_INSTALL_START')
                time.sleep(.1)
            self.phase = 'installing'
            self._report('installing', downloaded=(self.latest or {}).get('size', 0))
            self._report('restart_pending', downloaded=(self.latest or {}).get('size', 0))
            return {'closeRequired': True, 'version': self.latest['version']}
        except OSError:
            self._report('failed', error_code='UPDATE_INSTALL_START')
            fail('无法启动安装助手，请重试', 'UPDATE_INSTALL_START')


def install_lifecycle_hook(api_class):
    """Invalidate account-bound updates even if the UI logout event is lost."""
    previous = getattr(api_class, 'invoke', None)
    if previous is None or getattr(previous, '_aive_update_lifecycle', False):
        return

    def invoke(api, action, data):
        result = previous(api, action, data)
        if action in ('license.logout', 'app.shutdown'):
            video = getattr(api, 'groups', {}).get('video')
            service = getattr(video, '_update_service', None)
            if service is not None:
                service.clear_session()
        return result

    invoke._aive_update_lifecycle = True
    api_class.invoke = invoke


class AppUpdatesMixin:
    def _updates(self):
        if not hasattr(self, '_update_service'):
            self._update_service = UpdateService()
        return self._update_service

    def video_updateStatus(self, data):
        return self._updates().status()

    def video_establishUpdateSession(self, data):
        if not isinstance(data, dict):
            fail('账号信息无效，无法建立在线更新会话', 'UPDATE_LOGIN')
        username = data.get('username', '')
        password = data.get('password', '')
        return self._updates().establish_session(username, password)

    def video_clearUpdateSession(self, data):
        return self._updates().clear_session()

    def video_checkUpdate(self, data):
        return self._updates().check()

    def video_configureUpdates(self, data):
        return self._updates().configure(data)

    def video_downloadUpdate(self, data):
        return self.api.tasks.start('下载应用更新', self._updates().download,
                                    category='update', location={'route': '/settings'})

    def video_installUpdate(self, data):
        return self._updates().install(self.api.tasks.list())
