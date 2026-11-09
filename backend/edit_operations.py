"""Typed, source-bound tools available to the conversational editor.

Models choose indices and bounded values. Paths and renderer expressions are
always supplied by captured application records, never by model output.
"""
import copy
import math
import re


class EditOperationError(ValueError):
    pass


_OPS = {
    'transform': '位置、大小、旋转、翻转、透明度、适配与裁剪',
    'effects': '亮度、对比度、饱和度、色相、模糊、黑白、复古色调',
    'mask': '矩形、圆形、圆角遮罩与反向遮罩',
    'keyframes': '位置、缩放、旋转、透明度和音量的动画关键帧',
    'addText': '在指定成片时间添加标题或文字',
    'reverse': '倒放选中视频', 'freeze': '将视频末尾指定秒数定格',
    'audioFade': '原声音轨或配乐的淡入和淡出',
    'trim': '保留素材的指定源时间区间', 'removeRange': '删除素材的指定源时间区间',
    'reorder': '按素材序号重新排列', 'duplicate': '重复指定素材',
    'background': '设置画布背景颜色',
}
_RANGES = {
    'x':(-2,2),'y':(-2,2),'width':(.01,4),'height':(.01,4),
    'rotation':(-3600,3600),'opacity':(0,1),
    'brightness':(-1,1),'contrast':(0,4),'saturation':(0,4),'hue':(-180,180),'blur':(0,80),
    'scale':(.01,4),'volume':(0,4),
}
_EASING = ('linear','hold','ease-in','ease-out','ease-in-out')


def _fail(message):
    raise EditOperationError(message)


def _number(value, low, high, name):
    if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
        _fail(f'{name}必须为{low}至{high}之间的有限数值')
    return float(value)


def _bool(value, name):
    if type(value) is not bool: _fail(name+'必须为开关')
    return value


def _color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',value): _fail('颜色必须为#RRGGBB')
    return value.upper()


def _fields(params, allowed):
    if not isinstance(params,dict) or set(params)-set(allowed): _fail('操作参数包含未知字段')


def get_capabilities():
    parameters={
        'transform':{k:list(v) for k,v in _RANGES.items() if k in ('x','y','width','height','rotation','opacity')},
        'effects':{k:list(_RANGES[k]) for k in ('brightness','contrast','saturation','hue','blur')},
        'mask':{'type':['none','rect','circle','rounded'],'radius':[0,.5],'feather':[0,.5],'inverted':'boolean'},
        'keyframes':{'property':['x','y','scale','opacity','rotation','volume'],'points':'ordered [{time,value,easing}], maximum 32; local clip seconds'},
        'addText':{'text':'string','start':'output seconds','end':'output seconds','position':['top','center','bottom'],
            'size':[8,300],'color':'#RRGGBB','noWrap':'boolean'},
        'reverse':{'enabled':'boolean'},'freeze':{'duration':[.04,30]},
        'audioFade':{'fadeIn':[0,30],'fadeOut':[0,30]},
        'trim':{'start':'source seconds','end':'source seconds'},'removeRange':{'start':'source seconds','end':'source seconds'},
        'reorder':{'order':'permutation of original 0-based source indices'},
        'duplicate':{'count':'integer 2..10, total copies'},'background':{'color':'#RRGGBB'},
    }
    parameters['transform'].update(fit=['contain','cover','stretch'],flipX='boolean',flipY='boolean',crop='{x,y,width,height} normalized source coordinates')
    parameters['effects'].update(grayscale='boolean',sepia='boolean')
    return [{'op':op,'description':description,'targets':(['all'] if op in ('reorder','background','addText') else ['all','source index'])+(['music'] if op=='audioFade' else []),'parameters':parameters[op]} for op,description in _OPS.items()]


