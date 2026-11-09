"""Reapply imported custom effects after an editable timeline is rendered."""
import copy
from pathlib import Path
import shutil

from app.ui2.common import BridgeError
from app.workers.control import check_control


def start_export(actions,data):
    helpers=actions._smart_helpers
    finishing=data.get('smartFinishing')
    if not isinstance(finishing,dict) or set(finishing)!={'effects'} or not isinstance(finishing['effects'],list):
        raise BridgeError('TIMELINE_INVALID','后期效果参数无效')
    if data.get('format','mp4')!='mp4':
        raise BridgeError('TIMELINE_INVALID','带自定义后期效果的精修工程请导出 MP4')
    payload=copy.deepcopy(data)
    payload.pop('smartFinishing')
    compositor=helpers['_load_editor_extension']('timeline_compositor')
    validated=compositor.validate_document(payload,actions.api.ctx.ffmpeg_tool(),helpers)
    target=validated['output']
    identity=actions._smart_project()
    companion=helpers['_load_editor_extension']('smart_editing')
    effects=helpers['_load_editor_extension']('editor_assets')
    # Validate supplied effect IDs and settings before queueing.
    effect_records=effects.prepare_effects(finishing['effects'],validated['duration'])

    def work(progress,control):
        if actions._smart_project()!=identity:
            raise BridgeError('TIMELINE_CHANGED','项目已切换，请重新导出')
        effects.validate_effects(effect_records)
        with companion._scratch_directory(target.parent,target.parent) as scratch:
            intermediate=scratch/'timeline.mp4'
            document={**payload,'output':str(intermediate)}
            render,_=compositor.make_work(actions,document)
            render(lambda p,m='':progress(p*.7,m),control)
            check_control(control)
            planned=actions.video_smartPlan({'paths':[str(intermediate)],'text':'顺序拼接',
                'keepAudio':bool(validated['audioClips']) or any(row.get('volume',0)>0 for row in validated['layers']),
                'bgm':False,'subtitles':False,'effects':finishing['effects'],
                'transition':{'type':'none','duration':0},'ratio':'自动','resolution':'原画'})
            record=actions._smart_plans[planned['planId']]
            finished=actions._smart_execute_record(record,lambda p,m='':progress(70+p*.27,m),control)
            generated=Path(finished['path'])
            owner=companion._owned_directory(generated.parent,identity[1])
            try:
                stage=scratch/'finished.mp4'
                shutil.copyfile(generated,stage)
                check_control(control)
                if actions._smart_project()!=identity:
                    raise BridgeError('TIMELINE_CHANGED','项目已切换，未发布成片')
                helpers['_commit'](stage,target,progress,control)
                return {**finished,'path':str(target)}
            finally:
                companion._cleanup_owned(generated.parent,owner,identity[1])
    return actions.api.tasks.start('精修工程与后期效果导出',work,category='video',location={'route':'/video-tools'})
