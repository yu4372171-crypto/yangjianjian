"""Pinned free media downloads feeding the existing, validated effect renderer."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from app.ui2.common import BridgeError
from app.workers.control import check_control

DATA = Path(__file__).resolve().with_name('free_assets_data')
_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,95}$')
_SHA = re.compile(r'^[a-f0-9]{64}$')
_LOCKS = {}
_MAX_SIZE = 16*1024**2


def _load(name):
    key = '_aive_'+name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name+'.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)
            raise
    return sys.modules[key]


def _error(message):
    raise BridgeError('FREE_ASSET_INVALID', message)


def _url(value):
    if not isinstance(value, str):
        _error('素材下载地址无效')
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname not in
            {'raw.githubusercontent.com', 'cdn.jsdelivr.net'} or
            parsed.username or parsed.password or parsed.port not in (None, 443) or
            parsed.query or parsed.fragment):
        _error('素材下载仅支持目录中的 HTTPS 固定版本来源')
    prefix = (r'^/[^/]+/[^/]+/[a-f0-9]{40}/' if parsed.hostname == 'raw.githubusercontent.com'
              else r'^/gh/[^/]+/[^/@]+@[a-f0-9]{40}/')
    if not re.match(prefix, parsed.path):
        _error('素材地址未固定到审核版本')
    return value


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _open_url(request, timeout=12):
    return urllib.request.build_opener(_Redirects()).open(request, timeout=timeout)


def load_catalog():
    try:
        data = json.loads((DATA/'catalog.json').read_text('utf8'))
    except (OSError, ValueError):
        _error('免费素材目录缺失或损坏，请通过应用更新修复')
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('items'), list):
        _error('免费素材目录版本不受支持')
    seen = set()
    for row in data['items']:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or
                not _ID.fullmatch(row['id']) or row['id'] in seen or
                row.get('kind') not in {'image', 'lut', 'transition'} or
                row.get('category') not in {'sticker', 'effect', 'template', 'transition'} or
                type(row.get('size')) is not int or not 0 < row['size'] <= _MAX_SIZE or
                not isinstance(row.get('sha256'), str) or not _SHA.fullmatch(row['sha256'])):
            _error('免费素材目录条目无效')
        if (not isinstance(row.get('urls'), list) or not 1 <= len(row['urls']) <= 2 or
                Path(row.get('filename', '')).name != row.get('filename') or
                Path(row.get('filename', '')).suffix not in {'.png', '.cube', '.json'} or
                row.get('license') not in {'MIT', 'CC0-1.0'}):
            _error('免费素材来源、格式或授权不受支持')
        for url in row['urls']:
            _url(url)
        seen.add(row['id'])
    return data


def _item(identifier):
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        _error('请选择有效的免费素材编号')
    item = next((row for row in load_catalog()['items'] if row['id'] == identifier), None)
    if item is None:
        _error('素材不在当前免费目录中，请刷新素材库或更新应用')
    return item


def _folder(item):
    assets = _load('editor_assets')
    folder = assets._safe(assets._root()/'catalog'/item['id'])
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _cache(item):
    return _load('editor_assets')._safe(_folder(item)/('source'+Path(item['filename']).suffix))


def _verified(path, item):
    return (path.is_file() and path.stat().st_size == item['size'] and
            _load('editor_assets')._digest(path) == item['sha256'])


def _recipe(item, path):
    try:
        data = json.loads(path.read_text('utf8'))
        recipe = item['recipe']
        alias = data['aliases'][recipe['alias']]
        if alias['xfade'] != recipe['type']:
            raise ValueError()
        return _load('transitions').normalize_transition(
            {'type': recipe['type'], 'duration': recipe['duration']})
    except (OSError, ValueError, KeyError, TypeError):
        _error('下载的转场目录与审核模板不一致，请更新素材库')


def _installed(item):
    assets = _load('editor_assets')
    try:
        state_file = assets._safe(_folder(item)/'state.json')
        if state_file.stat().st_size > 16384:
            return None
        state = json.loads(state_file.read_text('utf8'))
        if state.get('id') != item['id'] or state.get('sha256') != item['sha256']:
            return None
        if item['kind'] == 'transition':
            source = _cache(item)
            if _verified(source, item):
                return {'transition': _recipe(item, source)}
        else:
            effect = assets.resolve_effect(state.get('effectId'))
            if (effect['sha256'] == item['sha256'] and
                    effect.get('provenance', {}).get('catalogId') == item['id']):
                return {'effect': effect}
    except (OSError, ValueError, TypeError, AttributeError, BridgeError):
        pass
    return None


def _public(item):
    result = {key: copy.deepcopy(value) for key, value in item.items() if key not in {'urls', 'licenseFile'}}
    installed = _installed(item)
    result['installed'] = installed is not None
    result['effectId'] = installed.get('effect', {}).get('id', '') if installed else ''
    return result


def get_catalog():
    catalog = load_catalog()
    return {**{key: value for key, value in catalog.items() if key != 'items'},
            'items': [_public(row) for row in catalog['items']]}


def _license(item):
    name = item.get('licenseFile')
    if not isinstance(name, str) or Path(name).name != name:
        _error('素材许可证路径无效')
    try:
        return (DATA/'licenses'/name).read_text('utf8')
    except OSError:
        _error('素材许可证缺失，请更新应用后再下载')


def _download(item, progress, control):
    target = _cache(item)
    if _verified(target, item):
        progress(88, '正在从已验证的本地缓存恢复素材')
        return target
    assets = _load('editor_assets')
    stage = assets._safe(target.with_name('download-'+uuid.uuid4().hex+'.pending'))
    for index, url in enumerate(item['urls']):
        check_control(control)
        progress(3, '正在连接'+(' GitHub' if index == 0 else '备用下载源'))
        try:
            request = urllib.request.Request(_url(url), headers={
                'User-Agent': 'Yangyu-AutoEdit-FreeAssets/1', 'Accept-Encoding': 'identity'})
            with _open_url(request, timeout=12) as response:
                _url(response.geturl())
                length = response.headers.get('Content-Length')
                if length is not None and int(length) != item['size']:
                    _error('素材下载长度与审核目录不符')
                digest, size = hashlib.sha256(), 0
                with stage.open('wb') as output:
                    while True:
                        check_control(control)
                        block = response.read(min(65536, item['size']-size+1))
                        if not block:
                            break
                        size += len(block)
                        if size > item['size']:
                            _error('素材下载超过审核大小')
                        output.write(block)
                        digest.update(block)
                        progress(5+int(80*size/item['size']), f"下载 {item['name']}：{size//1024}/{max(1, item['size']//1024)} KB")
            if size != item['size'] or digest.hexdigest() != item['sha256']:
                _error('素材下载校验失败，请重新下载')
            check_control(control)
            assets._safe(target)
            os.replace(assets._safe(stage), target)
            return target
        except (OSError, ValueError, BridgeError):
            if index == len(item['urls'])-1:
                raise BridgeError('FREE_ASSET_DOWNLOAD',
                                  '素材下载失败，网络不可用或文件校验未通过。请检查网络后重试；不会影响已下载素材。') from None
        finally:
            if stage.exists():
                assets._safe(stage).unlink()
    _error('素材没有可用下载源')


def install(identifier, tool, progress, control):
    item = _item(identifier)
    lock = _LOCKS.setdefault(item['id'], threading.Lock())
    while not lock.acquire(timeout=.2):
        check_control(control)
    effect = None
    try:
        check_control(control)
        current = _installed(item)
        if current:
            progress(100, '素材已在本机，可直接应用')
            return {'item': _public(item), **current}
        license_text = _license(item)
        source = _download(item, progress, control)
        check_control(control)
        assets = _load('editor_assets')
        result, state = {}, {'id': item['id'], 'sha256': item['sha256']}
        if item['kind'] == 'transition':
            result['transition'] = _recipe(item, source)
        else:
            progress(90, '正在验证素材格式并加入我的素材')
            effect = assets.import_effect(source, tool)
            metadata = {key: value for key, value in effect.items() if key != 'path'}
            metadata.update(name=item['name'], sourceName=item['filename'], provenance={
                'catalogId': item['id'], 'author': item['author'], 'license': item['license'],
                'source': item['source'], 'sha256': item['sha256'],
            })
            folder = assets._folder(effect['id'])
            assets._safe(folder/'LICENSE.txt').write_text(license_text, 'utf8')
            assets._write_meta(folder, metadata)
            state['effectId'] = effect['id']
            result['effect'] = assets.resolve_effect(effect['id'])
        check_control(control)
        folder = _folder(item)
        assets._safe(folder/'LICENSE.txt').write_text(license_text, 'utf8')
        assets._write_meta(folder, state)
        # Use the same atomic writer, then distinguish the receipt from effect metadata.
        os.replace(assets._safe(folder/'metadata.json'), assets._safe(folder/'state.json'))
        progress(100, '素材下载完成，已加入我的素材')
        return {'item': _public(item), **result}
    except BaseException:
        if effect is not None:
            try:
                metadata = assets.resolve_effect(effect['id'])
                metadata.pop('path', None)
                metadata['active'] = False
                assets._write_meta(assets._folder(effect['id']), metadata)
            except (OSError, BridgeError):
                pass
        raise
    finally:
        lock.release()


def remove(identifier):
    item = _item(identifier)
    current = _installed(item)
    assets = _load('editor_assets')
    if current and current.get('effect'):
        metadata = current['effect'].copy()
        metadata.pop('path', None)
        metadata['active'] = False
        assets._write_meta(assets._folder(metadata['id']), metadata)
    state = assets._safe(_folder(item)/'state.json')
    if state.exists():
        state.unlink()
    return {'removed': True, 'id': identifier}


class FreeAssetsMixin:
    def video_getFreeAssetCatalog(self, data):
        return get_catalog()

    def video_freeAssetLicense(self, data):
        item = _item(data.get('id'))
        return {'id': item['id'], 'license': item['license'], 'text': _license(item)}

    def video_downloadFreeAsset(self, data):
        if not isinstance(data, dict) or set(data) != {'id'}:
            _error('素材下载只接受目录编号')
        item = _item(data.get('id'))
        tool = self.api.ctx.ffmpeg_tool()
        return self.api.tasks.start(
            '下载免费素材：'+item['name'],
            lambda progress, control: install(item['id'], tool, progress, control),
            category='other', location={'route': '/editor/smart'})

    def video_getFreeAsset(self, data):
        item = _item(data.get('id'))
        current = _installed(item)
        if not current:
            _error('请先下载此素材')
        return {'item': _public(item), **current}

    def video_removeFreeAsset(self, data):
        return remove(data.get('id'))
