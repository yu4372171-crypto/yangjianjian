"""Immutable requirement ledger shared by planning, rendering and acceptance."""
from __future__ import annotations

import copy
import hashlib
import json
import math


_SETTINGS = ('start', 'duration', 'minDuration', 'minSpeed', 'speed', 'ratio', 'resolution',
             'keepAudio', 'bgm', 'bgmVolume')
_OPTIONS = ('bgmTrack', 'subtitleStyle', 'transition', 'montageMode',
            'shotDuration', 'fitMode', 'bgmDucking')
_FLAGS = ('subtitles', 'visualCleanup', 'preserveFrames')


def _stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _normalize_plan(plan):
    """Expose the accepted settings consistently across both plan formats.

    Dialogue plans carry nested settings/options, while the older explicit
    smart-editing path stores the same values at the top level.  The ledger is
    shared by both renderers, so normalize only the accepted fields and retain
    the rest of the plan for output verification.
    """
    if not isinstance(plan, dict):
        return plan
    normalized = copy.deepcopy(plan)
    nested_settings = plan.get('settings')
    if not isinstance(nested_settings, dict):
        nested_settings = {}
    settings = {}
    for key in _SETTINGS:
        if key in plan:
            settings[key] = copy.deepcopy(plan[key])
        if key in nested_settings:
            settings[key] = copy.deepcopy(nested_settings[key])
    normalized['settings'] = settings
    nested_options = plan.get('options')
    if not isinstance(nested_options, dict):
        nested_options = {}
    options = {}
    for key in _OPTIONS:
        if key in plan:
            options[key] = copy.deepcopy(plan[key])
        if key in nested_options:
            options[key] = copy.deepcopy(nested_options[key])
    normalized['options'] = options
    operations = plan.get('operations', [])
    normalized['operations'] = copy.deepcopy(operations) if isinstance(operations, list) else []
    return normalized


class RequirementLedger:
    """A detached, hash-addressed snapshot of the complete accepted target."""

    def __init__(self, plan):
        if not isinstance(plan, dict):
            raise ValueError('需求清单必须来自完整剪辑计划')
        normalized = _normalize_plan(plan)
        settings = normalized.get('settings')
        options = normalized.get('options', {})
        operations = normalized.get('operations', [])
        if not isinstance(settings, dict) or not isinstance(options, dict) or not isinstance(operations, list):
            raise ValueError('需求清单的剪辑计划结构无效')
        self.settings = {key: copy.deepcopy(settings[key]) for key in _SETTINGS if key in settings}
        self.options = {key: copy.deepcopy(options[key]) for key in _OPTIONS if key in options}
        # Older smart-plan records expose accepted presentation choices at
        # the top level. Preserve those facts when building the ledger.
        aliases = {'subtitleStyle': 'subtitleStyle', 'bgmTrack': 'bgmTrack',
                   'transition': 'transition', 'fitMode': 'fitMode'}
        for option, source in aliases.items():
            if option not in self.options and source in plan:
                self.options[option] = copy.deepcopy(plan[source])
        self.operations = copy.deepcopy(operations)
        self.flags = {key: copy.deepcopy(plan[key]) for key in _FLAGS if key in plan}
        self.requirements = str(plan.get('requirements', ''))
        self.plan = normalized
        self.revision = hashlib.sha256(_stable({
            'settings': self.settings, 'options': self.options,
            'operations': self.operations, 'flags': self.flags,
            'requirements': self.requirements,
        }).encode('utf-8')).hexdigest()

    @classmethod
    def build(cls, plan):
        return cls(plan)

    def target(self):
        return {
            'revision': self.revision,
            'requirements': self.requirements,
            'settings': copy.deepcopy(self.settings),
            'options': copy.deepcopy(self.options),
            'operations': copy.deepcopy(self.operations),
            **copy.deepcopy(self.flags),
        }


def _same_number(left, right, tolerance=0.001):
    return (type(left) in (int, float) and type(right) in (int, float)
            and math.isfinite(left) and math.isfinite(right)
            and abs(float(left) - float(right)) <= tolerance)


def _same_value(left, right):
    if isinstance(left, float) or isinstance(right, float):
        return _same_number(left, right)
    return left == right


