"""Bounded transitions and one shared, cancellable normalized-segment renderer.

Only catalog IDs and finite numbers enter the graph. Callers retain ownership
of sources, temporary directories, validation, cancellation and publication.
"""
from __future__ import annotations

import math
from pathlib import Path


_CATALOG = (('none', '无转场'), ('fade', '淡入淡出'), ('dissolve', '溶解'),
    ('wipeleft', '向左擦除'), ('wiperight', '向右擦除'),
    ('slideleft', '向左滑动'), ('slideright', '向右滑动'))


def get_catalog():
    return [dict(id=identifier, name=name) for identifier, name in _CATALOG]


def _fail(message, error):
    if error is not None:
        error(message)
    raise ValueError(message)


def normalize_transition(raw, error=None):
    if raw is None:
        return {'type': 'none', 'duration': 0.}
    if not isinstance(raw, dict) or set(raw) - {'type', 'duration'}:
        _fail('转场参数只能包含类型和时长', error)
    kind = raw.get('type')
    if not isinstance(kind, str) or kind not in {row[0] for row in _CATALOG}:
        _fail('请选择支持的转场类型', error)
    duration = raw.get('duration', 0 if kind == 'none' else .4)
    if type(duration) not in (int, float) or not 0 <= duration <= 2 or not math.isfinite(duration):
        _fail('转场时长需要使用 0.1–2 秒的有限数字', error)
    if kind != 'none' and duration < .1:
        _fail('转场时长需要在 0.1–2 秒之间', error)
    return {'type': kind, 'duration': float(duration) if kind != 'none' else 0.}


def normalize_joins(durations, transitions=None, fps=30, error=None):
    if not isinstance(durations, (list, tuple)) or not durations or len(durations) > 250:
        _fail('转场需要有效的片段列表', error)
    if any(type(value) not in (int, float) or not 0 < value <= 345600 or not math.isfinite(value) for value in durations):
        _fail('转场片段时长无效', error)
    if type(fps) not in (int, float) or not 1 <= fps <= 120 or not math.isfinite(fps):
        _fail('转场帧率无效', error)
    if transitions is None:
        transitions = [None] * (len(durations)-1)
    if not isinstance(transitions, (list, tuple)) or len(transitions) != len(durations)-1:
        _fail('转场数量与片段连接数不一致', error)
    joins, starts, notes = [], [0.], []
    position = float(durations[0])
    for index, raw in enumerate(transitions):
        requested = normalize_transition(raw, error)
        overlap = min(requested['duration'], durations[index]/2, durations[index+1]/2)
        # Each clip allocates at most half its duration to either neighbour.
        # Frame quantization never creates a partial-frame transition.
        overlap = math.floor(overlap * fps + 1e-7) / fps
        kind = requested['type'] if overlap > 0 else 'none'
        if overlap < requested['duration']-1e-7:
            notes.append(f'第 {index+1} 处转场因片段长度或帧率调整为 {overlap:g} 秒。')
        position -= overlap
        starts.append(round(position, 8))
        joins.append(dict(type=kind, duration=round(overlap, 8), offset=round(position, 8)))
        position += durations[index+1]
    return dict(joins=joins, starts=starts, totalOverlap=round(sum(row['duration'] for row in joins), 8),
        duration=round(position, 8), notes=notes)


def render_joined_segments(tool, segments, layout, output, helpers, progress, control, folder,
                           *, fps=30, audio=True, start=0, span=100):
    """Join already normalized local MKV segments; return an intermediate MKV.

    A single graph keeps joins deterministic without repeatedly encoding the
    growing timeline. The graph file avoids Windows command-line size limits.
    """
    # Group adjacent hard cuts with explicit demuxer durations. A concat filter
    # rounds every short clip to complete frames and drifts before later joins.
    groups, boundaries, current = [], [], []
    for index, segment in enumerate(segments):
        current.append(segment)
        if index == len(segments)-1 or layout['joins'][index]['type'] != 'none':
            groups.append(current)
            current = []
            if index < len(segments)-1:
                boundaries.append(layout['joins'][index])
    args, graph = [], []
    for index, group in enumerate(groups):
        duration = sum(segment[1] for segment in group)
        rows = []
        for path, length in group:
            path = Path(path)
            try:
                path = path.relative_to(folder)
            except ValueError:
                pass
            escaped = path.as_posix().replace("'", "'\\''")
            rows.append(f"file '{escaped}'\nduration {length:.8f}\n")
        manifest = Path(folder)/f'transition-group-{index:05d}.txt'
        manifest.write_text(''.join(rows), encoding='utf-8')
        args += ['-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', manifest.name]
        graph.append(f'[{index}:v:0]fps={fps:.8f},settb=AVTB,setpts=PTS-STARTPTS,'
            f'tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration:.8f},format=yuv420p[v{index}]')
        if audio:
            graph.append(f'[{index}:a:0]aresample=48000:async=1:first_pts=0,'
                f'aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS[a{index}]')
    video, sound = 'v0', 'a0'
    for index, join in enumerate(boundaries, 1):
        next_video, next_sound = f'joinedv{index}', f'joineda{index}'
        graph.append(f'[{video}][v{index}]xfade=transition={join["type"]}:'
            f'duration={join["duration"]:.8f}:offset={join["offset"]:.8f},settb=AVTB[{next_video}]')
        if audio:
            graph.append(f'[{sound}][a{index}]acrossfade=d={join["duration"]:.8f}:c1=tri:c2=tri[{next_sound}]')
        video, sound = next_video, next_sound
    graph.append(f'[{video}]fps={fps:.8f},trim=duration={layout["duration"]:.8f},format=yuv420p[transitionvideo]')
    graph_path = Path(folder) / 'transitions.ffgraph'
    graph_path.write_text(';\n'.join(graph), encoding='utf-8')
    args += ['-filter_complex_threads', '1', '-/filter_complex', graph_path,
        '-map', '[transitionvideo]', '-t', f'{layout["duration"]:.8f}',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p']
    args += ['-map', f'[{sound}]', '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2'] if audio else ['-an']
    args += ['-map_metadata', '-1', '-metadata:s:v:0', 'rotate=0', output]
    helpers['_run_ffmpeg'](tool, args, layout['duration'], progress, control, folder, start=start, span=span)
    return Path(output)
