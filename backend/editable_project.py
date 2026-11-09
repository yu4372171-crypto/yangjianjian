"""Build a source-based timeline alongside an automatically rendered movie."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid


def _operations():
    name='_aive_edit_operations'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name('edit_operations.py'))
        value=importlib.util.module_from_spec(spec)
        sys.modules[name]=value
        spec.loader.exec_module(value)
    return sys.modules[name]


def save(record, result, operations, indices):
    output=Path(result['path']).resolve()
    document=_operations().build_document(record,operations,output,indices)
    plan=record['plan']
    draft={'version':3,'assets':[],'clips':[],'overlays':[],'texts':[],
           'audioAssets':[],'audioClips':[],'tracks':[
               {'id':'main','name':'原始视频','type':'video','order':0},
               {'id':'titles','name':'标题文字','type':'text','order':1},
               {'id':'captions','name':'口播字幕','type':'subtitle','order':2}],
           'markers':[],'music':None,
           'settings':{'ratio':plan.get('ratio','自动'),'resolution':plan.get('resolution','原画'),
                       'fps':min((24,25,30,50,60),key=lambda n:abs(n-plan.get('fps',30))),
                       'background':document['background']},
           'output':{'folder':str(output.parent),'filename':'精修成片.mp4','format':'mp4','quality':'high','audio':True}}
    paths={}
    for index,source in enumerate(record['sources']):
        path=str(source)
        if path in paths:
            continue
        info=record['infos'][index]
        identifier='asset_'+str(index)
        paths[path]=identifier
        draft['assets'].append({'id':identifier,'path':path,'name':Path(path).name,
            **{key:info[key] for key in ('duration','width','height','hasAudio')}})
    warnings=[]
    for layer in document['layers']:
        if layer['type']=='text':
            style=layer.get('style',{})
            draft['texts'].append({'id':layer['id'],'text':layer['text'],
                'start':layer['start'],'end':layer['start']+layer['duration'],
                'trackId':'titles','font':style.get('font','Microsoft YaHei'),
                'size':style.get('size',48),'color':style.get('color','#FFFFFF'),
                'transform':copy.deepcopy(layer['transform']),
                'style':{'bold':style.get('bold',False),'italic':style.get('italic',False),
                         'underline':style.get('underline',False),'align':style.get('align','center'),
                         'noWrap':style.get('noWrap',False),
                         'borderWidth':style.get('outline',2),'borderColor':style.get('outlineColor','#141414'),
                         'shadowBlur':style.get('shadow',1)}})
        else:
            clip={key:copy.deepcopy(value) for key,value in layer.items()
                  if key not in ('path','type','track')}
            clip.update(assetId=paths[layer['path']],trackId='main')
            if clip.get('transform',{}).get('fit')=='blur':
                clip['transform']['fit']='contain'
                warnings.append('模糊背景暂转为完整画面预览，请在精修后检查背景。')
            if not plan.get('keepAudio',True):
                clip['volume']=0
            draft['clips'].append(clip)
    subtitles=result.get('subtitles') or {}
    style=subtitles.get('style',{})
    for index,row in enumerate(subtitles.get('segments',[])):
        draft['texts'].append({'id':f'caption_{index}','trackId':'captions',
            'text':row['text'],'start':row['start'],'end':row['end'],
            'font':style.get('font','Microsoft YaHei'),'size':style.get('size') or max(16,min(90,round(plan['height']*.052))),
            'color':style.get('color','#FFFFFF'),'position':style.get('position','bottom'),
            'style':{'bold':style.get('bold',False),'borderWidth':style.get('outline',2),
                     'borderColor':style.get('outlineColor','#141414'),'shadowBlur':style.get('shadow',1)}})
    visual_layer_count=len(draft['clips'])+len(draft['overlays'])+len(draft['texts'])
    if visual_layer_count>200:
        raise ValueError(f'智能剪辑工程包含 {visual_layer_count} 个视觉图层；最多支持 200 个，请缩短字幕覆盖范围后重试')
    if record.get('bgmSource') and plan.get('bgm'):
        fades=plan.get('musicFades',{})
        duration=plan['duration']
        draft['music']={'path':str(record['bgmSource']),'trackId':plan.get('bgmTrack',''),
                        'volume':plan.get('bgmVolume',.18),'loop':True,
                        'fadeIn':min(float(fades.get('fadeIn',min(.8,duration/3))),duration),
                        'fadeOut':min(float(fades.get('fadeOut',min(.8,duration/3))),duration),
                        'ducking':bool(plan.get('bgmDucking',False))}
    finishing=[{key:copy.deepcopy(row[key]) for key in
        ('id','start','end','opacity','scale','position','chromaKey','keyColor','lutStrength') if key in row}
        for row in record.get('effects',[])]
    if finishing:
        draft['smartFinishing']={'effects':finishing}
        warnings.append('自定义特效保留在后期效果中，精修导出时重新应用。')
    if style.get('preset') not in (None,'classic','yellow','boxed'):
        warnings.append('字幕已拆成可编辑文字，动态字幕效果请在精修预览中确认。')
    for i,row in enumerate((result.get('qualityReport') or {}).get('checks',[])):
        if row['status']!='passed':
            draft['markers'].append({'id':f'quality_{i}','time':row.get('start',0),
                'label':row['label'],'note':row['message'],'color':'#ffb547'})
    project={'schema':1,'requirements':plan.get('requirements',''),'referenceOutput':str(output),
             'draft':draft,'warnings':list(dict.fromkeys(warnings)),
             'sourceStamps':[[str(p),p.stat().st_size,p.stat().st_mtime_ns] for p in map(Path,paths)]}
    target=output.parent/'editable-project.json'
    temporary=target.with_name(uuid.uuid4().hex+'.partial')
    try:
        with temporary.open('x',encoding='utf8') as stream:
            json.dump(project,stream,ensure_ascii=False,allow_nan=False)
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)