def _option_matches(key, expected, actual):
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return _same_value(expected, actual)
    # The renderer validates and fills a preset into the complete style object.
    # Every customer-selected field still has to survive exactly.
    return all(key in actual and _same_value(value, actual[key])
               for key, value in expected.items())


def _operation_present(required, actual):
    if not isinstance(actual, list):
        return False
    for row in actual:
        if not isinstance(row, dict) or row.get('op') != required.get('op') or row.get('target') != required.get('target'):
            continue
        wanted = required.get('params', {})
        got = row.get('params', {})
        if all(key in got and _same_value(value, got[key]) for key, value in wanted.items()):
            return True
    return False


def _operation_label(operation):
    op = operation.get('op', 'operation')
    if op == 'addText':
        return 'addText（固定文字“' + str(operation.get('params', {}).get('text', '')) + '”）'
    if op == 'effects':
        return 'effects（画面效果）'
    return op


def verify(ledger, result):
    """Return a complete item report and reject every mismatch."""
    if not isinstance(ledger, RequirementLedger):
        ledger = RequirementLedger.build(ledger)
    plan = result.get('plan') if isinstance(result, dict) else None
    plan = _normalize_plan(plan)
    probe = result.get('probe') if isinstance(result, dict) else None
    report = []
    errors = []

    def add(key, label, expected, actual, ok):
        status = 'verified' if ok else 'failed'
        report.append({'key': key, 'label': label, 'expected': expected,
                       'actual': actual, 'status': status,
                       'source': 'accepted-plan'})
        if not ok:
            errors.append(label + '（' + key + '）')

    if not isinstance(plan, dict):
        add('plan', '最终剪辑计划', 'available', None, False)
        plan = {}

    labels = {
        'start': '开始位置', 'duration': '成片时长', 'minDuration': '最短时长',
        'minSpeed': '最低播放速度',
        'speed': '播放倍速', 'ratio': '画幅比例', 'resolution': '输出分辨率',
        'keepAudio': '保留原声', 'bgm': '背景音乐', 'bgmVolume': '背景音乐音量',
    }
    actual_settings = plan.get('settings', {})
    for key, expected in ledger.settings.items():
        actual = actual_settings.get(key)
        ok = _same_value(expected, actual)
        if key == 'duration' and plan.get('minimumSatisfied') is False and plan.get('minDurationPolicy') == 'slowdown':
            ok = actual is not None and _same_number(expected, actual, .08)
        add('settings.' + key, labels.get(key, key), expected, actual, ok)

    for key, expected in ledger.flags.items():
        actual = plan.get(key)
        add(key, {'subtitles': '口播字幕', 'visualCleanup': '异常画面检测',
                  'preserveFrames': '保留全部画面'}.get(key, key), expected, actual,
            _same_value(expected, actual))

    option_labels = {
        'bgmTrack': '背景音乐风格', 'subtitleStyle': '字幕样式',
        'transition': '转场', 'montageMode': '取材方式',
        'shotDuration': '单镜头最长时长', 'fitMode': '画面适配',
        'bgmDucking': '口播配乐避让',
    }
    plan_options = plan.get('options', {})
    if not isinstance(plan_options, dict):
        plan_options = {}
    for key, expected in ledger.options.items():
        actual = plan_options.get(key, plan.get(key))
        add('options.' + key, option_labels.get(key, key), expected, actual,
            _option_matches(key, expected, actual))

    requested_transition = ledger.options.get('transition')
    if isinstance(requested_transition, dict) and requested_transition.get('type') not in (None, 'none'):
        storyboard = plan.get('storyboard')
        layout = plan.get('transitions')
        joins = layout.get('joins') if isinstance(layout, dict) else None
        joins = joins if isinstance(joins, list) else []
        expected_join_count = max(0, len(storyboard) - 1) if isinstance(storyboard, list) else None
        every_join_is_smooth = (
            bool(joins)
            and (expected_join_count is None or len(joins) == expected_join_count)
            and all(
                isinstance(row, dict)
                and row.get('type') == requested_transition.get('type')
                and type(row.get('duration')) in (int, float)
                and math.isfinite(row['duration'])
                and row['duration'] > 0
                for row in joins
            )
        )
        # A one-piece film has no cut to soften. In every other case a
        # requested transition must survive short-piece normalization on all
        # retained joins; a single fallback to "none" would ship a hard cut.
        ok = expected_join_count == 0 or every_join_is_smooth
        add('output.transitionJoins', '全部剪辑连接处', requested_transition,
            [{'type': row.get('type'), 'duration': row.get('duration')}
             for row in joins if isinstance(row, dict)], ok)

    planned = plan.get('operations', [])
    for index, operation in enumerate(ledger.operations):
        add('operations.' + operation.get('op', 'unknown'),
            _operation_label(operation), operation, operation if _operation_present(operation, planned) else None,
            _operation_present(operation, planned))

    if ledger.flags.get('subtitles') is True:
        subtitles = result.get('subtitles')
        count = subtitles.get('count') if isinstance(subtitles, dict) else None
        add('subtitles', '实际烧录字幕', '至少1条字幕', count,
            type(count) is int and count > 0)

    if ledger.flags.get('visualCleanup') is True:
        analysis = result.get('analysis')
        add('visualCleanup', '实际画面分析', '已执行视觉分析',
            bool(analysis) if analysis is not None else None,
            isinstance(analysis, dict) and bool(analysis.get('analysisId') or analysis.get('ranges') is not None))

    expected_width, expected_height = plan.get('width'), plan.get('height')
    actual_width = result.get('width')
    actual_height = result.get('height')
    if isinstance(probe, dict):
        actual_width = probe.get('width', actual_width)
        actual_height = probe.get('height', actual_height)
    add('output.width', '实际画面宽度', expected_width, actual_width,
        type(expected_width) is int and actual_width == expected_width)
    add('output.height', '实际画面高度', expected_height, actual_height,
        type(expected_height) is int and actual_height == expected_height)
    expected_ratio = ledger.settings.get('ratio')
    if expected_ratio not in (None, '自动') and expected_width and expected_height:
        left, right = map(int, expected_ratio.split(':'))
        add('output.ratio', '实际画幅比例', expected_ratio,
            f'{actual_width}:{actual_height}' if actual_width and actual_height else None,
            actual_width * right == actual_height * left)

    if isinstance(probe, dict):
        expected_duration = plan.get('duration')
        actual_duration = probe.get('duration')
        duration_label = '实际成片时长'
        if (_same_number(expected_duration, actual_duration, 86400)
                and abs(float(expected_duration) - float(actual_duration)) > .08):
            duration_label = (f'实际成片时长（计划 {float(expected_duration):.2f} 秒，'
                              f'实际 {float(actual_duration):.2f} 秒）')
        add('output.duration', duration_label, expected_duration,
            actual_duration,
            _same_number(expected_duration, actual_duration, .08))
        # "Keep original audio" cannot create sound in silent footage. Derive
        # this exception only from the captured media probes of retained pieces;
        # absent/invalid evidence still requires audio rather than relaxing QA.
        source_audio = True
        inputs, storyboard = ledger.plan.get('inputs'), ledger.plan.get('storyboard')
        if isinstance(inputs, list) and inputs and isinstance(storyboard, list) and storyboard:
            selected = [row.get('index') for row in storyboard if isinstance(row, dict)]
            if (len(selected) == len(storyboard) and
                    all(type(index) is int and 0 <= index < len(inputs) and
                        isinstance(inputs[index], dict) and type(inputs[index].get('hasAudio')) is bool
                        for index in selected)):
                source_audio = any(inputs[index]['hasAudio'] for index in selected)
        expected_audio = ((ledger.settings.get('keepAudio') is True and source_audio)
                          or ledger.settings.get('bgm') is True)
        add('output.audio', '实际音轨', expected_audio, probe.get('hasAudio'),
            probe.get('hasAudio') is expected_audio)
    if ledger.flags.get('visualCleanup') is True:
        add('output.analysis', '实际画面分析', True,
            isinstance(result.get('analysis'), dict),
            isinstance(result.get('analysis'), dict))

    if errors:
        unique = list(dict.fromkeys(errors))
        raise ValueError('SMART_REQUIREMENT_NOT_DELIVERED|成片未完成明确要求：'
                         + '、'.join(unique) + '。本次结果未发布。')
    return report
