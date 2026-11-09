"""Local, cancellable rendering of the manual video-tools timeline.

The mixin deliberately has no project or AI dependency. VideoActions supplies
its existing path, probing, encoder and atomic publication helpers.
"""
from __future__ import annotations

import math
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from app.ui2.common import BridgeError
from app.workers.control import check_control


_RATIOS = {'自动', '16:9', '9:16', '1:1', '4:3', '3:4', '21:9'}
_RESOLUTIONS = {'原画', '720p', '1080p', '2K', '4K'}
_FPS = {24, 25, 30, 50, 60}


def _error(message, code='TIMELINE_INVALID'):
    raise BridgeError(code, message)


def _number(value, name, minimum, maximum):
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        _error(f'{name}需要在 {minimum:g}–{maximum:g} 之间')
    return float(value)


def _identity(path, *, directory=False):
    try:
        if path.resolve() != path or (not path.is_dir() if directory else not path.is_file()):
            raise OSError('path changed')
        stat = path.stat()
        if directory:
            return stat.st_dev, stat.st_ino
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    except (OSError, RuntimeError, ValueError):
        _error('素材或输出目录已变化，请重新选择后导出', 'TIMELINE_CHANGED')


def _clock(value):
    ticks = round(value * 100)
    minutes, seconds = divmod(ticks // 100, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{ticks % 100:02d}'


def _probe_audio(tool, path, helpers):
    raw = helpers['_capture']([tool.ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-show_streams', '-show_format', '-of', 'json', path])
    try:
        info = json.loads(raw)
        streams = [row for row in info.get('streams', []) if row.get('codec_type') == 'audio']
        stream = next((row for row in streams if row.get('disposition', {}).get('default')), None)
        stream = stream if stream is not None else next(iter(streams))
        duration = None
        for raw_duration in (stream.get('duration'), info.get('format', {}).get('duration')):
            try:
                value = float(raw_duration)
            except (ValueError, TypeError):
                continue
            if math.isfinite(value) and value >= .05:
                duration = value
                break
        if duration is None:
            raise ValueError('invalid duration')
        return dict(path=str(path), name=path.name, duration=duration, hasAudio=True,
            audioCodec=str(stream.get('codec_name') or ''), sampleRate=int(stream.get('sample_rate') or 0),
            channels=int(stream.get('channels') or 0), _audioStream=int(stream['index']))
    except (ValueError, KeyError, TypeError, StopIteration):
        _error('所选文件没有有效音轨，请选择完整的音频文件或带原声的视频', 'TIMELINE_AUDIO_INVALID')


def _plain_text(value):
    # Neither user text nor font names can introduce ASS override commands.
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    value = re.sub(r'[\x00-\x09\x0b-\x1f\x7f]', ' ', value)
    return value.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')


def _write_ass(rows, width, height, folder):
    styles, events = [], []
    for index, row in enumerate(rows):
        color = row['color']
        color = '&H00' + color[5:7] + color[3:5] + color[1:3]
        alignment = {'top': 8, 'center': 5, 'bottom': 2}[row['position']]
        margin = max(4, round(height * .045))
        styles.append(f'Style: Text{index},{row["font"]},{row["size"]:g},{color},{color},&H00141414,&H60000000,0,0,0,0,100,100,0,0,1,1,0,{alignment},8,8,{margin},1')
        events.append(f'Dialogue: {index},{_clock(row["start"])},{_clock(row["end"])},Text{index},,0,0,0,,{_plain_text(row["text"])}')
    text = (f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        + '\n'.join(styles) + '\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
        + '\n'.join(events) + '\n')
    (folder / 'timeline.ass').write_text(text, encoding='utf-8-sig')


class TimelineEditingMixin:
    def video_imageProbe(self, data):
        return self._smart_helpers['_load_editor_extension']('timeline_compositor').image_probe(
            data, self.api.ctx.ffmpeg_tool(), self._smart_helpers)

    def video_audioProbe(self, data):
        if not isinstance(data, dict):
            _error('音频素材参数无效')
        helpers = self._smart_helpers
        source = helpers['_local_path'](data.get('path'), existing=True)
        before = _identity(source)
        info = _probe_audio(self.api.ctx.ffmpeg_tool(), source, helpers)
        if _identity(source) != before:
            _error('音频素材正在变化，请保存完成后重新导入', 'TIMELINE_CHANGED')
        return {key: value for key, value in info.items() if not key.startswith('_')}

    def video_timelineExport(self, data):
        if not isinstance(data, dict):
            _error('时间线导出参数无效')
        if 'documentVersion' in data:
            if 'smartFinishing' in data:
                return self._smart_helpers['_load_editor_extension']('timeline_finishing').start_export(self,data)
            return self._smart_helpers['_load_editor_extension']('timeline_compositor').start_export(self, data)
        helpers = self._smart_helpers
        companion = helpers['_load_editor_extension']('smart_editing')
        transitions = companion._load_companion('transitions')
        tool = self.api.ctx.ffmpeg_tool()
        clips, overlays, texts = data.get('clips'), data.get('overlays', []), data.get('texts', [])
        audio_clips = data.get('audioClips', [])
        if not isinstance(clips, list) or not 1 <= len(clips) <= 200:
            _error('请在主轨放置 1–200 段视频')
        if not isinstance(overlays, list) or len(overlays) > 20:
            _error('叠加轨最多支持 20 段视频')
        if not isinstance(texts, list) or len(texts) > 200:
            _error('文字轨最多支持 200 条文字')
        if len(clips) + len(overlays) + len(texts) > 200:
            _error('时间线最多支持 200 个视觉图层')
        if not isinstance(audio_clips, list) or len(audio_clips) > 50:
            _error('独立音频轨最多支持 50 段音频')
        ratio, resolution, fps = data.get('ratio', '自动'), data.get('resolution', '原画'), data.get('fps', 30)
        if not isinstance(ratio, str) or ratio not in _RATIOS or not isinstance(resolution, str) or resolution not in _RESOLUTIONS:
            _error('请选择有效的视频比例和分辨率')
        if type(fps) not in (int, float) or fps not in _FPS or not math.isfinite(fps):
            _error('帧率请选择 24、25、30、50 或 60')
        fps = int(fps)
        sources, infos = {}, {}

        def load_source(raw):
            source = helpers['_local_path'](raw, existing=True)
            if source not in sources:
                sources[source] = _identity(source)
                infos[source] = helpers['_probe'](tool, source)
                if _identity(source) != sources[source]:
                    _error('素材正在变化，请保存完成后再导出', 'TIMELINE_CHANGED')
            return source, infos[source]

        def prepare_clip(row, overlay=False):
            if not isinstance(row, dict):
                _error('视频片段参数无效')
            source, info = load_source(row.get('path'))
            start = _number(row.get('trimStart', 0), '素材入点', 0, info['duration'])
            end = _number(row.get('trimEnd', info['duration']), '素材出点', 0, info['duration'])
            speed = _number(row.get('speed', 1), '视频倍速', .25, 4)
            volume = _number(row.get('volume', 0 if overlay else 1), '视频音量', 0, 1)
            duration = (end - start) / speed
            if duration < .05 - 1e-8:
                _error('视频片段至少需要保留 0.05 秒，且出点必须晚于入点')
            return dict(path=source, info=dict(info), trimStart=start, trimEnd=end,
                speed=speed, volume=volume, duration=duration,
                transitionToNext=transitions.normalize_transition(row.get('transitionToNext'), error=_error))

        prepared = tuple(prepare_clip(row) for row in clips)
        raw_duration = sum(row['duration'] for row in prepared)
        transition_layout = transitions.normalize_joins([row['duration'] for row in prepared],
            [row['transitionToNext'] for row in prepared[:-1]], fps=fps, error=_error)
        duration = transition_layout['duration']
        has_transitions = any(row['type'] != 'none' for row in transition_layout['joins'])
        if duration > 86400:
            _error('时间线总时长不能超过 24 小时')
        width, height = companion._dimensions(prepared[0]['info'], ratio, resolution)
        layers = []
        for row in overlays:
            layer = prepare_clip(row, True)
            offset = _number(row.get('start', 0), '叠加开始时间', 0, duration)
            if offset >= duration:
                _error('叠加开始时间超出主轨，请调整叠加位置')
            x = _number(row.get('x', 0), '叠加横向位置', 0, 1)
            y = _number(row.get('y', 0), '叠加纵向位置', 0, 1)
            box_width = _number(row.get('width', .3), '叠加宽度', 0, 1)
            box_height = _number(row.get('height', .3), '叠加高度', 0, 1)
            if box_width <= 0 or box_height <= 0 or x + box_width > 1 + 1e-9 or y + box_height > 1 + 1e-9:
                _error('叠加位置和尺寸必须位于画布范围内')
            px, py = min(width - 1, round(x * width)), min(height - 1, round(y * height))
            pw, ph = max(1, min(width - px, round(box_width * width))), max(1, min(height - py, round(box_height * height)))
            layers.append(dict(layer, start=offset, duration=min(layer['duration'], duration-offset),
                x=px, y=py, width=pw, height=ph, opacity=_number(row.get('opacity', 1), '叠加透明度', 0, 1)))
        layers = tuple(layers)
        captions = []
        for row in texts:
            if not isinstance(row, dict):
                _error('文字参数无效')
            text, font = row.get('text'), row.get('font', 'Microsoft YaHei')
            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                _error('请输入有效文字（每条最多 4000 字）')
            if not isinstance(font, str) or not font.strip() or len(font) > 80 or re.search(r'[\x00-\x1f\x7f,{}\\]', font):
                _error('文字字体名称无效')
            start = _number(row.get('start', 0), '文字开始时间', 0, duration)
            end = _number(row.get('end', duration), '文字结束时间', 0, duration)
            if start >= duration or end <= start:
                _error('文字时间超出主轨或结束时间早于开始时间，请调整')
            color, position = row.get('color', '#FFFFFF'), row.get('position', 'bottom')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                _error('文字颜色需要使用 #RRGGBB 格式')
            if not isinstance(position, str) or position not in ('top', 'center', 'bottom'):
                _error('文字位置请选择顶部、居中或底部')
            captions.append(dict(text=text, font=font.strip(), start=start, end=end, color=color, position=position,
                size=_number(row.get('size', 48), '文字字号', 12, 120)))
        captions = tuple(captions)
        audio_infos, audio_layers = {}, []
        for row in audio_clips:
            if not isinstance(row, dict):
                _error('独立音频片段参数无效')
            source = helpers['_local_path'](row.get('path'), existing=True)
            if source not in audio_infos:
                before = _identity(source)
                if source in sources and sources[source] != before:
                    _error('音频素材已变化，请重新导入后导出', 'TIMELINE_CHANGED')
                audio_infos[source] = _probe_audio(tool, source, helpers)
                if _identity(source) != before:
                    _error('音频素材正在变化，请保存完成后导出', 'TIMELINE_CHANGED')
                sources[source] = before
            info = audio_infos[source]
            trim_start = _number(row.get('trimStart', 0), '音频素材入点', 0, info['duration'])
            trim_end = _number(row.get('trimEnd', info['duration']), '音频素材出点', 0, info['duration'])
            speed = _number(row.get('speed', 1), '音频倍速', .25, 4)
            volume = _number(row.get('volume', 1), '音频音量', 0, 1)
            muted = row.get('muted', False)
            if type(muted) is not bool:
                _error('音频静音选项无效')
            length = (trim_end - trim_start) / speed
            if length < .05 - 1e-8:
                _error('音频片段至少需要保留 0.05 秒，且出点必须晚于入点')
            offset = _number(row.get('start', 0), '音频开始时间', 0, duration)
            if offset >= duration:
                _error('音频开始时间超出主轨，请调整音频位置')
            audio_layers.append(dict(path=source, stream=info['_audioStream'], trimStart=trim_start,
                speed=speed, volume=0 if muted else volume, start=offset, duration=min(length, duration-offset)))
        audio_layers = tuple(audio_layers)
        music = data.get('music')
        if music is not None:
            if not isinstance(music, dict):
                _error('配乐参数无效')
            path, track = music.get('path', ''), music.get('trackId', '')
            if not isinstance(path, str) or not isinstance(track, str):
                _error('请重新选择本地配乐或内置音乐')
            loop = music.get('loop', True)
            if type(loop) is not bool:
                _error('配乐循环选项无效')
            volume = _number(music.get('volume', .18), '配乐音量', 0, 1)
            if path:
                path = helpers['_local_path'](path, existing=True)
            elif track:
                path = helpers['_load_editor_extension']('editor_assets').get_bgm_path(track).resolve()
            else:
                _error('请选择本地配乐或内置音乐')
            before = _identity(path)
            stream = companion._audio_source(tool, path, helpers)
            if _identity(path) != before or (path in sources and sources[path] != before):
                _error('配乐正在变化，请保存完成后导出', 'TIMELINE_CHANGED')
            sources[path] = before
            music = dict(path=path, stream=stream, loop=loop, volume=volume)
        output = helpers['_output_path'](data.get('output'), tuple(sources))
        parent = output.parent
        parent_identity = _identity(parent, directory=True)
        snapshots = tuple(sources.items())

        def validate(folder=None, ownership=None):
            if _identity(parent, directory=True) != parent_identity:
                _error('输出目录已变化，请重新选择保存位置', 'TIMELINE_CHANGED')
            if folder is not None and _identity(folder, directory=True) != ownership:
                _error('导出临时目录已变化，请重新导出', 'TIMELINE_CHANGED')
            for source, identity in snapshots:
                if _identity(source) != identity:
                    _error('素材已变化，请重新导入后导出', 'TIMELINE_CHANGED')
            if os.path.lexists(output):
                _error('输出文件已存在，请选择新的文件名', 'VIDEO_OUTPUT_EXISTS')

        validate()

        def work(progress, control):
            check_control(control)
            validate()
            folder = Path(tempfile.mkdtemp(prefix='.aive-timeline-', dir=parent))
            ownership = _identity(folder, directory=True)
            try:
                validate(folder, ownership)
                processed = 0.
                preparation_span = 60 if has_transitions else 70
                for index, row in enumerate(prepared):
                    check_control(control)
                    validate(folder, ownership)
                    progress(int(preparation_span * processed / raw_duration), f'正在处理主轨第 {index+1}/{len(prepared)} 段')
                    info, length = row['info'], row['duration']
                    args = ['-protocol_whitelist', 'file,pipe', '-ss', f'{row["trimStart"]:.8f}', '-t', f'{row["trimEnd"]-row["trimStart"]:.8f}', '-i', row['path']]
                    audible = info['hasAudio'] and row['volume'] > 0
                    if not audible:
                        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                    video = (f'setpts=(PTS-STARTPTS)/{row["speed"]:.8f},scale={info["width"]}:{info["height"]},setsar=1,'
                        f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},'
                        f'tpad=stop_mode=clone:stop_duration=0.1,trim=duration={length:.8f},setpts=PTS-STARTPTS,format=yuv420p')
                    audio = ('aformat=sample_fmts=fltp:channel_layouts=stereo,' + (companion._atempo(row['speed']) + ',' if audible else '') +
                        f'aresample=48000:async=1:first_pts=0,volume={row["volume"]:.8f},apad,atrim=duration={length:.8f},asetpts=PTS-STARTPTS')
                    args += ['-map', f'0:{info["_videoStream"]}', '-map', '0:a:0' if audible else '1:a:0', '-vf', video, '-af', audio,
                        '-t', f'{length:.8f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', '-map_metadata', '-1', '-metadata:s:v:0', 'rotate=0', folder/f'segment-{index:05d}.mkv']
                    helpers['_run_ffmpeg'](tool, args, length, progress, control, folder,
                        start=preparation_span*processed/raw_duration, span=preparation_span*length/raw_duration)
                    processed += length
                validate(folder, ownership)
                manifest = folder / 'segments.txt'
                # Explicit durations prevent frame rounding in each normalized
                # segment from accumulating into the manual timeline clock.
                manifest.write_text(''.join(f"file 'segment-{index:05d}.mkv'\nduration {row['duration']:.8f}\n" for index, row in enumerate(prepared)), encoding='utf-8')
                args = ['-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', manifest]
                if has_transitions:
                    progress(60, '正在渲染主轨转场和原声交叉淡化')
                    joined = transitions.render_joined_segments(tool,
                        [(folder/f'segment-{index:05d}.mkv', row['duration']) for index, row in enumerate(prepared)],
                        transition_layout, folder/'joined.mkv', helpers, progress, control, folder,
                        fps=fps, audio=True, start=60, span=10)
                    validate(folder, ownership)
                    args = ['-protocol_whitelist', 'file,pipe', '-i', joined]
                graph = [f'[0:v:0]fps={fps},tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration:.8f},setpts=PTS-STARTPTS[main0]',
                    f'[0:a:0]aresample=48000:async=1:first_pts=0,apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS[baseaudio]']
                video, audio_labels = 'main0', ['baseaudio']
                for index, row in enumerate(layers, 1):
                    args += ['-protocol_whitelist', 'file,pipe', '-ss', f'{row["trimStart"]:.8f}', '-t', f'{row["duration"]*row["speed"]:.8f}', '-i', row['path']]
                    info = row['info']
                    graph.append(f'[{index}:{info["_videoStream"]}]setpts=(PTS-STARTPTS)/{row["speed"]:.8f},scale={info["width"]}:{info["height"]},setsar=1,'
                        f'scale={row["width"]}:{row["height"]}:force_original_aspect_ratio=decrease,format=rgba,'
                        f'pad={row["width"]}:{row["height"]}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,colorchannelmixer=aa={row["opacity"]:.8f},'
                        f'setpts=PTS+{row["start"]:.8f}/TB[overlay{index}]')
                    graph.append(f'[{video}][overlay{index}]overlay=x={row["x"]}:y={row["y"]}:eof_action=repeat:repeatlast=1:'
                        f"enable='gte(t,{row['start']:.8f})*lt(t,{row['start']+row['duration']:.8f})'[main{index}]")
                    video = f'main{index}'
                    if info['hasAudio'] and row['volume'] > 0:
                        label = f'layeraudio{index}'
                        graph.append(f'[{index}:a:0]aformat=sample_fmts=fltp:channel_layouts=stereo,{companion._atempo(row["speed"])},'
                            f'aresample=48000:async=1:first_pts=0,volume={row["volume"]:.8f},apad,atrim=duration={row["duration"]:.8f},'
                            f'asetpts=PTS-STARTPTS,adelay={round(row["start"]*48000)}S:all=1,asetpts=N/SR/TB,apad,atrim=duration={duration:.8f}[{label}]')
                        audio_labels.append(label)
                if music:
                    index = 1 + len(layers)
                    args += ['-protocol_whitelist', 'file,pipe']
                    if music['loop']:
                        args += ['-stream_loop', '-1']
                    args += ['-i', music['path']]
                    graph.append(f'[{index}:{music["stream"]}]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                        f'asetpts=PTS-STARTPTS,volume={music["volume"]:.8f},apad,atrim=duration={duration:.8f}[musicaudio]')
                    audio_labels.append('musicaudio')
                next_input = 1 + len(layers) + int(music is not None)
                for number, row in enumerate(audio_layers):
                    if row['volume'] <= 0:
                        continue
                    index, label = next_input, f'trackaudio{number}'
                    next_input += 1
                    args += ['-protocol_whitelist', 'file,pipe', '-ss', f'{row["trimStart"]:.8f}',
                        '-t', f'{row["duration"]*row["speed"]:.8f}', '-i', row['path']]
                    graph.append(f'[{index}:{row["stream"]}]aformat=sample_fmts=fltp:channel_layouts=stereo,'
                        f'{companion._atempo(row["speed"])},aresample=48000:async=1:first_pts=0,volume={row["volume"]:.8f},'
                        f'apad,atrim=duration={row["duration"]:.8f},asetpts=PTS-STARTPTS,'
                        # Reset the delayed clock from actual sample counts.
                        # FFmpeg 9 can otherwise retain the pre-delay atempo
                        # time base when a second duration trim follows it.
                        f'adelay={round(row["start"]*48000)}S:all=1,asetpts=N/SR/TB,apad,atrim=duration={duration:.8f}[{label}]')
                    audio_labels.append(label)
                audio = audio_labels[0]
                if len(audio_labels) > 1:
                    graph.append(''.join(f'[{label}]' for label in audio_labels) +
                        f'amix=inputs={len(audio_labels)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false:latency=true[mixed]')
                    audio = 'mixed'
                if captions:
                    _write_ass(captions, width, height, folder)
                    graph.append(f'[{video}]ass=filename=timeline.ass[captioned]')
                    video = 'captioned'
                stage = folder / 'output.mp4'
                # Keep large multi-track filter graphs out of Windows' 32K
                # process command limit. FFmpeg 9 loads this owned local file.
                graph_file = folder / 'timeline.ffgraph'
                graph_file.write_text(';'.join(graph), encoding='utf-8')
                args = [os.path.relpath(value, folder) if isinstance(value, Path) and value.is_relative_to(parent) else value for value in args]
                args += ['-filter_complex_threads', '1', '-/filter_complex', graph_file.name, '-map', f'[{video}]', '-map', f'[{audio}]',
                    '-t', f'{duration:.8f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-map_metadata', '-1', '-metadata:s:v:0', 'rotate=0', '-movflags', '+faststart', stage]
                helpers['_run_ffmpeg'](tool, args, duration, progress, control, folder, start=70, span=27)
                completed = helpers['_probe'](tool, stage)
                validate(folder, ownership)

                def commit_progress(percent, message=''):
                    progress(percent, message)
                    # _commit reports 98 before renaming. Revalidate after that
                    # callback as it can yield to other UI work or cancellation.
                    validate(folder, ownership)

                helpers['_commit'](stage, output, commit_progress, control)
                return dict(path=str(output), width=width, height=height, duration=completed['duration'],
                    count=len(prepared), textCount=len(captions), overlayCount=len(layers), audioCount=len(audio_layers), transitions=transition_layout)
            finally:
                # Only remove the directory this worker created, and only when
                # neither it nor its parent has been replaced or redirected.
                try:
                    if _identity(parent, directory=True) == parent_identity and _identity(folder, directory=True) == ownership:
                        shutil.rmtree(folder)
                except (OSError, BridgeError):
                    pass

        return self.api.tasks.start('时间线剪辑导出', work, category='video', location={'route': '/video-tools'})