def validate_operations(operations, source_count=None):
    if not isinstance(operations,list) or len(operations)>100: _fail('最多支持100项剪辑操作')
    result=[]
    for item in operations:
        if not isinstance(item,dict) or set(item)-{'op','target','params'}: _fail('剪辑操作格式无效')
        op=item.get('op'); target=item.get('target','all'); p=item.get('params',{})
        if op not in _OPS: _fail('尚未接入此剪辑操作：'+str(op))
        if type(target) is int:
            if target<0 or (source_count is not None and target>=source_count): _fail('操作素材序号越界')
        elif not isinstance(target,str) or target not in (('all','music') if op=='audioFade' else ('all',)): _fail('操作目标无效')
        if op in ('background','addText','reorder') and target!='all':_fail('此操作使用成片时间，请将目标设为all')
        q={}
        if op in ('transform','effects'):
            names=('x','y','width','height','rotation','opacity','flipX','flipY','fit','crop') if op=='transform' else ('brightness','contrast','saturation','hue','blur','grayscale','sepia')
            _fields(p,names)
            for key,value in p.items():
                if key in _RANGES:q[key]=_number(value,*_RANGES[key],key)
                elif key in ('flipX','flipY','grayscale','sepia'):q[key]=_bool(value,key)
                elif key=='fit':
                    if value not in ('contain','cover','stretch'): _fail('画面适配方式无效')
                    q[key]=value
                else:
                    _fields(value,('x','y','width','height'))
                    crop={k:_number(value.get(k,0 if k in ('x','y') else 1),0 if k in ('x','y') else .001,1,'crop.'+k) for k in ('x','y','width','height')}
                    if crop['x']+crop['width']>1.000001 or crop['y']+crop['height']>1.000001:_fail('裁剪区域超过原画面')
                    q[key]=crop
        elif op=='mask':
            _fields(p,('type','radius','feather','inverted'))
            if p.get('type','none') not in ('none','rect','circle','rounded'):_fail('遮罩类型无效')
            q={'type':p.get('type','none')}
            for key in ('radius','feather'):
                if key in p:q[key]=_number(p[key],0,.5,key)
            if 'inverted' in p:q['inverted']=_bool(p['inverted'],'inverted')
        elif op=='keyframes':
            _fields(p,('property','points')); prop=p.get('property'); points=p.get('points')
            if prop not in ('x','y','scale','opacity','rotation','volume') or not isinstance(points,list) or not 1<=len(points)<=32:_fail('关键帧格式无效')
            q={'property':prop,'points':[]}; previous=-1
            for point in points:
                _fields(point,('time','value','easing')); time=_number(point.get('time'),0,86400,'关键帧时间')
                if time<=previous:_fail('关键帧时间必须递增且不能重复')
                easing=point.get('easing','linear')
                if isinstance(easing,dict):
                    _fields(easing,('type','x1','y1','x2','y2'))
                    if easing.get('type')!='bezier':_fail('关键帧曲线无效')
                    easing={'type':'bezier',**{key:_number(easing.get(key),0,1,'贝塞尔控制点') for key in ('x1','y1','x2','y2')}}
                elif easing not in _EASING:_fail('关键帧曲线无效')
                q['points'].append({'time':time,'value':_number(point.get('value'),*_RANGES[prop],prop),'easing':easing});previous=time
        elif op=='addText':
            _fields(p,('text','start','end','position','size','font','color','bold','italic','underline',
                'outline','outlineColor','shadow','background','align','noWrap'))
            if not isinstance(p.get('text'),str) or not 1<=len(p['text'].strip())<=4000:_fail('文字内容需为1至4000字')
            q={'text':p['text'],'start':_number(p.get('start',0),0,86400,'文字开始时间')}
            if 'end' in p:
                q['end']=_number(p['end'],0,86400,'文字结束时间')
                if q['end']<=q['start']:_fail('文字结束时间须晚于开始时间')
            for key in ('position','align'):
                if key in p:
                    if p[key] not in (('top','center','bottom') if key=='position' else ('left','center','right')):_fail('文字位置无效')
                    q[key]=p[key]
            for key in ('size','outline','shadow'):
                if key in p:q[key]=_number(p[key],8 if key=='size' else 0,300 if key=='size' else 20,key)
            for key in ('color','outlineColor','background'):
                if key in p:q[key]=_color(p[key])
            for key in ('bold','italic','underline','noWrap'):
                if key in p:q[key]=_bool(p[key],key)
            if 'font' in p:
                if not isinstance(p['font'],str) or not re.fullmatch(r'[\w \-\u4e00-\u9fff]{1,100}',p['font']):_fail('字体名称无效')
                q['font']=p['font']
        elif op=='reverse':
            _fields(p,('enabled',));q={'enabled':_bool(p.get('enabled',True),'倒放')}
        elif op=='freeze':
            _fields(p,('duration',));q={'duration':_number(p.get('duration',1),.04,30,'定格时长')}
        elif op=='audioFade':
            _fields(p,('fadeIn','fadeOut'));q={k:_number(v,0,30,k) for k,v in p.items()}
        elif op in ('trim','removeRange'):
            _fields(p,('start','end'));q={k:_number(p.get(k),0,86400,k) for k in ('start','end')}
            if q['end']<=q['start']:_fail('结束时间须晚于开始时间')
        elif op=='reorder':
            _fields(p,('order',));order=p.get('order')
            if target!='all' or not isinstance(order,list) or not order or any(type(x) is not int or x<0 for x in order) or len(order)!=len(set(order)):_fail('排序序号无效')
            if source_count is not None and sorted(order)!=list(range(source_count)):_fail('排序必须包含所有原始素材且不重复')
            q={'order':list(order)}
        elif op=='duplicate':
            _fields(p,('count',));count=p.get('count',2)
            if type(count) is not int or not 2<=count<=10:_fail('重复份数须为2至10')
            q={'count':count}
        elif op=='background':
            _fields(p,('color',));q={'color':_color(p.get('color'))}
        result.append({'op':op,'target':target,'params':q})
    return result


