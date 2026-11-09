"""Explicit local editing requirements with reviewable plans and cancellable FFmpeg jobs."""
from __future__ import annotations

import copy
import importlib.util
from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

from app.ui2.common import BridgeError
from app.workers.control import check_control


_NUM = r'(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+(?:点[零一二三四五六七八九]+)?)'
_UNIT = r'(?:分钟|秒钟|秒|分(?!辨)|s\b)'
_RATIOS = {'竖屏': '9:16', '横屏': '16:9', '方形': '1:1', '正方形': '1:1'}
_VALID_RATIOS = {'自动', '9:16', '16:9', '1:1', '4:5', '3:4', '4:3', '21:9'}
_VALID_RESOLUTIONS = {'原画', '720p', '1080p', '2K', '4K'}
_SEMANTIC_CUT = (r'(?:剪辑掉|剪掉|去掉|裁去|裁掉|删除|删掉|移除|剔除)\s*'
                 r'(?:画面|视频)?\s*(?:穿模|瑕疵|卡顿|黑屏|不自然|不符合物理逻辑)'
                 r'(?:\s*的)?\s*(?:部分|片段|镜头|画面)?'
                 r'|(?:裁去|裁掉|去掉|删除|删掉|移除|剔除)\s*(?:不符合物理逻辑)'
                 r'(?:\s*的)?\s*(?:画面|视频|部分|片段|镜头)?')


