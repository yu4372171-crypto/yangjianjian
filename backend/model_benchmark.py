"""A small, explicit inference probe; never call capacity estimates a benchmark."""
import json
import os
from pathlib import Path
import tempfile
import time
from datetime import datetime


def run(load, kind, control, progress):
    scheduler=load('ai_scheduler')
    route=scheduler.freeze_route(kind)
    if not route['ready']:
        raise RuntimeError(route['message'])
    start=time.monotonic()
    with scheduler.job_budget(2):
        progress(10,'正在加载当前模型并进行一次真实推理')
        if kind=='language':
            schema={'type':'object','properties':{'seconds':{'type':'integer'},'subtitles':{'type':'boolean'}},
                    'required':['seconds','subtitles'],'additionalProperties':False}
            messages=[{'role':'system','content':'按用户要求返回 JSON：seconds 是秒数，subtitles 表示是否添加字幕。'},
                      {'role':'user','content':'剪成15秒并添加口播字幕'}]
            answer,execution=scheduler.run_language(messages,schema,control=control,route=route,
                local_call=lambda identifier:load('language_models').complete_json(
                    messages,schema,identifier,control,progress))
            valid=answer=={'seconds':15,'subtitles':True}
        elif kind=='vision':
            from PIL import Image,ImageDraw
            root=Path(os.environ.get('AIVE_API_STATE_ROOT',Path(__file__).parent/'runtime'))
            root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='model-probe-',dir=root) as folder:
                image=Image.new('RGB',(256,256),'white')
                ImageDraw.Draw(image).rectangle((40,40,216,216),fill='red')
                path=Path(folder)/'sample.png'
                image.save(path)
                frames=[{'path':str(path),'time':0.}]
                prompt='这是一张正常静态图形。只检查明显人体穿模，正常图形返回 {"ranges":[]}。'
                answer,execution=scheduler.run_vision(frames,prompt,load('local_vision')._frame_schema(1),
                    control=control,route=route,local_call=lambda identifier:load('local_vision').analyze_frames(
                        frames,prompt,identifier,control,progress))
                valid=answer=={'ranges':[]}
        else:
            raise ValueError('请选择语言或视觉模型')
        usage=scheduler.budget_usage()
    result={'kind':kind,'success':valid,'elapsedSeconds':round(time.monotonic()-start,2),
            'execution':execution,'apiUsage':usage,'created':datetime.now().isoformat(timespec='seconds'),
            'message':'小样例推理通过' if valid else '模型已响应，但小样例结果未通过',
            'note':'包含首次加载时间；仅代表此样例，不代表长视频质量或固定处理速度。'}
    root=Path(os.environ.get('AIVE_API_STATE_ROOT',Path(__file__).parent/'runtime'))/'model_benchmarks'
    root.mkdir(parents=True,exist_ok=True)
    path=root/(kind+'.json')
    temporary=path.with_suffix('.partial')
    temporary.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
    os.replace(temporary,path)
    return result
