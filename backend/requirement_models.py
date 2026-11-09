"""Requirement selection and RPC compatibility for independent text models."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import threading

_lock = threading.RLock()
_MODEL_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,79}$')
_DEFAULT_KEYS = ('start', 'duration', 'minDuration', 'minSpeed', 'speed', 'ratio', 'resolution',
                 'keepAudio', 'bgm', 'bgmVolume', 'totalDuration')


def _load(name):
    identifier = '_aive_' + name
    path = Path(__file__).resolve().with_name(name + '.py')
    module = sys.modules.get(identifier)
    if module is None:
        ordinary = sys.modules.get(name)
        if ordinary is not None and Path(getattr(ordinary, '__file__', '')).resolve() == path:
            module = ordinary
            sys.modules[identifier] = module
        else:
            spec = importlib.util.spec_from_file_location(identifier, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[identifier] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(identifier, None)
                raise
    return module


def _error(message):
    raise _load('local_vision').LocalVisionError('SMART_REQUIREMENT_MODEL', message)


def validate_model_id(value):
    if value == '':
        return None
    if value is not None and (not isinstance(value, str) or not _MODEL_ID.fullmatch(value)):
        _error('请选择已安装的本地需求模型')
    return value


def get_status():
    engine = _load('local_vision')
    status = engine.get_status()
    models = []
    for model in status['models']:
        row = dict(model)
        try:
            metadata = json.loads((engine.ROOT / 'models' / model['id'] / 'manifest.json').read_text('utf-8'))
            row.update(repoId=str(metadata.get('repoId') or '')[:200],
                       license=str(metadata.get('license') or '请查看模型许可证')[:200])
        except (OSError, ValueError, TypeError, AttributeError):
            row.update(repoId='', license='请查看模型许可证')
        models.append(row)
    try:
        saved = json.loads((engine.ROOT / 'requirement_settings.json').read_text('utf-8'))['modelId']
    except (OSError, ValueError, TypeError, KeyError):
        saved = None
    language = _load('language_models').get_status()
    text_models = [dict(row) for row in language['models'] if row.get('installed')]
    models = text_models + models
    installed = {row['id'] for row in models}
    # A stable default does not follow subsequent changes to the visual model.
    selected = saved if isinstance(saved, str) and saved in installed | {'rules'} else (
        language['selectedModel'] if language['selectedModel'] in installed else
        'qwen3-vl-2b-q8' if 'qwen3-vl-2b-q8' in installed else (models[0]['id'] if models else None))
    scheduler = _load('ai_scheduler').get_scheduler_status('language')
    if scheduler['apiReady']:
        connection = scheduler['connection']
        models += [
            {'id': 'text-api', 'name': 'API · ' + connection['name'] + ' / ' + scheduler['model'],
             'installed': False, 'source': 'api', 'ready': True}]
    if scheduler['apiReady'] or scheduler['localReady'] or scheduler['mode'] == 'auto':
        label = (scheduler['connection'] or {}).get('name', 'API')
        models.append({'id': 'text-auto', 'name': '自动 · ' + label + ' → 本地',
                       'installed': False, 'source': 'auto',
                       'ready': scheduler['apiReady'] or scheduler['localReady']})
    if scheduler['mode'] in ('api', 'auto'):
        selected = 'text-' + scheduler['mode']
    selected_text = isinstance(selected, str) and selected.startswith('text-')
    result = {'mode': scheduler['mode'], 'models': models, 'selectedModel': selected,
            'ready': selected == 'rules' or (language['ready'] if selected_text else bool(models and status['ready'])),
            'engine': language['engine'] if selected_text else status['engine'],
            'runningModel': language.get('runningModel') if selected_text else status.get('runningModel'),
            'message': '语言模型独立理解完整多轮需求；画面检测模型可分别选择' if selected_text else
                       '使用已安装的本地模型理解需求；需求模型与画面检测模型可分别选择' if models
                       else '请先在语言模型库下载模型；明确的基础剪辑要求仍可直接执行',
            'supported': ['按顺序拼接、截取和时长', '播放速度、画幅比例和分辨率',
                          '口播同步字幕及内置字幕样式', '内置配乐风格与音量',
                          '原声开关', '穿模和明显画面异常删减', '片段间淡入淡出、叠化、擦除和滑动转场'],
            'limits': ['仅执行已有剪辑能力，不执行模型生成的命令或滤镜',
                       '换人物、修复画面、任意转场和指定歌曲等未支持要求会明确列出']}
    result['scheduler'] = scheduler
    if selected in ('text-api', 'text-auto'):
        result.update(ready=scheduler['ready'], engine='customer-api', message=scheduler['message'])
    return result


def resolve_model_id(model_id=None):
    model_id = validate_model_id(model_id)
    status = get_status()
    selected = model_id if model_id is not None else status['selectedModel']
    if selected not in {row['id'] for row in status['models']} | {'rules'}:
        _error('所选需求模型尚未安装，请在本地模型库下载，或改用明确的基础剪辑要求')
    return selected


def set_selected_model(model_id):
    if model_id is None or model_id == '':
        _error('请选择已安装的本地需求模型')
    selected = resolve_model_id(model_id)
    if selected in ('text-api', 'text-auto'):
        current = _load('ai_scheduler').get_scheduler_status('language')
        _load('ai_scheduler').select_scheduler('language', selected.removeprefix('text-'),
            current['connectionId'], model=current['model'])
    else:
        _load('ai_scheduler').select_scheduler('language', 'local',
            local_model_id=selected if selected.startswith('text-') else None)
    if selected.startswith('text-') and selected not in ('text-api', 'text-auto'):
        _load('language_models').configure({'modelId': selected})
    engine = _load('local_vision')
    with _lock:
        engine.ROOT.mkdir(parents=True, exist_ok=True)
        target = engine.ROOT / 'requirement_settings.json'
        temporary = target.with_suffix('.json.partial')
        if target.is_symlink() or temporary.is_symlink():
            _error('需求模型设置保存路径无效')
        temporary.write_text(json.dumps({'modelId': selected}) + '\n', encoding='utf-8')
        os.replace(temporary, target)
    return get_status()


def _bridge(call):
    try:
        return call()
    except RuntimeError as error:
        from app.ui2.common import BridgeError
        raise BridgeError(getattr(error, 'code', 'SMART_REQUIREMENT_MODEL'),
                          getattr(error, 'message', str(error))) from error


class RequirementModelsMixin:
    def video_requirementModels(self, data):
        return _bridge(get_status)

    def video_requirementSettings(self, data):
        return _bridge(lambda: set_selected_model(data.get('modelId')))

    def video_requirementPlan(self, data):
        def understand():
            if not isinstance(data, dict):
                _error('需求预览参数无效')
            chosen = validate_model_id(data.get('requirementModelId')) or get_status()['selectedModel']
            if isinstance(chosen, str) and chosen.startswith('text-'):
                request = dict(data, requirementModelId=chosen)
                request.setdefault('defaults', {key: data[key] for key in _DEFAULT_KEYS if key in data})
                reply = _load('dialogue_planner').chat(request)
                if reply['status'] != 'ready':
                    return {'status': reply['status'], 'assistant': reply['assistant'], 'questions': reply['questions'],
                        'unsupported': reply['unsupported'], 'plan': reply['plan'], 'modelId': chosen,
                        'settings': (reply['plan'] or {}).get('settings', {}), 'summary': [reply['assistant']],
                        'interpreter': 'dialogue'}
                intent = _load('dialogue_planner').plan_to_intent(reply['plan'])
                return dict(intent, status='ready', assistant=reply['assistant'], questions=[], modelId=chosen,
                    modelName=next((row['name'] for row in get_status()['models'] if row['id'] == chosen), chosen))
            return _load('smart_intent').interpret_requirements(data.get('text'),
                {key: data[key] for key in _DEFAULT_KEYS if key in data},
                model_id=data.get('requirementModelId'))
        return _bridge(understand)

    def video_requirementChat(self, data):
        return _bridge(lambda: _load('dialogue_planner').chat(data))

    def video_requirementPrepare(self, data):
        if not isinstance(data, dict):
            _error('需求对话参数无效')
        request = dict(data)
        def work(progress, control):
            def report(value, message=''):
                if isinstance(value, str):
                    progress(0, value)
                else:
                    progress(value, message)
            return _bridge(lambda: _load('dialogue_planner').chat(
                request, control=control, progress=report))
        return self.api.tasks.start('理解剪辑需求', work, category='model',
            location={'route': '/editor/smart'})

    def video_languageModels(self, data):
        return _bridge(lambda: dict(_load('language_models').get_status(),
            scheduler=_load('ai_scheduler').get_scheduler_status('language')))

    def video_languageCatalog(self, data):
        return _bridge(lambda: _load('language_models').get_catalog())

    def video_languageInstall(self, data):
        model_id = data.get('modelId') or data.get('variantId')
        module = _load('language_models')
        _bridge(lambda: module._variant(model_id))
        def work(progress, control):
            return _bridge(lambda: module.install(model_id, progress, control))
        return self.api.tasks.start('下载语言模型：' + str(model_id), work, category='model',
            location={'route': '/editor/smart'})

    def video_languageRemove(self, data):
        return _bridge(lambda: _load('language_models').remove(data.get('modelId')))

    def video_languageSettings(self, data):
        def configure():
            result = _load('language_models').configure(data)
            # Selecting a language model updates only the requirement choice;
            # the visual model's selected_model.json is never touched.
            set_selected_model(result['selectedModel'])
            return result
        return _bridge(configure)

    def video_languageTest(self, data):
        return _bridge(lambda: _load('language_models').test_model(data.get('modelId')))
