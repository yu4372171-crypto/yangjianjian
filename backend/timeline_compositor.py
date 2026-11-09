"""Version 2 local timeline compositor.

The document is data, never an FFmpeg program. Only bounded, whitelisted
properties below produce filter expressions. Workers own their temporary
directory and recheck every input identity before publishing atomically.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

from app.ui2.common import BridgeError
from app.workers.control import check_control


def _error(message, code='TIMELINE_INVALID'):
    raise BridgeError(code, message)


def _number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        _error(f'{name}需要在 {low:g}–{high:g} 之间的有限数字')
    return float(value)


def _integer(value, name, low, high):
    number = _number(value, name, low, high)
    if int(number) != number:
        _error(f'{name}需要使用整数')
    return int(number)


def _boolean(value, name):
    if type(value) is not bool:
        _error(f'{name}需要使用布尔值')
    return value


def _object(value, fields, name):
    if not isinstance(value, dict) or set(value) - set(fields):
        _error(f'{name}包含不支持的字段')
    return value


def _choice(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        _error(f'{name}无效')
    return value


def _easing(value):
    if isinstance(value, str):
        return _choice(value, {'linear','hold','ease-in','ease-out','ease-in-out'}, '关键帧曲线')
    row = _object(value, {'type','x1','y1','x2','y2'}, '关键帧曲线')
    if row.get('type') != 'bezier':
        _error('关键帧曲线无效')
    return dict(type='bezier', **{
        key: _number(row.get(key), '贝塞尔控制点', 0, 1)
        for key in ('x1','y1','x2','y2')
    })


def _color(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        _error(f'{name}需要使用 #RRGGBB 格式')
    return value.upper()


def _identity(path, directory=False):
    try:
        if path.resolve() != path or (not path.is_dir() if directory else not path.is_file()):
            raise OSError('changed path')
        stat = path.stat()
        return (stat.st_dev, stat.st_ino) if directory else (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    except (OSError, RuntimeError, ValueError):
        _error('素材或输出目录已变化，请重新选择后导出', 'TIMELINE_CHANGED')


def _image_info(tool, source, helpers):
    if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.gif', '.avif'}:
        _error('请选择支持的本地图片文件')
    try:
        raw = helpers['_capture']([tool.ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-show_streams', '-of', 'json', source])
        streams = json.loads(raw)['streams']
        stream = next(row for row in streams if row.get('codec_type') == 'video')
        width = _integer(stream['width'], '图片宽度', 1, 32768)
        height = _integer(stream['height'], '图片高度', 1, 32768)
        if width * height > 100_000_000:
            _error('图片像素过大，请缩小后导入')
        return dict(path=str(source), name=source.name, width=width, height=height,
            duration=5., fps=30, hasAudio=False, kind='image', _videoStream=int(stream['index']))
    except (KeyError, TypeError, ValueError, StopIteration):
        _error('图片无法读取，请确认文件完整', 'TIMELINE_IMAGE_INVALID')


def image_probe(data, tool, helpers):
    _object(data, {'path'}, '图片探测参数')
    source = helpers['_local_path'](data.get('path'), existing=True)
    identity = _identity(source)
    info = _image_info(tool, source, helpers)
    factor = min(1., 640 / max(info['width'], info['height']))
    png = helpers['_capture']([tool.ffmpeg, '-hide_banner', '-loglevel', 'error', '-protocol_whitelist', 'file,pipe',
        '-i', source, '-map', f"0:{info['_videoStream']}", '-frames:v', '1', '-vf',
        f"scale={max(1,round(info['width']*factor))}:{max(1,round(info['height']*factor))},setsar=1,format=rgba",
        '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'])
    if not png or len(png) > 4_000_000:
        _error('无法生成图片预览', 'VIDEO_PREVIEW_FAILED')
    if _identity(source) != identity:
        _error('图片素材正在变化，请重新导入', 'TIMELINE_CHANGED')
    return dict({key: value for key, value in info.items() if not key.startswith('_')},
        preview='data:image/png;base64,' + base64.b64encode(png).decode('ascii'))


def _style(raw):
    row = _object(raw, {'size','fontSize','font','fontFamily','color','bold','italic','underline','align',
        'outline','outlineWidth','outlineColor','borderWidth','borderColor','shadow','shadowBlur','shadowColor',
        'background','backgroundColor','backgroundOpacity','letterSpacing','noWrap'}, '文字样式')
    font = row.get('font', row.get('fontFamily', 'Microsoft YaHei'))
    if not isinstance(font, str) or not font.strip() or len(font) > 80 or re.search(r'[\x00-\x1f\x7f,{}\\]', font):
        _error('文字字体名称无效')
    background = row.get('backgroundColor', row.get('background', None))
    if background in ('transparent', '', None):
        background = None
    else:
        background = _color(background, '文字背景颜色')
    return dict(font=font.strip(), size=_number(row.get('size', row.get('fontSize', 48)), '字号', 4, 600),
        color=_color(row.get('color', '#FFFFFF'), '文字颜色'),
        bold=_boolean(row.get('bold', False), '粗体'), italic=_boolean(row.get('italic', False), '斜体'),
        underline=_boolean(row.get('underline', False), '下划线'),
        align=_choice(row.get('align', 'center'), {'left','center','right'}, '文字对齐'),
        outline=_number(row.get('outline', row.get('outlineWidth', row.get('borderWidth', 0))), '文字描边', 0, 30),
        outlineColor=_color(row.get('outlineColor', row.get('borderColor', '#000000')), '描边颜色'),
        shadow=_number(row.get('shadow', row.get('shadowBlur', 0)), '文字阴影', 0, 30),
        shadowColor=_color(row.get('shadowColor', '#000000'), '阴影颜色'), background=background,
        backgroundOpacity=_number(row.get('backgroundOpacity', 1), '文字背景透明度', 0, 1),
        letterSpacing=_number(row.get('letterSpacing', 0), '字间距', -10, 40),
        noWrap=_boolean(row.get('noWrap', False), '禁止文字换行'))


def _keyframes(raw, duration, allowed=None):
    fields = {'x','y','scale','opacity','rotation','volume'} if allowed is None else set(allowed)
    keys = _object(raw,fields,'关键帧')
    result = {}
    for key,points in keys.items():
        if not isinstance(points,list) or len(points)>200:
            _error('每个属性最多支持 200 个关键帧')
        previous,normalized = -1.,[]
        low,high = {'x':(-4,4),'y':(-4,4),'scale':(.01,8),'opacity':(0,1),'rotation':(-3600,3600),'volume':(0,4)}[key]
        for point in points:
            _object(point,{'time','value','easing'},'关键帧')
            time = _number(point.get('time'),'关键帧时间',0,duration)
            if time<=previous:
                _error('关键帧时间需要严格递增')
            previous=time
            normalized.append(dict(time=time,value=_number(point.get('value'),'关键帧数值',low,high),
                easing=_easing(point.get('easing','linear'))))
        result[key]=normalized
    return result


def validate_document(data, tool, helpers):
    """Return a detached normalized document; do all expensive probing before a task starts."""
    _object(data, {'documentVersion','duration','width','height','fps','background','layers','audioClips','format','quality','output'}, '时间线文档')
    if type(data.get('documentVersion')) is not int or data['documentVersion'] not in {2,3}:
        _error('时间线文档版本无效')
    duration = _number(data.get('duration'), '时间线时长', .05, 86400)
    width = _integer(data.get('width'), '画布宽度', 16, 7680)
    height = _integer(data.get('height'), '画布高度', 16, 7680)
    if width % 2 or height % 2 or width * height > 33_177_600:
        _error('导出宽高需要使用偶数，且不能超过 8K 像素数量')
    doc = dict(documentVersion=3, duration=duration, width=width, height=height,
        fps=_number(data.get('fps', 30), '帧率', 1, 120), background=_color(data.get('background','#000000'), '画布背景'),
        format=_choice(data.get('format', 'mp4'), {'mp4','webm'}, '输出格式'),
        quality=_choice(data.get('quality', 'high'), {'high','medium','low'}, '导出质量'))
    layers, audio = data.get('layers', []), data.get('audioClips', [])
    if not isinstance(layers, list) or len(layers) > 200 or not isinstance(audio, list) or len(audio) > 50:
        _error('时间线最多支持 200 个视觉图层和 50 个音频片段')
    sources, cache = {}, {}
    timeline = helpers['_load_editor_extension']('timeline_editing')
    transitions = helpers['_load_editor_extension']('transitions')

    def source_info(raw, kind):
        source = helpers['_local_path'](raw, existing=True)
        identity = _identity(source)
        if source in sources and sources[source] != identity:
            _error('素材正在变化，请保存完成后导出', 'TIMELINE_CHANGED')
        sources[source] = identity
        if (source,kind) not in cache:
            cache[source,kind] = (_image_info(tool, source, helpers) if kind == 'image' else
                timeline._probe_audio(tool, source, helpers) if kind == 'audio' else helpers['_probe'](tool, source))
        if _identity(source) != identity:
            _error('素材正在变化，请保存完成后导出', 'TIMELINE_CHANGED')
        return source, dict(cache[source,kind])

    def timing(row, info=None):
        speed = _number(row.get('speed',1), '素材倍速', .25, 4)
        requested_length = _number(row['duration'],'片段时长',.05,86400) if 'duration' in row else None
        trim_start = _number(row.get('trimStart',0), '素材入点', 0, info['duration'] if info else 86400)
        trim_end = _number(row.get('trimEnd', info['duration'] if info else trim_start+(requested_length if requested_length is not None else duration)*speed),
            '素材出点', 0, info['duration'] if info else 345600)
        if trim_end <= trim_start:
            _error('素材出点必须晚于入点')
        length = _number(requested_length if requested_length is not None else (trim_end-trim_start)/speed, '片段时长', .05, 86400)
        start = _number(row.get('start',0), '片段开始时间', 0, duration)
        if start >= duration or start + length > duration + .0001:
            _error('片段时间超出画布时长')
        return dict(start=start, duration=length, speed=speed, trimStart=trim_start, trimEnd=trim_end,
            reverse=_boolean(row.get('reverse',False), '倒放'), volume=_number(row.get('volume',1), '音量', 0, 4),
            fadeIn=_number(row.get('fadeIn',0), '淡入时长', 0, length), fadeOut=_number(row.get('fadeOut',0), '淡出时长', 0, length))

    prepared, ids = [], set()
    for index, raw in enumerate(layers):
        row = _object(raw, {'id','type','path','start','duration','track','trimStart','trimEnd','speed','reverse','freezeAt','freezeTail',
            'volume','fadeIn','fadeOut','transform','effects','mask','keyframes','text','style','color','transitionToNext'}, '图层')
        identifier = row.get('id', f'layer-{index}')
        if not isinstance(identifier, str) or not identifier or len(identifier)>200 or identifier in ids:
            _error('图层标识无效或重复')
        ids.add(identifier)
        kind = _choice(row.get('type'), {'video','image','solid','text'}, '图层类型')
        info, source = None, None
        if kind in {'video','image'}:
            source, info = source_info(row.get('path'), kind)
        item = timing(row, info if kind == 'video' else None)
        item.update(id=identifier,type=kind,path=source,info=info,track=_integer(row.get('track',0),'轨道',0,100),order=index)
        freeze = row.get('freezeAt')
        item['freezeAt'] = _number(freeze, '定格位置', 0, max(0,info['duration']-.000001)) if freeze is not None and kind=='video' else None
        item['freezeTail'] = _number(row.get('freezeTail',0),'尾部定格时长',0,item['duration'])
        if item['freezeTail'] and (kind!='video' or item['freezeAt'] is not None):
            _error('尾部定格只支持普通视频片段，不能同时设置定格位置')
        if freeze is not None and kind!='video':
            _error('只有视频图层支持定格')
        transform = _object(row.get('transform',{}), {'x','y','width','height','rotation','flipX','flipY','opacity','fit','crop'}, '图层变换')
        crop = _object(transform.get('crop',{}), {'x','y','width','height'}, '源素材裁切')
        crop = {key:_number(crop.get(key,0 if key in {'x','y'} else 1),'源素材裁切',0 if key in {'x','y'} else .0001,1) for key in ('x','y','width','height')}
        if crop['x']+crop['width']>1.000001 or crop['y']+crop['height']>1.000001:
            _error('裁切范围超出源素材')
        item['transform'] = dict(x=_number(transform.get('x',0),'横向位置',-4,4),y=_number(transform.get('y',0),'纵向位置',-4,4),
            width=_number(transform.get('width',1),'图层宽度',.0001,4),height=_number(transform.get('height',1),'图层高度',.0001,4),
            rotation=_number(transform.get('rotation',0),'旋转',-3600,3600),opacity=_number(transform.get('opacity',1),'透明度',0,1),
            flipX=_boolean(transform.get('flipX',False),'水平翻转'),flipY=_boolean(transform.get('flipY',False),'垂直翻转'),
            fit=_choice(transform.get('fit','contain'),{'contain','cover','stretch','blur'},'画面适配'),crop=crop)
        effects = _object(row.get('effects',{}), {'brightness','contrast','saturation','hue','blur','grayscale','sepia'}, '滤镜')
        item['effects'] = {key:_number(effects.get(key,default),'滤镜 '+key,low,high) for key,default,low,high in
            [('brightness',0,-1,1),('contrast',1,0,4),('saturation',1,0,4),('hue',0,-360,360),('blur',0,0,100)]}
        item['effects'].update({key:_boolean(effects.get(key,False),'滤镜 '+key) for key in ('grayscale','sepia')})
        mask = _object(row.get('mask',{}), {'type','radius','feather','inverted'}, '蒙版')
        item['mask'] = dict(type=_choice(mask.get('type','none'),{'none','rect','circle','ellipse','rounded','diamond','heart','star','split','cinematic-bars'},'蒙版类型'),
            radius=_number(mask.get('radius',.1),'蒙版圆角',0,.5),feather=_number(mask.get('feather',0),'蒙版羽化',0,.5),inverted=_boolean(mask.get('inverted',False),'反向蒙版'))
        item['keyframes'] = _keyframes(row.get('keyframes',{}),item['duration'])
        scale = max([1]+[point['value'] for point in item['keyframes'].get('scale',[])])
        if math.hypot(width*item['transform']['width'],height*item['transform']['height'])*scale>16384:
            _error('图层尺寸或缩放过大，请缩小后导出')
        item['transitionToNext'] = transitions.normalize_transition(row.get('transitionToNext'), error=_error)
        if kind == 'solid':
            item['color'] = _color(row.get('color','#000000'),'色块颜色')
        if kind == 'text':
            text = row.get('text')
            if not isinstance(text,str) or not text.strip() or len(text)>4000:
                _error('文字图层需要 1–4000 个文字')
            item.update(text=text,style=_style(row.get('style',{})))
        prepared.append(item)
    prepared.sort(key=lambda row:(row['track'],row['start'],row['order']))
    # Transitions use explicit timeline overlap. Keeping absolute starts retains
    # gaps and all other tracks instead of shortening the document implicitly.
    for index, row in enumerate(prepared):
        transition = row['transitionToNext']
        if transition['type']=='none':
            continue
        next_row = next((other for other in prepared[index+1:] if other['track']==row['track']),None)
        if next_row is None:
            _error('转场需要同轨的下一段素材')
        overlap = row['start']+row['duration']-next_row['start']
        if overlap<=0:
            _error('转场片段需要在时间线上重叠，请先调整下一段开始时间')
        transition['duration'] = min(transition['duration'],overlap,row['duration']/2,next_row['duration']/2)
        transition['nextId'] = next_row['id']
        transition['localStart'] = next_row['start']-row['start']
        next_row['_incomingTransition'] = dict(type=transition['type'],duration=transition['duration'])
    sounds = []
    for row in audio:
        _object(row, {'path','start','duration','trimStart','trimEnd','speed','volume','fadeIn','fadeOut','reverse','loop','keyframes','ducking'}, '音频片段')
        source, info = source_info(row.get('path'),'audio')
        item = timing(row,info)
        item.update(path=source,info=info,loop=_boolean(row.get('loop',False),'音频循环'),
            ducking=_boolean(row.get('ducking',False),'配乐避让'),
            keyframes=_keyframes(row.get('keyframes',{}),item['duration'],{'volume'}))
        sounds.append(item)
    output = helpers['_local_path'](data.get('output'),existing=False)
    if output.suffix.lower()!='.'+doc['format'] or output in sources or os.path.lexists(output):
        _error('输出文件已存在、与素材相同或扩展名不匹配，请选择新的文件名','VIDEO_OUTPUT_EXISTS')
    if not output.parent.is_dir():
        _error('输出目录不存在，请重新选择')
    doc.update(layers=prepared,audioClips=sounds,output=output,_sources=tuple(sources.items()),_parentIdentity=_identity(output.parent,True))
    return copy.deepcopy(doc)


def _n(number):
    return f'{number:.8f}'


def _bezier_coordinate(t, first, second):
    inverse = 1 - t
    return 3*inverse*inverse*t*first + 3*inverse*t*t*second + t*t*t


def _bezier_progress(x, first, second):
    t = min(1., max(0., x))
    for _ in range(8):
        current = _bezier_coordinate(t, first, second) - x
        if abs(current) < 1e-7:
            return t
        inverse = 1 - t
        derivative = 3*inverse*inverse*first + 6*inverse*t*(second-first) + 3*t*t*(1-second)
        if abs(derivative) < 1e-7:
            break
        t = min(1., max(0., t-current/derivative))
    low, high = 0., 1.
    for _ in range(24):
        middle = (low+high)/2
        if _bezier_coordinate(middle, first, second) < x:
            low = middle
        else:
            high = middle
    return (low+high)/2


def _bezier_polynomial(curve):
    """Fit y(x) with a compact cubic so FFmpeg expressions stay bounded."""
    samples = []
    for x in (0., 1/3, 2/3, 1.):
        t = _bezier_progress(x, curve['x1'], curve['x2'])
        samples.append((x, _bezier_coordinate(t, curve['y1'], curve['y2'])))
    matrix = [[x**power for power in range(4)] + [y] for x, y in samples]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(matrix[row][column]))
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        divisor = matrix[column][column]
        if abs(divisor) < 1e-12:
            return (0., 0., 1., 0.)
        matrix[column] = [value/divisor for value in matrix[column]]
        for row in range(4):
            if row == column:
                continue
            scale = matrix[row][column]
            matrix[row] = [left-scale*right for left, right in zip(matrix[row], matrix[column])]
    return tuple(matrix[index][4] for index in range(4))


def _expression(points, default, clock='t'):
    if not points:
        return _n(default)
    if len(points)==1:
        return _n(points[0]['value'])
    def number(value):
        return format(value,'.17g')
    def segment(low,high):
        # Balanced selection keeps 200 keyframes below FFmpeg's expression
        # recursion limit. A linear chain of nested if() fails around 100.
        if high-low>1:
            middle=(low+high)//2
            return f'if(lt({clock},{number(points[middle]["time"])}),{segment(low,middle)},{segment(middle,high)})'
        first,second=points[low],points[high]
        u = f'clip(({clock}-{number(first["time"])})/{number(second["time"]-first["time"])},0,1)'
        easing = first['easing']
        if easing=='hold':
            return number(first['value'])
        if isinstance(easing, dict):
            constant,linear,quadratic,cubic = _bezier_polynomial(easing)
            factor = (f'clip({number(cubic)}*pow({u},3)+{number(quadratic)}*pow({u},2)'
                      f'+{number(linear)}*{u}+{number(constant)},0,1)')
        else:
            factor = {'linear':u,'ease-in':f'pow({u},2)','ease-out':f'(1-pow(1-{u},2))',
                'ease-in-out':f'if(lt({u},0.5),2*pow({u},2),1-pow(-2*{u}+2,2)/2)'}[easing]
        return f'({number(first["value"])}+({number(second["value"]-first["value"])})*({factor}))'
    return f'if(gte({clock},{number(points[-1]["time"])}),{number(points[-1]["value"])},{segment(0,len(points)-1)})'


def _ass_color(color):
    return '&H00'+color[5:7]+color[3:5]+color[1:3]


def _text_file(row, width, height, index, folder):
    style = row['style']
    original = row['text'].replace('\r\n','\n').replace('\r','\n')
    text = original
    text = re.sub(r'[\x00-\x09\x0b-\x1f\x7f]',' ',text).replace('\\','＼').replace('{','｛').replace('}','｝').replace('\n',r'\N')
    align = {'left':4,'center':5,'right':6}[style['align']]
    x = {'left':min(4,width/2),'center':width/2,'right':max(width/2,width-4)}[style['align']]
    wrap_style = 2 if style['noWrap'] else 0
    scale_x = 100
    if style['noWrap']:
        def units(value):
            return sum(.56 if ord(char) < 128 else 1 for char in value)
        longest = max((units(line) for line in original.split('\n')), default=1)
        available = max(1, width - 8)
        scale_x = max(5, min(100, round(available * 100 / max(1, longest * style['size']))))
    scale = rf'\fscx{scale_x}\fscy100' if scale_x != 100 else ''
    content = (f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: {wrap_style}\nScaledBorderAndShadow: yes\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Layer,{style["font"]},{style["size"]},{_ass_color(style["color"])},{_ass_color(style["color"])},{_ass_color(style["outlineColor"])},{_ass_color(style["shadowColor"])},'
        f'{-int(style["bold"])},{-int(style["italic"])},{-int(style["underline"])},0,100,100,{style["letterSpacing"]},0,1,{style["outline"]},{style["shadow"]},{align},0,0,0,1\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
        f'Dialogue: 0,0:00:00.00,24:00:00.00,Layer,,0,0,0,,{{\\an{align}\\q{wrap_style}\\pos({x:g},{height/2:g}){scale}}}{text}\n')
    name = f'text-{index:05d}.ass'
    (folder/name).write_text(content,encoding='utf-8-sig')
    return name


def _mask_expression(mask):
    kind = mask['type']
    x, y = '(2*X/W-1)', '(2*Y/H-1)'
    if kind in {'none','rect'}:
        shape = '1'
    elif kind=='circle':
        shape = 'lte(pow(X-W/2,2)+pow(Y-H/2,2),pow(min(W,H)/2,2))'
    elif kind=='ellipse':
        shape = f'lte(pow({x},2)+pow({y},2),1)'
    elif kind=='diamond':
        shape = f'lte(abs({x})+abs({y}),1)'
    elif kind=='rounded':
        radius = f'max(0.001,min(W,H)*{_n(mask["radius"])})'
        shape = f'lte(pow(max(abs(X-W/2)-(W/2-{radius}),0),2)+pow(max(abs(Y-H/2)-(H/2-{radius}),0),2),pow({radius},2))'
    elif kind=='heart':
        shape = f'lte(pow(pow({x},2)+pow(-{y},2)-0.7,3)-pow({x},2)*pow(-{y},3),0)'
    elif kind=='star':
        shape = f'lte(hypot({x},{y}),0.65+0.3*cos(5*atan2({x},-{y})))'
    elif kind=='split':
        shape = 'lt(X,W/2)'
    else:
        shape = 'between(Y,H*0.125,H*0.875)'
    return f'(1-({shape}))' if mask['inverted'] else shape


def _atempo(speed):
    filters = []
    while speed>2:
        filters.append('atempo=2'); speed/=2
    while speed<.5:
        filters.append('atempo=0.5'); speed/=.5
    return ','.join(filters+[f'atempo={_n(speed)}'])


def _bounded_inputs(args,folder,durations):
    """Move long local input URLs into owned one-file demuxer manifests.

    A graph file alone cannot protect CreateProcess when 200 layers each
    repeat a long filename. Small documents retain the direct demuxer path.
    """
    if sum(len(str(value))+3 for value in args)<24000:
        return args
    result,manifests,index=[],{},0
    while index<len(args):
        value=args[index]
        if value=='-i' and index+1<len(args) and isinstance(args[index+1],Path):
            source=args[index+1]
            if source not in manifests:
                name=f'input-{len(manifests):05d}.ffconcat'
                escaped=source.as_posix().replace("'","'\\''")
                # Explicit durations make this single-file virtual input
                # seekable, preserving each layer's input -ss trim.
                (folder/name).write_text(f"ffconcat version 1.0\nfile '{escaped}'\nduration {_n(durations[source])}\n",encoding='utf-8')
                manifests[source]=name
            result+=['-f','concat','-safe','0','-i',manifests[source]]
            index+=2
        else:
            result.append(value)
            index+=1
    return result


def _audio_filters(row, total):
    filters = ['asetpts=PTS-STARTPTS']
    if row['reverse']:
        filters.append('areverse')
    filters += [_atempo(row['speed']),'aformat=sample_fmts=fltp:channel_layouts=stereo','aresample=48000:async=1:first_pts=0']
    if row.get('freezeTail'):
        moving = row['duration']-row['freezeTail']
        filters.append(f'atrim=duration={_n(moving)}' if moving>0 else 'volume=0')
    if row.get('loop'):
        samples = max(1,round((row['trimEnd']-row['trimStart'])/row['speed']*48000))
        filters += [f'atrim=end_sample={samples}',f'aloop=loop=-1:size={samples}:start=0','asetpts=N/SR/TB']
    filters += [f'apad,atrim=duration={_n(row["duration"])},asetpts=PTS-STARTPTS']
    volume = _expression(row.get('keyframes',{}).get('volume',[]),row['volume'])
    filters.append(f"volume='{volume}':eval=frame")
    if row['fadeIn']:
        filters.append(f'afade=t=in:st=0:d={_n(row["fadeIn"])}')
    if row['fadeOut']:
        filters.append(f'afade=t=out:st={_n(row["duration"]-row["fadeOut"])}:d={_n(row["fadeOut"])}')
    incoming = row.get('_incomingTransition')
    outgoing = row.get('transitionToNext')
    if incoming:
        filters.append(f'afade=t=in:st=0:d={_n(incoming["duration"])}')
    if outgoing and outgoing['type']!='none':
        filters.append(f'afade=t=out:st={_n(outgoing["localStart"])}:d={_n(outgoing["duration"])}')
    filters += [f'adelay={round(row["start"]*48000)}S:all=1','asetpts=N/SR/TB',f'apad,atrim=duration={_n(total)}']
    return ','.join(filters)


def _visual_filters(row, doc, index, folder):
    transform, effects, mask = row['transform'],row['effects'],row['mask']
    width,height = max(1,round(doc['width']*transform['width'])),max(1,round(doc['height']*transform['height']))
    filters = (['trim=end_frame=1','loop=loop=-1:size=1:start=0',f'setpts=N/{_n(doc["fps"])}/TB']
        if row['type']=='image' else ['setpts=PTS-STARTPTS'])
    if row['type']=='video' and row['reverse'] and row['freezeAt'] is None:
        filters.append('reverse')
    if row['type']=='video':
        filters += [f'setpts=PTS/{_n(row["speed"])}',f'scale={row["info"]["width"]}:{row["info"]["height"]},setsar=1']
        if row['freezeTail']:
            moving = row['duration']-row['freezeTail']
            filters.append(f'trim=duration={_n(moving)}' if moving>0 else 'trim=end_frame=1')
    filters += [f'fps={_n(doc["fps"])}',f'tpad=stop_mode=clone:stop_duration={_n(row["duration"])}',f'trim=duration={_n(row["duration"])}','setpts=PTS-STARTPTS','format=rgba']
    crop = transform['crop']
    if crop!={'x':0.,'y':0.,'width':1.,'height':1.}:
        filters.append(f"crop=w='max(1,iw*{_n(crop['width'])})':h='max(1,ih*{_n(crop['height'])})':x=iw*{_n(crop['x'])}:y=ih*{_n(crop['y'])}")
    if row['type'] in {'solid','text'} or transform['fit']=='stretch':
        filters.append(f'scale={width}:{height}')
    elif transform['fit']=='cover':
        filters += [f'scale={width}:{height}:force_original_aspect_ratio=increase',f'crop={width}:{height}']
    elif transform['fit']=='blur':
        filters.append(f'split=2[fitbg{index}][fitfg{index}];[fitbg{index}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=20[fitbed{index}];[fitfg{index}]scale={width}:{height}:force_original_aspect_ratio=decrease[fitfront{index}];[fitbed{index}][fitfront{index}]overlay=(W-w)/2:(H-h)/2:shortest=1')
    else:
        filters += [f'scale={width}:{height}:force_original_aspect_ratio=decrease',f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0']
    if row['type']=='text':
        filters.append('ass=filename='+_text_file(row,width,height,index,folder)+':alpha=1')
    if transform['flipX']:
        filters.append('hflip')
    if transform['flipY']:
        filters.append('vflip')
    if any(effects[key]!=default for key,default in [('brightness',0),('contrast',1),('saturation',1)]) or effects['grayscale']:
        filters.append(f'eq=brightness={_n(effects["brightness"])}:contrast={_n(effects["contrast"])}:saturation={_n(0 if effects["grayscale"] else effects["saturation"])}')
    if effects['hue']:
        filters.append(f'hue=h={_n(effects["hue"])}')
    if effects['sepia']:
        filters.append('colorchannelmixer=rr=.393:rg=.769:rb=.189:gr=.349:gg=.686:gb=.168:br=.272:bg=.534:bb=.131')
    if effects['blur']:
        filters.append(f'gblur=sigma={_n(effects["blur"])}:planes=7')
    filters.append('format=rgba')
    if mask['type']!='none' or mask['inverted']:
        shape = _mask_expression(mask)
        filters.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({shape})'")
        if mask['feather']:
            filters.append(f'gblur=sigma={_n(max(.01,mask["feather"]*min(width,height)))}:planes=8')
    opacity = _expression(row['keyframes'].get('opacity',[]),transform['opacity'],'T')
    if row['fadeIn']:
        opacity = f'({opacity})*clip(T/{_n(row["fadeIn"])},0,1)'
    if row['fadeOut']:
        opacity = f'({opacity})*clip(({_n(row["duration"])}-T)/{_n(row["fadeOut"])},0,1)'
    if row['keyframes'].get('opacity') or transform['opacity']!=1 or row['fadeIn'] or row['fadeOut']:
        filters.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({opacity})'")
    incoming = row.get('_incomingTransition')
    if incoming:
        kind,span = incoming['type'],_n(incoming['duration'])
        fraction = f'clip(T/{span},0,1)'
        reveal = None
        if kind=='fade':
            reveal = fraction
        elif kind=='dissolve':
            reveal = f'lt(mod(abs(sin(X*12.9898+Y*78.233)*43758.5453),1),{fraction})'
        elif kind=='wipeleft':
            reveal = f'gte(X,W*(1-{fraction}))'
        elif kind=='wiperight':
            reveal = f'lte(X,W*{fraction})'
        if reveal is not None:
            filters.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({reveal})'")
    scale = _expression(row['keyframes'].get('scale',[]),1)
    scale_max = max([1]+[point['value'] for point in row['keyframes'].get('scale',[])])
    rotating = bool(transform['rotation'] or row['keyframes'].get('rotation'))
    side_width = math.ceil(math.hypot(width,height)*scale_max)+4 if rotating else math.ceil(width*scale_max)
    side_height = side_width if rotating else math.ceil(height*scale_max)
    # Fixed transparent bounds keep scale/rotation animation acceptable to
    # framesync; changing overlay dimensions every frame corrupts its cache.
    if row['keyframes'].get('scale'):
        filters.append(f"scale=w='max(1,round({width}*({scale})))':h='max(1,round({height}*({scale})))':eval=frame")
    if rotating or row['keyframes'].get('scale'):
        filters.append(f'pad={side_width}:{side_height}:(ow-iw)/2:(oh-ih)/2:color=black@0:eval=frame')
    if rotating:
        rotation = _expression(row['keyframes'].get('rotation',[]),transform['rotation'])
        filters.append(f"rotate=angle='({rotation})*PI/180':ow=iw:oh=ih:c=black@0")
    filters += ['format=rgba',f'setpts=PTS+{_n(row["start"])}/TB']
    clock = f'(t-{_n(row["start"])})'
    x = _expression(row['keyframes'].get('x',[]),transform['x'],clock)
    y = _expression(row['keyframes'].get('y',[]),transform['y'],clock)
    slide=''
    if incoming and incoming['type'] in {'slideleft','slideright'}:
        sign=1 if incoming['type']=='slideleft' else -1
        slide+=f'+({sign}*{doc["width"]}*(1-clip({clock}/{_n(incoming["duration"])},0,1)))'
    outgoing = row['transitionToNext']
    if outgoing['type'] in {'slideleft','slideright'}:
        sign=-1 if outgoing['type']=='slideleft' else 1
        slide+=f'+({sign}*{doc["width"]}*clip(({clock}-{_n(outgoing["localStart"])})/{_n(outgoing["duration"])},0,1))'
    position = (f"x='{doc['width']}*({x})-({side_width}-{width})/2{slide}':"
        f"y='{doc['height']}*({y})-({side_height}-{height})/2'")
    return ','.join(filters),position


def make_work(self, data):
    helpers, tool = self._smart_helpers, self.api.ctx.ffmpeg_tool()
    doc = validate_document(data,tool,helpers)
    output, parent = doc['output'],doc['output'].parent

    def validate(folder=None, owner=None):
        if _identity(parent,True)!=doc['_parentIdentity'] or (folder is not None and _identity(folder,True)!=owner):
            _error('输出目录已变化，请重新选择保存位置','TIMELINE_CHANGED')
        for source,identity in doc['_sources']:
            if _identity(source)!=identity:
                _error('素材已变化，请重新导入后导出','TIMELINE_CHANGED')
        if os.path.lexists(output):
            _error('输出文件已存在，请选择新的文件名','VIDEO_OUTPUT_EXISTS')

    def work(progress,control):
        check_control(control)
        validate()
        folder = Path(tempfile.mkdtemp(prefix='.aive-timeline-v2-',dir=parent))
        owner = _identity(folder,True)
        try:
            validate(folder,owner)
            args = ['-f','lavfi','-i',f'color=c={doc["background"]}:s={doc["width"]}x{doc["height"]}:r={_n(doc["fps"])}:d={_n(doc["duration"])}',
                '-f','lavfi','-i',f'anullsrc=r=48000:cl=stereo:d={_n(doc["duration"])}']
            graph, video, audios = ['[0:v]format=rgba[base]','[1:a]anull[silence]'],'base',['silence']
            next_input = 2
            for number,row in enumerate(doc['layers']):
                check_control(control)
                index = next_input; next_input+=1
                kind = row['type']
                if kind=='image':
                    args += ['-protocol_whitelist','file,pipe','-i',row['path']]
                elif kind=='video':
                    freeze = row['freezeAt']
                    args += ['-protocol_whitelist','file,pipe','-ss',_n(freeze if freeze is not None else row['trimStart']),
                        '-t',_n(1/doc['fps'] if freeze is not None else row['trimEnd']-row['trimStart']),'-i',row['path']]
                else:
                    color = row['color'] if kind=='solid' else ((row['style']['background']+'@'+_n(row['style']['backgroundOpacity'])) if row['style']['background'] else 'black@0')
                    args += ['-f','lavfi','-i',f'color=c={color}:s=16x16:r={_n(doc["fps"])}:d={_n(row["duration"])},format=rgba']
                filters, position = _visual_filters(row,doc,number,folder)
                stream = row['info']['_videoStream'] if row['info'] else 'v:0'
                graph.append(f'[{index}:{stream}]{filters}[layer{number}]')
                graph.append(f'[{video}][layer{number}]overlay={position}:eof_action=pass:repeatlast=0:format=auto:'
                    f"enable='gte(t,{_n(row['start'])})*lt(t,{_n(row['start']+row['duration'])})'[composite{number}]")
                video = f'composite{number}'
                if kind=='video' and row['info']['hasAudio'] and row['freezeAt'] is None and (row['volume']>0 or row['keyframes'].get('volume')):
                    # Probe's default audio stream is independent from the video
                    # index (cover art and multiple language tracks are legal).
                    audio_info = helpers['_load_editor_extension']('timeline_editing')._probe_audio(tool,row['path'],helpers)
                    label = f'layeraudio{number}'
                    graph.append(f'[{index}:{audio_info["_audioStream"]}]{_audio_filters(row,doc["duration"])}[{label}]')
                    audios.append(label)
            beds=[]
            for number,row in enumerate(doc['audioClips']):
                index = next_input; next_input+=1
                args += ['-protocol_whitelist','file,pipe','-ss',_n(row['trimStart']),'-t',_n(row['trimEnd']-row['trimStart']),'-i',row['path']]
                label = f'audio{number}'
                graph.append(f'[{index}:{row["info"]["_audioStream"]}]{_audio_filters(row,doc["duration"])}[{label}]')
                (beds if row['ducking'] else audios).append(label)
            if beds:
                # The foreground includes the full-duration silent anchor, so
                # gaps and videos with no narration keep the music audible.
                graph.append(''.join(f'[{label}]' for label in audios)+
                    f'amix=inputs={len(audios)}:duration=first:dropout_transition=0:normalize=0[foreground]')
                graph.append(f'[foreground]asplit={len(beds)+1}[voice]'+
                    ''.join(f'[sidechain{index}]' for index in range(len(beds))))
                audios=['voice']
                for index,label in enumerate(beds):
                    graph.append(f'[{label}][sidechain{index}]sidechaincompress='
                        f'threshold=0.025:ratio=8:attack=15:release=350:makeup=1[ducked{index}]')
                    audios.append(f'ducked{index}')
            graph.append(''.join(f'[{label}]' for label in audios)+f'amix=inputs={len(audios)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false:latency=true[outaudio]')
            graph.append(f'[{video}]fps={_n(doc["fps"])},format=yuv420p[outvideo]')
            graph_file = folder/'compositor.ffgraph'
            graph_file.write_text(';\n'.join(graph),encoding='utf-8')
            stage = folder/('output.'+doc['format'])
            args += ['-filter_complex_threads','1','-/filter_complex',graph_file.name,'-map','[outvideo]','-map','[outaudio]','-t',_n(doc['duration'])]
            quality = doc['quality']
            if doc['format']=='mp4':
                args += ['-c:v','libx264','-preset','veryfast','-crf',{'high':'18','medium':'23','low':'28'}[quality],'-c:a','aac','-b:a','192k','-movflags','+faststart']
            else:
                args += ['-c:v','libvpx-vp9','-deadline','good','-cpu-used','4','-crf',{'high':'24','medium':'32','low':'40'}[quality],'-b:v','0','-c:a','libopus','-b:a','160k']
            args += ['-pix_fmt','yuv420p','-ar','48000','-ac','2','-map_metadata','-1','-metadata:s:v:0','rotate=0',stage]
            source_durations={row['path']:row['info']['duration'] for row in doc['layers']+doc['audioClips'] if row.get('info')}
            args = _bounded_inputs(args,folder,source_durations)
            progress(1,'正在合成视觉图层、关键帧和音频')
            validate(folder,owner)
            helpers['_run_ffmpeg'](tool,args,doc['duration'],progress,control,folder,start=1,span=96)
            completed = helpers['_probe'](tool,stage)
            validate(folder,owner)
            def commit_progress(percent,message=''):
                progress(percent,message)
                validate(folder,owner)
            helpers['_commit'](stage,output,commit_progress,control)
            return dict(path=str(output),width=doc['width'],height=doc['height'],duration=completed['duration'],
                documentVersion=3,layerCount=len(doc['layers']),audioCount=len(doc['audioClips']),format=doc['format'])
        finally:
            try:
                if _identity(parent,True)==doc['_parentIdentity'] and _identity(folder,True)==owner:
                    shutil.rmtree(folder)
            except (OSError,BridgeError):
                pass
    return work,dict(documentVersion=3,duration=doc['duration'],width=doc['width'],height=doc['height'],layerCount=len(doc['layers']),audioCount=len(doc['audioClips']))


def start_export(self,data):
    work,_ = make_work(self,data)
    return self.api.tasks.start('时间线剪辑导出',work,category='video',location={'route':'/video-tools'})
