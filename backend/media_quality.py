"""Bounded, cancellable inspection of the encoded output, with honest coverage."""
import math
import os
from pathlib import Path
import re
import subprocess
import time

from app.ui2.common import BridgeError
from app.workers.control import check_control


def scan_windows(duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('成片时长无效')
    if duration <= 120:
        return [(0., duration)]
    return [(0., 20.), (max(0., duration / 2 - 10), 20.), (duration - 20, 20.)]


def _check(code, label, status, message, start=0., end=0.):
    return dict(code=code, label=label, status=status, message=message,
                start=round(start, 3), end=round(end, 3))


def subtitle_checks(segments, duration, style, width, height):
    checks = []
    last = 0.
    for row in segments or []:
        start, end = row.get('start'), row.get('end')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start or end > duration + .08 or start < last - .08):
            checks.append(_check('subtitle_timing', '字幕时间', 'failed',
                                 '字幕时间重叠或超出成片，请重新识别或调整。'))
            break
        last = end
    if segments and not checks:
        checks.append(_check('subtitle_timing', '字幕时间', 'passed', '字幕均在成片时间范围内。'))
    size = style.get('size') or max(16, min(90, round(height * .052)))
    if segments and any(max((len(line) for line in row['text'].splitlines()), default=0)
                        * size > width * .92 for row in segments):
        checks.append(_check('subtitle_layout', '字幕安全区', 'review',
                             '部分字幕较长，请查看是否超出安全区或遮挡主体。'))
    return checks


def _capture(tool, args, control, timeout=90):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen([str(tool.ffmpeg), '-hide_banner', '-nostdin', *map(str, args)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, creationflags=flags, shell=False)
    deadline = time.monotonic() + timeout
    try:
        while True:
            check_control(control)
            if time.monotonic() > deadline:
                raise BridgeError('QUALITY_TIMEOUT', '成片检查超时，可在任务中心重试。')
            try:
                _, error = process.communicate(timeout=.2)
                return process.returncode, error.decode('utf8', 'replace')[-200000:]
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def inspect_media(tool, path, info, plan, subtitles, control, progress=None):
    duration = float(info['duration'])
    windows = scan_windows(duration)
    checks = []
    for index, (offset, length) in enumerate(windows):
        check_control(control)
        if progress:
            progress(97, f'正在检查实际成片 {index + 1}/{len(windows)}')
        args = ['-v', 'info', '-protocol_whitelist', 'file,pipe', '-ss', f'{offset:.6f}',
                '-i', Path(path), '-t', f'{length:.6f}', '-map', '0:v:0',
                '-vf', 'fps=5,scale=160:-2,blackdetect=d=0.4:pix_th=0.10,freezedetect=n=-50dB:d=2']
        if info.get('hasAudio'):
            args += ['-map', '0:a:0', '-af', 'volumedetect']
        args += ['-f', 'null', '-']
        code, log = _capture(tool, args, control)
        if code:
            raise BridgeError('QUALITY_DECODE_FAILED', '导出文件无法完整解码，未发布成片；请重试或检查素材。')
        for start, end in re.findall(r'black_start:([\d.]+)\s+black_end:([\d.]+)', log):
            checks.append(_check('black_frames', '黑屏画面', 'review',
                '检测到连续暗画面；若为刻意的黑场可保留。', offset + float(start), offset + float(end)))
        freeze = re.search(r'freeze_start:\s*([\d.]+)', log)
        if freeze and not any(row.get('op') == 'freeze' for row in plan.get('operations', [])):
            finish = re.search(r'freeze_end:\s*([\d.]+)', log[freeze.end():])
            checks.append(_check('still_frames', '较长静帧', 'review',
                '画面长时间变化很小；请确认是静态内容还是异常停顿。',
                offset + float(freeze[1]), offset + (float(finish[1]) if finish else length)))
        peak = re.search(r'max_volume:\s*(-?[\d.]+)\s*dB', log)
        if peak and float(peak[1]) >= -.05:
            checks.append(_check('audio_peak', '声音峰值', 'review',
                '声音接近满幅，建议试听是否有爆音。', offset, offset + length))
    checks.insert(0, _check('decoded_media', '成片解码', 'passed', '已检查实际编码的视频与音轨。'))
    if subtitles:
        checks.extend(subtitle_checks(subtitles.get('segments', []), duration,
            subtitles.get('style', {}), int(info.get('width', plan.get('width', 1920))),
            int(info.get('height', plan.get('height', 1080)))))
        checks.append(_check('subtitle_semantics', '字幕内容与遮挡', 'review',
            '时间检查已执行；错字、口型同步及是否遮挡主体仍需观看成片复核。'))
    if plan.get('spatialCrops'):
        checks.append(_check('composition', '裁剪构图', 'review',
            '已限制自动放大幅度；请预览各处构图与裁剪衔接。'))
    status = 'failed' if any(row['status'] == 'failed' for row in checks) else (
        'review' if any(row['status'] == 'review' for row in checks) else 'passed')
    return {'schema': 1, 'status': status, 'coverage': 'full' if len(windows) == 1 else 'sampled',
            'windows': [{'start': a, 'end': a + b} for a, b in windows], 'checks': checks,
            'message': '需要预览复核' if status == 'review' else '检查未通过' if status == 'failed' else '基础成片检查通过'}


def silence_boundaries(tool, source, duration, control):
    """Evidence only: no transcript, inferred sentence, or invented quiet boundary."""
    code, log = _capture(tool, ['-v', 'info', '-protocol_whitelist', 'file,pipe',
        '-i', source, '-vn', '-t', str(min(duration, 600)),
        '-af', 'silencedetect=noise=-35dB:d=0.12', '-f', 'null', '-'], control)
    if code:
        return []
    return [float(value) for value in re.findall(r'silence_(?:start|end):\s*([\d.]+)', log)]


def align_removals(ranges, boundaries, durations, maximum=.25):
    result = []
    for row in ranges:
        value = dict(row)
        points = boundaries.get(row['index'], [])
        # Expand only slightly around confirmed defects, never leave a known
        # defect in the retained footage merely to hit a convenient pause.
        left = [p for p in points if max(0, row['start'] - maximum) <= p <= row['start']]
        right = [p for p in points if row['end'] <= p <= min(durations[row['index']], row['end'] + maximum)]
        if left:
            value['start'] = max(left)
        if right:
            value['end'] = min(right)
        result.append(value)
    return result