def prepare_sources(paths, infos, operations, removals):
    operations=validate_operations(operations,len(paths));order=list(range(len(paths)));ranges=copy.deepcopy(removals)
    for item in operations:
        op,target,p=item['op'],item['target'],item['params'];targets=range(len(paths)) if target=='all' else [target]
        if op=='reorder':order=p['order'][:]
        elif op=='duplicate':order=[i for i in order for _ in range(p['count'] if i in targets else 1)]
        elif op in ('trim','removeRange'):
            for index in targets:
                duration=float(infos[index]['duration'])
                if p['end']>duration+.02:_fail('裁剪时间超过素材时长')
                if op=='removeRange':ranges.append({'index':index,**p})
                else:
                    if p['start']>0:ranges.append({'index':index,'start':0.,'end':p['start']})
                    if p['end']<duration:ranges.append({'index':index,'start':p['end'],'end':duration})
    if len(order)>50:_fail('重复后的素材不能超过50段')
    mapped=[]
    for new,index in enumerate(order):
        for row in ranges:
            if row.get('index')==index:mapped.append({'index':new,'start':float(row['start']),'end':float(row['end'])})
    return [paths[i] for i in order],order,mapped


def build_document(record, operations, output, original_indices=None):
    sources=record['sources'];plan=record['plan'];indices=original_indices or list(range(len(sources)))
    operations=validate_operations(operations,max(indices)+1 if indices else 0)
    speed=plan.get('speed',1);duration=plan['duration'];layers=[];clock=0.
    layout=plan.get('transitions',{});starts=layout.get('starts',[]);joins=layout.get('joins',[])
    repairs=plan.get('spatialCrops') or []
    if not isinstance(repairs,list):_fail('局部画面裁剪参数无效')
    for repair in repairs:
        if (not isinstance(repair,dict)
                or not {'index','start','end','crop'} <= set(repair)):
            _fail('局部画面裁剪参数无效')
        if type(repair['index']) is not int or repair['index']<0:
            _fail('局部画面裁剪缺少有效视频序号')
        start=repair['start'];end=repair['end'];crop=repair['crop']
        if (type(start) not in (int,float) or type(end) not in (int,float)
                or not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start):
            _fail('局部画面裁剪时间范围无效')
        if not isinstance(crop,dict) or set(crop)!={'x','y','width','height'}:
            _fail('局部画面裁剪范围无效')
        if not all(type(crop[key]) in (int,float) and math.isfinite(crop[key])
                   and (0<=crop[key]<=1 if key in ('x','y') else 0<crop[key]<=1)
                   for key in crop) or crop['x']+crop['width']>1.000001 or crop['y']+crop['height']>1.000001:
            _fail('局部画面裁剪范围超出素材')
        if not any(piece[-3]==repair['index']
                   and float(piece[-2])<=start+.000001
                   and float(piece[-2])+float(piece[-1])>=end-.000001
                   for piece in record['pieces']):
            _fail('局部画面裁剪未被拆分到独立时间片段')
    for number,piece in enumerate(record['pieces']):
        # Stored smart plans normally include segment number before source index.
        index,start,length=piece[-3:]
        transform={'fit':plan.get('fitMode','contain')}
        selected=[row for row in repairs if row['index']==index
                  and row['start']>=start-.000001 and row['end']<=start+length+.000001]
        if selected:
            first=selected[0]['crop']
            if any(row['crop']!=first for row in selected[1:]):
                _fail('同一剪辑片段内包含不同画面裁剪范围，无法安全合成')
            transform['crop']=copy.deepcopy(first)
        layer={'id':f'source-{number}','type':'video','path':str(sources[index]),'start':starts[number] if number<len(starts) else clock,
            'duration':length/speed,'track':0,'trimStart':start,'trimEnd':start+length,'speed':speed,
            # Speech recognition still needs narration when the final video is
            # muted. The final smart renderer removes it after transcription.
            'volume':1 if plan.get('keepAudio',True) or plan.get('subtitles') else 0,'transform':transform,'effects':{},'mask':{'type':'none'},'keyframes':{}}
        layer['duration']=min(layer['duration'],max(0,duration-layer['start']))
        if layer['duration']<=0:continue
        if number<len(joins) and joins[number].get('type') not in ('none',None):layer['transitionToNext']={k:joins[number][k] for k in ('type','duration')}
        for item in operations:
            op,target,p=item['op'],item['target'],item['params']
            if target not in ('all',indices[index]):continue
            if op in ('transform','effects','mask'):layer[op].update(copy.deepcopy(p))
            elif op=='keyframes':layer['keyframes'][p['property']]=copy.deepcopy(p['points'])
            elif op=='reverse':layer['reverse']=p['enabled']
            elif op=='audioFade':layer.update(p)
        freeze=next((x['params']['duration'] for x in reversed(operations) if x['op']=='freeze' and x['target'] in ('all',indices[index])),0)
        if freeze:
            layer['freezeTail']=min(freeze,layer['duration'])
            layers.append(layer)
        else:layers.append(layer)
        clock=layer['start']+length/speed
    background='#000000'
    for item in operations:
        p=item['params']
        if item['op']=='background':background=p['color']
        elif item['op']=='addText':
            end=min(duration,p.get('end',duration));start=min(duration,p.get('start',0))
            if end<=start:_fail('文字时间位于成片范围之外')
            style={k:v for k,v in p.items() if k not in ('text','start','end','position')}
            y={'top':.08,'center':.43,'bottom':.8}[p.get('position','bottom')]
            layers.append({'id':f'text-{len(layers)}','type':'text','text':p['text'],'start':start,'duration':end-start,'track':100,
                'transform':{'x':.05,'y':y,'width':.9,'height':.15},'style':style})
    return {'documentVersion':2,'duration':duration,'width':plan['width'],'height':plan['height'],'fps':plan.get('fps',30),
        'background':background,'layers':layers,'audioClips':[],'format':'mp4','quality':'high','output':str(output)}