def _load_companion(name):
    identifier='_aive_'+name
    module=sys.modules.get(identifier)
    if module is None:
        path=Path(__file__).with_name(name+'.py')
        spec=importlib.util.spec_from_file_location(identifier,path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[identifier]=module
        try:spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(identifier,None);raise
    return module


def _load_speech():return _load_companion('local_speech')


def _error(message, code='SMART_EDIT_INVALID'):
    raise BridgeError(code, message)


def _verify_smart_delivery(ledger, result):
    try:
        return _load_companion('requirement_ledger').verify(ledger, result)
    except ValueError as error:
        message = str(error)
        if message.startswith('SMART_REQUIREMENT_NOT_DELIVERED|'):
            message = message.split('|', 1)[1]
        raise BridgeError('SMART_REQUIREMENT_NOT_DELIVERED', message) from error


def _number(value, field, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        _error(f'{field}超出可用范围（{minimum}–{maximum}）')
    return float(value)


def _chinese_number(value):
    try:
        return float(value)
    except ValueError:
        digits = dict(zip('零〇一二两三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
        integer, _, decimal = value.partition('点')
        total, current = 0, 0
        for char in integer:
            if char in '十百':
                total += (current or 1) * (10 if char == '十' else 100)
                current = 0
            else:
                current = digits[char]
        return total + current + (float('0.' + ''.join(str(digits[c]) for c in decimal)) if decimal else 0)


def _seconds(number, unit):
    return _chinese_number(number) * (60 if unit in ('分', '分钟') else 1)


def _parse(text, defaults, removal_marked=False, reviewed=False):
    settings = dict(defaults)
    remaining = text
    recognized = []
    operations, spans = [], []

    def take(pattern, apply, name, flags=re.I):
        matches = list(re.finditer(pattern, text, flags))
        for match in matches:
            operations.append((match.start(), len(operations), apply, match))
            spans.append((match.start(), match.end()))
        if matches:
            recognized.append(name)

    take(r'(?:去掉|删除|删掉|跳过|剪掉|裁掉)\s*(?:开头|前)\s*(' + _NUM + r')\s*(' + _UNIT + ')',
         lambda m: settings.update(start=_seconds(m[1], m[2])), '跳过开头')
    take(r'从\s*(?:第)?\s*(' + _NUM + r')\s*(' + _UNIT + r')\s*(?:开始|起)',
         lambda m: settings.update(start=_seconds(m[1], m[2])), '开始位置')
    take(r'(?:剪成|裁剪成|保留(?:前)?|(?<!最短)(?:总)?时长(?:为)?|剪辑成|截取(?:前)?)\s*(' + _NUM + r')\s*(' + _UNIT + ')',
         lambda m: settings.update(duration=_seconds(m[1], m[2])), '成片时长')
    take(r'(?:最短时长(?:为)?|(?:(?:成片|视频|总)?时长)?\s*(?:至少|最少|不低于|不少于|不短于|最短(?:为)?))\s*(' + _NUM + r')\s*(' + _UNIT + ')',
         lambda m: settings.update(minDuration=_seconds(m[1], m[2])), '最短成片时长')
    take(r'(?:视频)?(?:播放|剪辑)?速度\s*(?:禁止|不得|不能|不可)\s*低于\s*(' + _NUM + r')',
         lambda m: settings.update(minSpeed=_chinese_number(m[1])), '最低播放速度')
    take(r'(?:视频|成片)?(?:播放|剪辑)?速度\s*(?:最低|下限)\s*(?:为|是)?\s*(' + _NUM + r')\s*倍(?:速)?',
         lambda m: settings.update(minSpeed=_chinese_number(m[1])), '最低播放速度')
    take(r'倍速\s*(?:最低|下限)\s*(?:为|是)?\s*(' + _NUM + r')',
         lambda m: settings.update(minSpeed=_chinese_number(m[1])), '最低播放速度')
    take(r'(' + _NUM + r')\s*倍速', lambda m: settings.update(speed=_chinese_number(m[1])), '播放速度')
    take(r'(?:不要|去掉|删除|关闭|移除)\s*(?:原声|原音|声音)|静音|无(?:原声|声音)',
         lambda m: settings.update(keepAudio=False), '关闭原声')
    take(r'保留\s*(?:原声|原音|声音)', lambda m: settings.update(keepAudio=True), '保留原声')
    music = r'(?:BGM|背景音乐|配乐)'
    adjectives = r'(?:(?:顺畅|舒缓|柔和|轻柔|平缓|流畅|动感|轻快|好听|合适|无缝|自然|的)\s*)*'
    take(r'(?:加上|加入|添加|配上|开启|使用|保留)\s*' + adjectives + music,
         lambda m: settings.update(bgm=True), '加入背景音乐')
    take(r'(?:不要|去掉|删除|关闭|移除|无)\s*' + adjectives + music,
         lambda m: settings.update(bgm=False), '关闭背景音乐')
    if removal_marked or reviewed:
        take(_SEMANTIC_CUT, lambda m: None, '删除已标记片段' if removal_marked else '采用视觉分析结果')
    take(r'(?:正方形|方形|竖屏|横屏)', lambda m: settings.update(ratio=_RATIOS[m[0]]), '画面比例')
    take(r'(9\s*[:：]\s*16|16\s*[:：]\s*9|1\s*[:：]\s*1|4\s*[:：]\s*5|3\s*[:：]\s*4|4\s*[:：]\s*3|21\s*[:：]\s*9)',
         lambda m: settings.update(ratio=re.sub(r'\s', '', m[1]).replace('：', ':')), '画面比例')
    take(r'(?:分辨率(?:为)?\s*)?(720p|1080p|1440p|2160p|2k|4k|原画|原始分辨率)',
         lambda m: settings.update(resolution={'1440p': '2K', '2160p': '4K', '2k': '2K', '4k': '4K', '原始分辨率': '原画'}.get(m[1].lower(), m[1].lower())), '分辨率')
    take(r'(?:顺序(?:拼接|合成|剪辑)|按(?:照)?(?:添加|导入|列表)?顺序(?:拼接|合成|剪辑)?|拼接|合并|合成)',
         lambda m: None, '顺序拼接')
    # Read repeated directives in the user's order, including across different
    # synonyms (e.g. "保留原声，然后静音"). The last explicit instruction wins.
    for _, _, apply, match in sorted(operations, key=lambda item: item[:2]):
        apply(match)
    for begin, end in spans:
        remaining = remaining[:begin] + ' ' * (end - begin) + remaining[end:]
    # Polite framing is not an additional editing operation.
    remaining = re.sub(r'(?:请|帮我|给我|把|将|这些|这几段|这些片段|所有|多个|多段|视频|素材|成片|比例|输出|导出|并且|以及|然后|并|和|为|的|成|到|做一个|做成一个|一个|一段|保持|使用|采用)', ' ', remaining)
    remaining = re.sub(r'[\s，,。；;、!！?？:：/（）()]+', '', remaining).strip()
    return settings, list(dict.fromkeys(recognized)), remaining


def _remove_ranges(value, infos):
    if not isinstance(value, list) or len(value) > 200:
        _error('请标记有效的删除区间（最多 200 个）')
    ordered = []
    for item in value:
        if not isinstance(item, dict):
            _error('删除区间格式无效，请重新标记')
        index = item.get('index')
        if type(index) is not int or not 0 <= index < len(infos):
            _error('删除区间对应的视频已变化，请重新标记')
        start = _number(item.get('start'), '删除开始时间', 0, infos[index]['duration'])
        end = _number(item.get('end'), '删除结束时间', 0, infos[index]['duration'])
        if end - start < .001:
            _error('删除结束时间必须晚于开始时间')
        ordered.append(dict(index=index, start=start, end=end))
    merged = []
    for item in sorted(ordered, key=lambda r: (r['index'], r['start'])):
        if merged and item['index'] == merged[-1]['index'] and item['start'] <= merged[-1]['end'] + .000001:
            merged[-1]['end'] = max(item['end'], merged[-1]['end'])
        else:
            merged.append(item.copy())
    return merged


def _kept_segments(infos, ranges):
    segments = []
    for index, info in enumerate(infos):
        position = 0.0
        for removed in (item for item in ranges if item['index'] == index):
            if removed['start'] - position > .001:
                segments.append((index, position, removed['start'] - position))
            position = removed['end']
        if info['duration'] - position > .001:
            segments.append((index, position, info['duration'] - position))
    return segments


def _transition_pieces(kept_segments, start, speed, transition, fps, target=None):
    """Map kept source footage to a finished clock before target truncation."""
    pieces, position = [], 0.
    for index, offset, duration in kept_segments:
        left = max(0., start-position)
        if duration-left > .001:
            pieces.append((index, offset+left, duration-left))
        position += duration
    lengths = [duration/speed for _, _, duration in pieces]
    transitions = _load_companion('transitions')
    layout = transitions.normalize_joins(lengths, [transition]*(len(lengths)-1), fps=fps, error=_error)
    if target is not None and target < layout['duration']-1e-8:
        count = sum(offset < target-1e-8 for offset in layout['starts'])
        pieces, lengths = pieces[:count], lengths[:count]
        # Preserve enough handles when the requested ending is inside a join;
        # the final export truncates the completed transition at the target.
        incoming = layout['joins'][count-2]['duration'] if count > 1 else 0.
        length = min(lengths[-1], max(target-layout['starts'][count-1], incoming*2))
        index, offset, _ = pieces[-1]
        pieces[-1] = (index, offset, length*speed)
        lengths[-1] = length
        layout = transitions.normalize_joins(lengths, [transition]*(len(lengths)-1), fps=fps, error=_error)
    return pieces, layout


def _smooth_joins(lengths, transition, fps, target=None):
    """Keep every requested join after any final split; never fall back to a hard cut."""
    own_w = _load_companion('transitions').normalize_joins(
        lengths, [transition] * (len(lengths) - 1), fps=fps, error=_error)
    starts, duration = [], 0.
    for index, length in enumerate(lengths):
        if index:
            duration -= own_w['joins'][index - 1]['duration']
        starts.append(duration)
        duration += length
    layout = {**own_w, 'starts': starts, 'duration': round(duration, 8)}
    layout['acceptable'] = duration + 1e-7 >= float(target or 0.)
    return layout


def _audio_source(tool, path, helpers):
    raw = helpers['_capture']([tool.ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-show_streams', '-show_format', '-of', 'json', path])
    try:
        info = json.loads(raw)
        stream = next(s for s in info.get('streams', []) if s.get('codec_type') == 'audio')
        duration = float(stream.get('duration') or info.get('format', {}).get('duration') or 0)
        if not math.isfinite(duration) or duration < .05:
            raise ValueError('invalid duration')
        return int(stream['index'])
    except (ValueError, KeyError, TypeError, StopIteration):
        _error('所选背景音乐没有有效音轨，请选择 MP3、WAV、M4A 等音频文件', 'SMART_EDIT_MUSIC_INVALID')


def _dimensions(info, ratio, resolution):
    aspect = info['width'] / info['height'] if ratio == '自动' else float(ratio.split(':')[0]) / float(ratio.split(':')[1])
    if resolution == '原画':
        longside = min(3840, max(info['width'], info['height']))
        width, height = (longside, longside / aspect) if aspect >= 1 else (longside * aspect, longside)
    else:
        shortside = {'720p': 720, '1080p': 1080, '2K': 1440, '4K': 2160}[resolution]
        width, height = (shortside * aspect, shortside) if aspect >= 1 else (shortside, shortside / aspect)
        scale = min(1, 3840 / max(width, height))
        width, height = width * scale, height * scale
    return max(2, int(round(width / 2)) * 2), max(2, int(round(height / 2)) * 2)


def _fingerprint(path):
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ino
    except OSError:
        _error('素材已被删除或无法读取，请重新生成剪辑计划', 'SMART_EDIT_CHANGED')


def _atempo(speed):
    parts = []
    while speed < .5:
        parts.append('atempo=0.5')
        speed *= 2
    while speed > 2:
        parts.append('atempo=2')
        speed /= 2
    parts.append(f'atempo={speed:.8f}')
    return ','.join(parts)


def _inside_project(path, project):
    resolved = path.resolve()
    if project.resolve() != project or resolved == project or not resolved.is_relative_to(project):
        _error('剪辑输出目录指向项目之外，请移除重定向目录后重试', 'SMART_EDIT_OUTPUT_PATH')
    return resolved


def _owned_directory(path, project):
    resolved = _inside_project(path, project)
    stat = resolved.stat()
    return resolved, stat.st_dev, stat.st_ino


def _cleanup_owned(path, ownership, project):
    # Do not traverse a replaced parent junction, symlink, or directory.
    try:
        if _owned_directory(path, project) != ownership:
            return False
    except (OSError, BridgeError):
        return False
    shutil.rmtree(path)
    return True


@contextmanager
def _scratch_directory(folder, project):
    path = Path(tempfile.mkdtemp(prefix='.aive-smart-', dir=folder))
    ownership = _owned_directory(path, project)
    try:
        yield path
    finally:
        _cleanup_owned(path, ownership, project)


class SmartEditingMixin:
    """Mixed into VideoActions; helper namespace comes from that existing module."""
    def _smart_project(self):
        ctx = self.api.ctx
        if getattr(ctx, 'project_id', None) is None:
            _error('请先打开项目，再拖入视频填写剪辑要求', 'PROJECT_REQUIRED')
        directory = Path(ctx.project_dir).resolve()
        if not directory.is_dir():
            _error('项目目录无法读取，请重新打开项目', 'PROJECT_REQUIRED')
        database = str(ctx.db.engine.url.database)
        return database, directory

    def video_smartPlan(self, data):
        database, directory = self._smart_project()
        text = data.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            _error('请填写剪辑要求（最多 4000 字）')
        paths = data.get('paths')
        if not isinstance(paths, list) or not 1 <= len(paths) <= 50:
            _error('请拖入或选择 1–50 段视频')
        helpers = self._smart_helpers
        sources = [helpers['_local_path'](path, existing=True) for path in paths]
        tool = self.api.ctx.ffmpeg_tool()
        snapshots = [_fingerprint(path) for path in sources]
        infos = [helpers['_probe'](tool, path) for path in sources]
        if snapshots != [_fingerprint(path) for path in sources]:
            _error('素材正在变化，请等待保存完成后重新生成计划', 'SMART_EDIT_CHANGED')
        analysis_id, review = data.get('analysisId'), None
        if analysis_id is not None and analysis_id != '':
            review_method = getattr(self, '_vision_review', None)
            if not callable(review_method):
                _error('视觉分析接口不可用，请重新启动软件后分析或使用手动标记')
            review = review_method(analysis_id, sources, snapshots, database)
        defaults = dict(start=_number(data.get('start', 0), '开始位置', 0, 86400),
            minDuration=_number(data.get('minDuration', 0), '最短时长', 0, 86400),
            minSpeed=_number(data.get('minSpeed', .25), '最低播放速度', .25, 4),
            duration=_number(data.get('duration', 0), '目标时长', 0, 86400),
            speed=_number(data.get('speed', 1), '倍速', .25, 4),
            ratio=data.get('ratio', '自动'), resolution=data.get('resolution', '原画'), keepAudio=data.get('keepAudio', True),
            bgm=data.get('bgm', False), bgmVolume=_number(data.get('bgmVolume', .18), '配乐音量', 0, 1))
        removals = _remove_ranges(data.get('removeRanges', []), infos)
        kept_segments = _kept_segments(infos, removals)
        spatial_crops=copy.deepcopy(data.get('spatialCrops',[]))
        if not isinstance(data.get('subtitles',False),bool):_error('字幕选项无效')
        language=data.get('speechLanguage','auto')
        if not isinstance(language,str) or language not in {row['code'] for row in _load_companion('local_speech').get_languages()}:
            _error('请选择支持的口播语言，或使用自动检测')
        try:subtitle_style=_load_companion('smart_subtitles')._style(data.get('subtitleStyle'))
        except ValueError as error:_error(str(error))
        bgm_track=data.get('bgmTrack','')
        if not isinstance(bgm_track,str) or (bgm_track and bgm_track not in {row['id'] for row in _load_companion('editor_assets').get_bgm_tracks()}):
            _error('请选择可用的背景音乐风格')
        settings, recognized, unhandled = _parse(text.strip(), defaults, bool(removals), review is not None)
        assembly=_load_companion('smart_assembly')
        try:assembly_options=assembly.options(data)
        except ValueError as error:_error(str(error))
        transition = _load_companion('transitions').normalize_transition(data.get('transition'), error=_error)
        fps = min(60.0, max(30.0, infos[0]['fps']))
        minimum_policy = data.get('minDurationPolicy', 'slowdown')
        if not isinstance(minimum_policy, str) or minimum_policy not in ('slowdown', 'available', 'strict'):
            _error('请选择有效的素材不足处理方式')
        use_all = settings['duration'] == 0
        if settings['duration']==0:
            settings['duration']=max(.05,(sum(piece[2] for piece in kept_segments)-settings['start'])/settings['speed'])
        if removals and '删除已标记片段' not in recognized:
            recognized.append('删除已标记片段')
        if settings['bgm'] and '加入背景音乐' not in recognized:
            recognized.append('加入背景音乐')
        _number(settings['start'], '开始位置', 0, 86400)
        _number(settings['duration'], '目标时长', .05, 86400)
        _number(settings['minDuration'], '最短时长', 0, 86400)
        _number(settings['minSpeed'], '最低播放速度', .25, 4)
        _number(settings['speed'], '倍速', .25, 4)
        if settings['minSpeed'] > settings['speed'] + 1e-9:
            _error('最低播放速度不能高于目标播放速度')
        if settings['ratio'] not in _VALID_RATIOS or settings['resolution'] not in _VALID_RESOLUTIONS or not isinstance(settings['keepAudio'], bool) or not isinstance(settings['bgm'], bool):
            _error('请选择有效的视频比例、分辨率与原声选项')
        bgm_source, bgm_snapshot, bgm_stream = None, None, None
        if settings['bgm']:
            requested_music = data.get('bgmPath', '')
            if not isinstance(requested_music, str):
                _error('请重新选择本地背景音乐文件')
            bgm_source = (helpers['_local_path'](requested_music, existing=True) if requested_music else
                _load_companion('editor_assets').get_bgm_path(bgm_track) if bgm_track else Path(__file__).with_name('builtin_music.wav'))
            bgm_snapshot = _fingerprint(bgm_source)
            bgm_stream = _audio_source(tool, bgm_source, helpers)
            if bgm_snapshot != _fingerprint(bgm_source):
                _error('背景音乐正在变化，请保存完成后重新生成计划', 'SMART_EDIT_CHANGED')
        total = sum(duration for _, _, duration in kept_segments)
        if total < .01:
            _error('所有画面都已被删除，请至少保留一段视频')
        if settings['start'] >= total - .01:
            _error('开始位置超过视频总时长，请缩短跳过的时间')
        requested_speed = settings['speed']
        requested_duration = settings['duration']
        minimum = settings['minDuration']
        notes = []
        transitions = _load_companion('transitions')
        spatial = _load_companion('smart_vision') if spatial_crops else None
        def assembled_at(speed):
            try:
                return assembly.pieces(kept_segments, settings['start'], speed, assembly_options,
                    0 if use_all else settings['duration'], transition['duration'] if transition['type']!='none' else 0)
            except ValueError as error:_error(str(error))
        def timeline_at(speed):
            """Build the one timeline used for availability, checks and rendering."""
            try:
                selected = assembled_at(speed)
                repairs = copy.deepcopy(spatial_crops)
                if spatial is not None:
                    repairs = spatial.normalize_repair_pieces(repairs, selected)
                    selected = spatial.split_repair_pieces(selected, repairs)
                lengths = [length/speed for _, _, length in selected]
                layout = _smooth_joins(lengths, transition, fps)
                if not use_all and settings['duration'] < layout['duration'] - 1e-8:
                    count = sum(offset < settings['duration'] - 1e-8
                                for offset in layout['starts'])
                    selected = selected[:count]
                    lengths = lengths[:count]
                    incoming = (layout['joins'][count-2]['duration']
                                if count > 1 else 0.)
                    length = min(lengths[-1], max(
                        settings['duration'] - layout['starts'][count-1],
                        incoming * 2))
                    index, offset, _ = selected[-1]
                    selected[-1] = (index, offset, length * speed)
                    lengths[-1] = length
                    layout = _smooth_joins(lengths, transition, fps)
                return {'speed': speed, 'pieces': selected, 'repairs': repairs,
                        'lengths': lengths, 'layout': layout}
            except (TypeError, ValueError) as error:
                _error(getattr(error, 'message', str(error)),
                       getattr(error, 'code', 'SMART_EDIT_INPUT'))
        def available_at(speed):
            return timeline_at(speed)['layout']['duration']
        if minimum_policy == 'slowdown' and minimum:
            settings['duration'] = max(settings['duration'], minimum)
            if available_at(settings['speed']) < minimum:
                low, high = settings['minSpeed'], settings['speed']
                if available_at(low) >= minimum:
                    for _ in range(48):
                        middle = (low+high)/2
                        if available_at(middle) >= minimum:
                            low = middle
                        else:
                            high = middle
                    settings['speed'] = low
                else:
                    settings['speed'] = settings['minSpeed']
            if use_all:
                settings['duration'] = max(minimum, available_at(settings['speed']))
            if settings['speed'] < requested_speed - 1e-7:
                notes.append(f'为尽量达到最短 {minimum:g} 秒，已自动将 {requested_speed:g} 倍速调整为 {settings["speed"]:.3f} 倍速；已删除的画面仍会排除。')
            if not use_all and requested_duration < minimum:
                notes.append(f'目标时长 {requested_duration:g} 秒低于最短时长，已优先调整为 {minimum:g} 秒。')
        available = available_at(settings['speed'])
        if use_all:
            settings['duration'] = available
        duration = min(settings['duration'], available)
        minimum_satisfied = duration+1e-7 >= minimum
        if not minimum_satisfied and minimum_policy == 'strict':
            _error(f'无法满足最短时长 {settings["minDuration"]:g} 秒：按当前删减、倍速和目标时长只能生成 {duration:.2f} 秒。请补充素材、调低倍速或调整时长设置。', 'SMART_EDIT_TOO_SHORT')
        width, height = _dimensions(infos[0], settings['ratio'], settings['resolution'])
        effects=_load_companion('editor_assets').prepare_effects(data.get('effects',[]),duration)
        timeline=timeline_at(settings['speed'])
        selected_pieces=timeline['pieces']
        spatial_crops=timeline['repairs']
        available=timeline['layout']['duration']
        if available + 1e-7 < duration:
            _error(f'画面裁剪后的可用成片只有 {available:.2f} 秒，无法满足目标时长 {duration:.2f} 秒',
                   'SMART_EDIT_TOO_SHORT')
        transition_layout=timeline['layout']
        notes.extend(assembly.summary(assembly_options))
        if assembly_options['montageMode']=='balanced':
            recognized.append('均衡取材')
            if settings['keepAudio']:
                notes.append('均衡取材会改变原声顺序；连续口播建议选择“顺序完整”。')
        notes.extend(transition_layout['notes'])
        transition_count = sum(row['type'] != 'none' for row in transition_layout['joins'])
        if transition['type'] != 'none':
            recognized.append('片段转场')
            if transition_count:
                name = next(row['name'] for row in _load_companion('transitions').get_catalog() if row['id'] == transition['type'])
                notes.append(f'在保留片段的 {transition_count} 个连接处加入{name}，原声同步交叉淡化；时长和字幕使用转场后的成片时间。')
            else:
                notes.append('当前成片没有可用的片段连接处，本次无需添加转场。')
        if minimum and not minimum_satisfied:
            if minimum_policy == 'slowdown':
                notes.append(f'已降至最低 {settings["minSpeed"]:g} 倍速，素材仍不足最短 {minimum:g} 秒；将导出最长可用时长约 {duration:.2f} 秒。')
            else:
                notes.append(f'可用成片不足最短 {minimum:g} 秒，按所选方式导出实际时长约 {duration:.2f} 秒。')
        elif minimum:
            notes.append(f'本次计划达到最短成片时长 {minimum:g} 秒。')
        if settings['duration'] > available + .01:
            notes.append(f'素材时长不足，按可用时长导出约 {duration:.2f} 秒；不会循环或冻结补足。')
        if unhandled:
            if re.search(_SEMANTIC_CUT, text) and not removals:
                notes.append('“穿模”等画面问题需要先标记删除区间：请预览视频，填写对应视频的开始与结束时间。标记后可按同一需求剪辑；当前不会猜测或跳过问题画面。')
            else:
                notes.append('以下要求尚不支持，未执行：' + unhandled + '。请改写为时长、开始位置、比例、分辨率、倍速、原声或背景音乐要求。')
        if not recognized:
            notes.append('尚未识别可执行的剪辑要求，请输入例如“剪成15秒，竖屏9:16，保留原声”。')
        if removals:
            notes.append(f'先删除 {len(removals)} 个已标记区间，再按列表顺序拼接保留画面，最后应用开始位置、时长与倍速。')
        if bgm_source:
            notes.append('背景音乐以原速循环铺满成片，并淡入淡出；' + ('与保留的原声混音。' if settings['keepAudio'] else '成片仅保留背景音乐。'))
        if effects:
            notes.append('应用所选特效：'+'、'.join(item['name'] for item in effects)+'；特效时间使用剪辑后成片的时间。')
        if review is not None:
            notes.append(f'已采用 {review["modelName"]} 的视觉分析结果；只删除当前已选区间，请预览确认。')
            notes.extend(note for note in review.get('notes', []) if isinstance(note, str))
            if not review.get('ranges'):
                notes.append('该分析未发现高置信度明显瑕疵，本次保留未标记的画面；采样未覆盖的短暂问题仍需预览确认。')
        plan = dict(settings, duration=round(duration, 8), requestedDuration=requested_duration, availableDuration=round(available, 8),
            **assembly_options,
            usedSourceCount=len({piece[0] for piece in selected_pieces}),
            storyboard=[{'index':index,'sourceStart':offset,'sourceEnd':offset+length,
                'start':transition_layout['starts'][number], 'duration':min(length/settings['speed'],max(0,duration-transition_layout['starts'][number]))}
                for number,(index,offset,length) in enumerate(selected_pieces)],
            requestedSpeed=requested_speed, minSpeed=settings['minSpeed'], minDurationPolicy=minimum_policy, minimumSatisfied=minimum_satisfied,
            requirements=text.strip(), width=width, height=height, inputCount=len(sources), recognized=recognized,
            spatialCrops=[{'index':row['index'],'start':row['start'],'end':row['end'],
                'crop':copy.deepcopy(row['crop'])} for row in spatial_crops],
            unhandled=unhandled, notes=notes, canExecute=bool(recognized) and not unhandled,
            bgmName=(bgm_source.name if data.get('bgmPath') else next((row['name'] for row in _load_companion('editor_assets').get_bgm_tracks() if row['id']==bgm_track),'内置舒缓器乐')) if bgm_source else '', removeRanges=removals,
            analysisId=analysis_id if review is not None else '',
            subtitles=data.get('subtitles',False),speechLanguage=language,subtitleStyle=subtitle_style,bgmTrack=bgm_track,
            transition=transition, transitions=copy.deepcopy(transition_layout), fps=fps,
            effects=[{key:item[key] for key in ('id','name','kind','start','end','opacity','scale','position','chromaKey','keyColor','lutStrength')} for item in effects],
            inputs=[{k: v for k, v in info.items() if not k.startswith('_')} for info in infos])
        identifier = uuid.uuid4().hex
        plans = getattr(self, '_smart_plans', None)
        if plans is None:
            plans = self._smart_plans = {}
        while len(plans) >= 32:
            plans.pop(next(iter(plans)))
        plans[identifier] = dict(database=database, directory=directory, sources=sources, snapshots=snapshots, infos=infos,
            bgmSource=bgm_source, bgmSnapshot=bgm_snapshot, bgmStream=bgm_stream, effects=effects,keptSegments=kept_segments,
            pieces=selected_pieces, plan=copy.deepcopy(plan))
        ledger_module = _load_companion('requirement_ledger')
        ledger = ledger_module.RequirementLedger.build({**plan, 'requirements': text.strip()})
        plans[identifier]['verifyDelivery'] = (
            lambda partial: _verify_smart_delivery(ledger, partial)
        )
        return {'planId': identifier, 'plan': plan}

    def _smart_validate(self, record, verify_effect_content=False):
        if callable(record.get('validateExtra')):record['validateExtra']()
        database, directory = self._smart_project()
        if (database, directory) != (record['database'], record['directory']):
            _error('项目已切换，请为当前项目重新生成剪辑计划', 'SMART_EDIT_CHANGED')
        if record['snapshots'] != [_fingerprint(path) for path in record['sources']]:
            _error('输入视频已变化，请重新生成剪辑计划', 'SMART_EDIT_CHANGED')
        if record.get('bgmSource') and record['bgmSnapshot'] != _fingerprint(record['bgmSource']):
            _error('背景音乐已变化，请重新生成剪辑计划', 'SMART_EDIT_CHANGED')
        _load_companion('editor_assets').validate_effects(record.get('effects',[]),verify_content=verify_effect_content)

    def video_smartExecute(self, data):
        self._smart_project()
        record = getattr(self, '_smart_plans', {}).get(data.get('planId'))
        if record is None:
            _error('请先生成当前项目的剪辑计划', 'SMART_EDIT_PLAN_REQUIRED')
        self._smart_validate(record,verify_effect_content=True)
        if not record['plan']['canExecute']:
            _error('剪辑要求包含尚不支持的操作，请查看计划提示并修改要求', 'SMART_EDIT_UNSUPPORTED')
        work = lambda progress, control: self._smart_execute_record(record, progress, control)
        return self.api.tasks.start('按我的需求剪辑', work, category='video', location={'route': '/editor/smart'})

    def _smart_execute_record(self, record, progress, control):
        helpers, plan = self._smart_helpers, copy.deepcopy(record['plan'])
        tool = self.api.ctx.ffmpeg_tool()

        check_control(control)
        self._smart_validate(record,verify_effect_content=True)
        root = _inside_project(record['directory'] / 'smart_edits', record['directory'])
        root.mkdir(exist_ok=True)
        root = _inside_project(root, record['directory'])
        folder = root / uuid.uuid4().hex
        folder.mkdir(exist_ok=False)
        ownership = _owned_directory(folder, record['directory'])
        output = folder / 'result.mp4'
        committed = False
        try:
            pieces = [(record['sources'][index], record['infos'][index], offset, length)
                for index, offset, length in record['pieces']]
            transition_layout = plan['transitions']
            has_transitions = any(row['type'] != 'none' for row in transition_layout['joins'])
            exact_final_trim = (
                has_transitions
                or len(pieces) != len(record.get('keptSegments', []))
                or transition_layout['duration'] > plan['duration'] + 1e-7
                or (type(plan.get('availableDuration')) in (int, float)
                    and plan['duration'] < plan['availableDuration'] - 1e-7))
            preparation_span = 70 if exact_final_trim else 85
            preparation_duration = sum(length/plan['speed'] for _, _, _, length in pieces)
            # Keep narration internally for recognition even when final audio is muted.
            audio = (plan['keepAudio'] or plan.get('subtitles',False)) and any(info['hasAudio'] for _, info, _, _ in pieces)
            output_audio = plan['keepAudio'] and audio
            if plan.get('subtitles') and not audio:
                _error('所选片段没有原声，无法根据口播旁白生成字幕', 'SMART_SUBTITLE_NO_AUDIO')
            fps = plan['fps']
            width, height = plan['width'], plan['height']
            processed = 0.0
            with _scratch_directory(folder, record['directory']) as scratch:
                for index, (source, info, offset, input_duration) in enumerate(pieces):
                    check_control(control)
                    self._smart_validate(record)
                    duration = input_duration / plan['speed']
                    progress(int(preparation_span * processed / preparation_duration), f'正在剪辑第 {index+1}/{len(pieces)} 段视频')
                    segment = scratch / f'segment-{index:05d}.mkv'
                    args = ['-protocol_whitelist', 'file,pipe', '-ss', f'{offset:.8f}', '-t', f'{input_duration:.8f}', '-i', source]
                    if audio and not info['hasAudio']:
                        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                    fit=_load_companion('smart_assembly').fit_filter(width,height,plan.get('fitMode','contain'))
                    local_crop=next((row['crop'] for row in plan.get('spatialCrops',[])
                        if row['index']==record['pieces'][index][0]
                        and offset>=row['start']-.000001
                        and offset+input_duration<=row['end']+.000001),None)
                    crop_filter=''
                    if local_crop:
                        crop_width=max(2,round(info['width']*float(local_crop['width'])))
                        crop_height=max(2,round(info['height']*float(local_crop['height'])))
                        crop_x=min(info['width']-crop_width,max(0,round(info['width']*float(local_crop['x']))))
                        crop_y=min(info['height']-crop_height,max(0,round(info['height']*float(local_crop['y']))))
                        crop_filter=f'crop={crop_width}:{crop_height}:{crop_x}:{crop_y},'
                    filters = (f'setpts=(PTS-STARTPTS)/{plan["speed"]:.8f},scale={info["width"]}:{info["height"]},setsar=1,'
                        f'{crop_filter}'
                        f'{fit},fps={fps:.8f},'
                        f'tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration:.8f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p')
                    args += ['-map', f'0:{info["_videoStream"]}', '-vf', filters, '-t', f'{duration:.8f}',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p']
                    if audio:
                        args += ['-map', '0:a:0' if info['hasAudio'] else '1:a:0', '-af',
                            f'aformat=sample_fmts=fltp,{_atempo(plan["speed"])},aresample=48000:async=1:first_pts=0,apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS',
                            '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2']
                    else:
                        args += ['-an']
                    args += ['-map_metadata', '-1', '-metadata:s:v:0', 'rotate=0', segment]
                    helpers['_run_ffmpeg'](tool, args, duration, progress, control, scratch,
                        start=preparation_span * processed / preparation_duration, span=preparation_span * duration / preparation_duration)
                    processed += duration
                manifest = scratch / 'segments.txt'
                manifest.write_text(''.join(f"file 'segment-{i:05d}.mkv'\nduration {length/plan['speed']:.8f}\n"
                    for i, (_, _, _, length) in enumerate(pieces)), encoding='utf-8')
                base_input = ['-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', manifest]
                if has_transitions:
                    progress(70, '正在渲染片段转场和原声交叉淡化')
                    joined = _load_companion('transitions').render_joined_segments(tool,
                        [(scratch/f'segment-{i:05d}.mkv', length/plan['speed']) for i, (_, _, _, length) in enumerate(pieces)],
                        transition_layout, scratch/'joined.mkv', helpers, progress, control, scratch,
                        fps=fps, audio=audio, start=70, span=15)
                    self._smart_validate(record)
                    base_input = ['-protocol_whitelist', 'file,pipe', '-i', joined]
                subtitle_result=None
                if plan.get('subtitles'):
                    progress(85,'正在识别剪辑后的口播旁白并同步字幕')
                    narration=scratch/'narration.wav'
                    helpers['_run_ffmpeg'](tool,[*base_input,
                        '-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-t',f'{plan["duration"]:.8f}',narration],
                        plan['duration'],progress,control,scratch,start=85,span=1)
                    self._smart_validate(record)
                    try:
                        recovery=record.get('workflow')
                        transcript=recovery.get('transcript') if recovery else None
                        if transcript is None:
                            transcript=_load_speech().transcribe(narration,control=control,language=plan['speechLanguage'],
                                progress=lambda percent,message='':progress(86+min(4,max(0,percent)*.04),message))
                            if recovery:recovery.save('transcript',transcript)
                        else:progress(87,'已恢复完成的口播转录')
                        check_control(control)
                        self._smart_validate(record)
                        if _owned_directory(folder,record['directory'])!=ownership:_error('输出目录已变化', 'SMART_EDIT_OUTPUT_PATH')
                        reserved_bottom=any(
                            row.get('op')=='addText'
                            and row.get('params',{}).get('position','bottom')=='bottom'
                            and min(plan['duration'],row.get('params',{}).get('end',plan['duration']))
                                > min(plan['duration'],row.get('params',{}).get('start',0))
                            for row in plan.get('operations',[]) if isinstance(row,dict)
                        )
                        subtitle_result=_load_companion('smart_subtitles').prepare_subtitles(
                            transcript,plan['duration'],width,height,scratch,
                            style=plan['subtitleStyle'],reserve_bottom=reserved_bottom)
                    except (RuntimeError,ValueError) as error:
                        if isinstance(error,BridgeError):raise
                        _error(getattr(error,'message',str(error)),getattr(error,'code','SMART_SUBTITLE_FAILED'))
                    # ASS is also left in the scratch folder for the relative libass filter.
                    for key,name in (('srtPath','subtitles.srt'),('assPath','subtitles.ass')):
                        shutil.copyfile(subtitle_result[key],folder/name)
                        subtitle_result[key]=str(folder/name)
                stage = scratch / 'output.mp4'
                args = list(base_input)
                if plan['bgm']:
                    args += ['-protocol_whitelist', 'file,pipe', '-stream_loop', '-1', '-i', record['bgmSource']]
                effect_graph=_load_companion('editor_assets').build_effect_graph(record.get('effects',[]),width,height,plan['duration'],scratch,2 if plan['bgm'] else 1)
                args+=effect_graph['inputs']
                graph=list(effect_graph['filters'])
                video=effect_graph['output']
                if subtitle_result:
                    graph.append(f'[{video}]ass=filename=subtitles.ass[subtitled]');video='subtitled'
                if exact_final_trim:
                    # Targets may end inside the extra handles retained for a
                    # transition. Copying B-frame packets past -t extends video
                    # beyond the narration clock; trim decoded frames instead.
                    # A spatial repair can also split the final piece so the
                    # encoder must not rely on a pre-repair stream duration.
                    graph.append(f'[{video}]fps={fps:.8f},trim=duration={plan["duration"]:.8f},'
                        'setpts=PTS-STARTPTS[finishedvideo]')
                    video='finishedvideo'
                args += ['-map',f'[{video}]' if video!='0:v:0' else video,'-t',f'{plan["duration"]:.8f}']
                if has_transitions or subtitle_result or effect_graph['count'] or video == 'finishedvideo':
                    args+=['-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p']
                else:args+=['-c:v','copy']
                if plan['bgm']:
                    fades=plan.get('musicFades',{})
                    fade_in=min(float(fades.get('fadeIn',min(.8,plan['duration']/3))),plan['duration'])
                    fade_out=min(float(fades.get('fadeOut',min(.8,plan['duration']/3))),plan['duration'])
                    bed = (f'[1:{record["bgmStream"]}]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                        f'atrim=duration={plan["duration"]:.8f},asetpts=PTS-STARTPTS,volume={plan["bgmVolume"]:.8f},'
                        f'afade=t=in:d={fade_in:.8f},afade=t=out:st={plan["duration"]-fade_out:.8f}:d={fade_out:.8f}[music]')
                    if output_audio:
                        bed += ';[0:a:0]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo[original]'
                        music='music'
                        if plan.get('bgmDucking'):
                            bed += ';[original]asplit=2[voice][sidechain];[music][sidechain]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=350:makeup=1[ducked]'
                            original,music='voice','ducked'
                        else:original='original'
                        bed += f';[{original}][{music}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false:latency=true[mixed]'
                    graph.append(bed)
                    args += ['-map', '[mixed]' if output_audio else '[music]', '-c:a', 'aac', '-b:a', '192k']
                elif output_audio:
                    args += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '192k', '-af', 'aresample=48000:async=1:first_pts=0']
                else:
                    args += ['-an']
                if graph:args+=['-filter_complex',';'.join(graph)]
                args += ['-t', f'{plan["duration"]:.8f}']
                args += ['-map_metadata', '-1', '-movflags', '+faststart', stage]
                helpers['_run_ffmpeg'](tool, args, plan['duration'], progress, control, scratch, start=91 if subtitle_result else 85, span=6 if subtitle_result else 12)
                completed = helpers['_probe'](tool, stage)
                if completed['duration']+.001 < plan.get('minDuration',0) and plan.get('minDurationPolicy','strict') == 'strict':
                    _error('实际导出视频未达到最短时长，未发布成片，请调整时长设置', 'SMART_EDIT_TOO_SHORT')
                if plan.get('speed', 1) + 1e-6 < plan.get('minSpeed', .25):
                    _error('实际导出速度低于已设置的最低倍速，未发布成片', 'SMART_EDIT_TOO_SHORT')
                self._smart_validate(record,verify_effect_content=True)
                if _owned_directory(folder, record['directory']) != ownership:
                    _error('输出目录已变化，请重新执行剪辑', 'SMART_EDIT_OUTPUT_PATH')
                def commit_progress(value,message=''):
                    progress(value,message)
                    self._smart_validate(record,verify_effect_content=True)
                    if _owned_directory(folder,record['directory'])!=ownership:
                        _error('输出目录已变化，未发布成片','SMART_EDIT_OUTPUT_PATH')
                delivery_result={'path':str(stage),'width':width,'height':height,
                    'duration':completed['duration'],'count':len(pieces),'requirements':plan['requirements'],
                    'subtitles':subtitle_result,'transitions':copy.deepcopy(transition_layout),
                    'plan':copy.deepcopy(plan),'probe':copy.deepcopy(completed),
                    'effects':{'count':len(record.get('effects',[])),
                        'names':[item['name'] for item in record.get('effects',[])]}}
                verify_delivery=record.get('verifyDelivery')
                if verify_delivery is not None:
                    delivery_result['requirementReport']=verify_delivery(delivery_result)
                quality=_load_companion('media_quality').inspect_media(
                    tool,stage,completed,plan,subtitle_result,control,commit_progress)
                if quality['status']=='failed':
                    _error('实际成片检查未通过，请查看字幕时间或素材后重试','SMART_QUALITY_FAILED')
                (folder/'quality-report.json').write_text(
                    json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf8')
                helpers['_commit'](stage, output, commit_progress, control)
                committed = True
            return {'path': str(output), 'width': width, 'height': height, 'duration': completed['duration'], 'count': len(pieces), 'requirements': plan['requirements'], 'subtitles':subtitle_result,
                'transitions':copy.deepcopy(transition_layout),
                'requirementReport':delivery_result.get('requirementReport'),
                'qualityReport':quality,
                'effects':{'count':len(record.get('effects',[])),'names':[item['name'] for item in record.get('effects',[])]}}
        finally:
            if not committed:
                _cleanup_owned(folder, ownership, record['directory'])
