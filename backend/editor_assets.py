"""Customer-managed media effects and original local music choices."""
import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from app.ui2.common import BridgeError

ASSET_ROOT=Path(__file__).resolve().parent/'runtime'/'editor_assets'
_ID=re.compile(r'^[a-f0-9]{32}$')
_COLOR=re.compile(r'^#[0-9a-fA-F]{6}$')
_TYPES={'.png':'image','.webp':'image','.jpg':'image','.jpeg':'image','.mov':'video','.mp4':'video','.webm':'video','.mkv':'video','.cube':'lut','.json':'preset'}
_TRACKS=[('soft','舒缓钢琴','柔和、平稳的原创器乐'),('upbeat','轻快律动','明快节拍，适合展示和快剪'),('ambient','空灵氛围','轻柔铺底，适合旁白'),('cinematic','电影氛围','低音与和弦，适合故事片段'),('acoustic','温暖木琴','温暖、轻盈的拨弦风格'),('playful','活泼趣味','轻快跳跃，适合趣味短片')]

def _error(message):raise BridgeError('EDITOR_ASSET_INVALID',message)

def _root():
    if ASSET_ROOT.resolve()!=ASSET_ROOT:_error('特效素材目录被重定向，请恢复应用目录')
    ASSET_ROOT.mkdir(parents=True,exist_ok=True)
    return ASSET_ROOT

def _safe(path):
    root=_root()
    absolute=Path(os.path.abspath(path))
    resolved=absolute.resolve()
    if not resolved.is_relative_to(root) or resolved==root:_error('特效路径不在素材库内')
    if resolved!=absolute:_error('特效素材目录或文件被重定向，请重新导入')
    return resolved

def _folder(identifier):
    if not isinstance(identifier,str) or not _ID.fullmatch(identifier):_error('特效编号无效')
    return _safe(_root()/'effects'/identifier)

def _number(value,name,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:_error(name+'超出支持范围')
    return float(value)

def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result

def _digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def _preset(path):
    if path.stat().st_size>1024*1024:_error('JSON特效预设最多1MB')
    try:data=json.loads(path.read_text('utf-8-sig'),object_pairs_hook=_unique_object)
    except (OSError,ValueError,UnicodeError):_error('特效预设不是有效的UTF-8 JSON')
    if not isinstance(data,dict) or set(data)-{'version','name','filters'} or type(data.get('version')) is not int or data['version']!=1:_error('JSON特效预设格式不支持，请查看格式示例')
    if 'name' in data and (not isinstance(data['name'],str) or len(data['name'])>120):_error('特效预设名称格式无效')
    rows=data.get('filters')
    if not isinstance(rows,list) or not 1<=len(rows)<=16:_error('特效预设需要1–16个受支持的调整')
    bounds={'brightness':(-1,1),'contrast':(0,3),'saturation':(0,3),'blur':(0,10),'sharpen':(0,2),'vignette':(0,1)}
    result=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'type','value'} or row['type'] not in bounds:_error('JSON只支持亮度、对比度、饱和度、模糊、锐化和暗角调整')
        value=_number(row['value'],row['type'],*bounds[row['type']]);result.append({'type':row['type'],'value':value})
    return result

def _lut(path):
    if path.stat().st_size>16*1024**2:_error('Cube调色文件最多16MB')
    try:lines=path.read_text('utf-8-sig').splitlines()
    except (OSError,UnicodeError):_error('Cube文件必须是可读取的文本')
    size=None;count=0;domains={}
    for line in lines:
        line=line.split('#',1)[0].strip()
        if not line:continue
        parts=line.split()
        if parts[0]=='TITLE':continue
        if parts[0]=='LUT_3D_SIZE':
            if size is not None or len(parts)!=2 or count:_error('Cube尺寸格式无效')
            try:size=int(parts[1])
            except ValueError:_error('Cube尺寸无效')
            if not 2<=size<=65:_error('支持2–65阶3D Cube文件')
            continue
        domain=parts[0] if parts[0] in ('DOMAIN_MIN','DOMAIN_MAX') else None
        if domain:
            if domain in domains or count:_error('Cube颜色范围声明无效')
            parts=parts[1:]
        else:count+=1
        if len(parts)!=3:_error('Cube颜色行格式无效')
        try:values=[float(value) for value in parts]
        except ValueError:_error('Cube颜色值无效')
        if any(not math.isfinite(value) or not -10<=value<=10 for value in values):_error('Cube颜色值超出支持范围')
        if domain:domains[domain]=values
    if size is None or count!=size**3:_error('Cube文件颜色数量与3D尺寸不匹配')
    minimum=domains.get('DOMAIN_MIN',[0,0,0]);maximum=domains.get('DOMAIN_MAX',[1,1,1])
    if any(high<=low for low,high in zip(minimum,maximum)):_error('Cube颜色范围必须有正向区间')
    return size

def _media(path,tool):
    try:
        process=subprocess.run([str(tool.ffprobe),'-v','error','-show_streams','-show_format','-of','json',str(path)],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        data=json.loads(process.stdout)
        candidates=[stream for stream in data['streams'] if stream.get('codec_type')=='video' and not stream.get('disposition',{}).get('attached_pic')]
        stream=next(iter(sorted(candidates,key=lambda row:row.get('disposition',{}).get('default',0),reverse=True)))
        width,height=int(stream['width']),int(stream['height'])
        if process.returncode or not 1<=width<=8192 or not 1<=height<=8192:raise ValueError()
        duration=float(data.get('format',{}).get('duration',stream.get('duration',0)) or 0)
        rotation=stream.get('tags',{}).get('rotate',0)
        for side in stream.get('side_data_list',[]):
            if 'rotation' in side:rotation=side['rotation']
        rotation=float(rotation)
        if not math.isfinite(rotation):raise ValueError()
        if abs(round(rotation))%180==90:width,height=height,width
        pix=str(stream.get('pix_fmt',''))
        alpha=pix.startswith(('rgba','bgra','argb','abgr','yuva','gbrap')) or stream.get('tags',{}).get('alpha_mode')=='1'
        return {'width':width,'height':height,'duration':duration,'hasAlpha':alpha,
            'videoStream':int(stream['index']),'videoCodec':str(stream.get('codec_name',''))}
    except (OSError,ValueError,KeyError,TypeError,StopIteration,subprocess.TimeoutExpired):_error('特效素材无法读取，或画面尺寸超过8192像素')

def list_effects():
    directory=_root()/'effects'
    if not directory.exists():return []
    result=[]
    for folder in directory.iterdir():
        if not _ID.fullmatch(folder.name):continue
        try:
            item=resolve_effect(folder.name)
            result.append(item)
        except (OSError,ValueError,BridgeError):continue
    return sorted(result,key=lambda row:row.get('created',0),reverse=True)

def resolve_effect(identifier):
    folder=_folder(identifier)
    try:
        metadata=_safe(folder/'metadata.json')
        if metadata.stat().st_size>65536:_error('特效元数据超过支持大小')
        data=json.loads(metadata.read_text('utf-8'),object_pairs_hook=_unique_object)
    except (OSError,ValueError):_error('特效不存在或尚未导入完成')
    if not isinstance(data,dict) or data.get('active') is not True or data.get('id')!=identifier or data.get('kind') not in set(_TYPES.values()):_error('特效已从素材库移出，请重新选择')
    name=data.get('file')
    if not isinstance(name,str) or Path(name).name!=name or not name.startswith('asset.'):_error('特效元数据文件路径无效')
    asset=_safe(folder/name)
    if _TYPES.get(asset.suffix.lower())!=data['kind']:_error('特效素材类型与元数据不一致')
    if type(data.get('size')) is not int or not 0<data['size']<=2*1024**3 or not asset.is_file() or asset.stat().st_size!=data['size']:_error('特效素材已变化，请重新导入')
    if not isinstance(data.get('sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',data['sha256']):_error('特效素材摘要无效，请重新导入')
    if data['kind'] in ('image','video'):
        for key in ('width','height'):
            if type(data.get(key)) is not int or not 1<=data[key]<=8192:_error('特效画面尺寸无效')
        if type(data.get('videoStream',0)) is not int or data.get('videoStream',0)<0:_error('特效视频流编号无效')
        if not isinstance(data.get('videoCodec',''),str) or not re.fullmatch(r'[a-zA-Z0-9_]*',data.get('videoCodec','')):_error('特效视频格式无效')
    if not isinstance(data.get('name'),str) or not isinstance(data.get('sourceName'),str):_error('特效名称元数据无效')
    _number(data.get('created'),'特效导入时间',0,10**12)
    return {**data,'path':str(asset)}

def _write_meta(folder,data):
    path=_safe(folder/'metadata.json');stage=_safe(folder/('metadata-'+uuid.uuid4().hex+'.pending'))
    try:
        with stage.open('x',encoding='utf-8') as stream:stream.write(json.dumps(data,ensure_ascii=False,indent=2))
        _safe(path);_safe(stage);os.replace(stage,path)
    finally:
        if stage.exists():_safe(stage).unlink()

def import_effect(source,tool):
    source=Path(source)
    extension=source.suffix.lower();kind=_TYPES.get(extension)
    if not kind:_error('支持图片、透明/绿幕视频、.cube调色文件和JSON预设；其它格式尚未适配')
    try:before=source.stat()
    except OSError:_error('所选特效文件不存在或不可读取')
    if not source.is_file():_error('请选择特效文件')
    size=before.st_size
    if not 0<size<=2*1024**3:_error('特效文件为空或超过2GB，请选择较小素材')
    effects=_safe(_root()/'effects');effects.mkdir(exist_ok=True)
    if shutil.disk_usage(effects).free<size+10*1024**2:_error('磁盘空间不足，无法保存特效副本')
    identifier=uuid.uuid4().hex;folder=_folder(identifier);folder.mkdir()
    owner=folder.stat().st_ino
    try:
        target=_safe(folder/('asset'+extension));digest=hashlib.sha256()
        with source.open('rb') as original,target.open('xb') as copied:
            for block in iter(lambda:original.read(1024*1024),b''):
                digest.update(block);copied.write(block)
        after=source.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino) or target.stat().st_size!=size or _digest(source)!=digest.hexdigest():_error('导入期间素材发生变化，请重新选择')
        extra={}
        if kind=='preset':extra['filters']=_preset(target)
        elif kind=='lut':extra['lutSize']=_lut(target)
        else:
            extra=_media(target,tool)
            if kind=='video' and (not math.isfinite(extra['duration']) or extra['duration']<=0):_error('特效视频时长无效')
        data={'id':identifier,'name':source.stem[:120],'sourceName':source.name[:240],'kind':kind,
            'file':target.name,'size':size,'sha256':digest.hexdigest(),'created':time.time(),'active':True,**extra}
        _write_meta(folder,data)
        return resolve_effect(identifier)
    except BaseException:
        # Only the unique directory created above is eligible for cleanup.
        try:
            if _safe(folder)==folder and folder.stat().st_ino==owner:shutil.rmtree(folder)
        except (OSError,BridgeError):pass
        raise

def get_bgm_tracks():
    root=_root()/'music'
    return [{'id':identifier,'name':name,'description':description,'path':str(root/(identifier+'.wav'))} for identifier,name,description in _TRACKS]

def get_bgm_path(identifier):
    if identifier not in {row[0] for row in _TRACKS}:_error('请选择支持的内置配乐')
    path=_safe(_root()/'music'/(identifier+'.wav'))
    if not path.is_file():_error('内置配乐文件未准备好，请检查应用安装目录')
    return path

def prepare_effects(selections,duration):
    duration=_number(duration,'视频时长',0.001,86400)
    if not isinstance(selections,list) or len(selections)>8:_error('每次支持最多8个叠加特效')
    result=[]
    for selected in selections:
        if not isinstance(selected,dict):_error('特效设置格式无效')
        if selected.get('enabled',True) is False:continue
        if not isinstance(selected.get('enabled',True),bool):_error('特效启用选项无效')
        item=resolve_effect(selected.get('id'))
        if _digest(Path(item['path']))!=item['sha256']:_error('特效素材已变化，请重新导入')
        if item['kind']=='preset':item['filters']=_preset(Path(item['path']))
        elif item['kind']=='lut':_lut(Path(item['path']))
        start=_number(selected.get('start',0),'特效开始时间',0,duration)
        end=_number(selected.get('end',0),'特效结束时间',0,duration)
        end=end or duration
        if end<=start:_error('特效结束时间必须晚于开始时间')
        position=selected.get('position','center')
        if position not in ('center','top','bottom','top-left','top-right','bottom-left','bottom-right'):_error('特效位置选项无效')
        key=selected.get('keyColor','#00FF00')
        if not isinstance(key,str) or not _COLOR.fullmatch(key):_error('绿幕颜色格式无效')
        chroma=selected.get('chromaKey',False)
        if not isinstance(chroma,bool):_error('绿幕选项无效')
        stat=Path(item['path']).stat()
        result.append({**item,'start':start,'end':end,'opacity':_number(selected.get('opacity',.6),'透明度',0,1),
            'scale':_number(selected.get('scale',1),'特效尺寸',.05,2),'position':position,'chromaKey':chroma,'keyColor':key,
            'lutStrength':_number(selected.get('lutStrength',1),'调色强度',0,1),'snapshot':(stat.st_size,stat.st_mtime_ns,stat.st_ino)})
    return result

def validate_effects(records,verify_content=True):
    """Use full content checks at queue/start/commit; cheap checks between frames."""
    if not isinstance(verify_content,bool):_error('特效校验选项无效')
    for item in records:
        try:
            path=_safe(item['path']);stat=path.stat()
            digest=_digest(path) if verify_content else None
        except OSError:_error('特效素材已移除，请重新生成计划')
        if (stat.st_size,stat.st_mtime_ns,stat.st_ino)!=item['snapshot'] or verify_content and digest!=item['sha256']:_error('特效素材已变化，请重新生成计划')

def build_effect_graph(records,width,height,duration,scratch,first_input_index):
    validate_effects(records)
    inputs=[];filters=[];current='0:v:0';stream_index=first_input_index
    positions={'center':('(W-w)/2','(H-h)/2'),'top':('(W-w)/2','0'),'bottom':('(W-w)/2','H-h'),
        'top-left':('0','0'),'top-right':('W-w','0'),'bottom-left':('0','H-h'),'bottom-right':('W-w','H-h')}
    for number,item in enumerate(records):
        enable=f"between(t,{item['start']:.6f},{item['end']:.6f})";output=f'fx{number}'
        if item['kind'] in ('image','video'):
            if item['kind']=='image':inputs+=['-loop','1','-framerate','30','-i',item['path']]
            else:
                inputs+=['-stream_loop','-1']
                # FFmpeg's native WebM decoders ignore the auxiliary alpha plane.
                if item.get('hasAlpha') and item.get('videoCodec') in ('vp8','vp9'):
                    inputs+=['-c:v','libvpx-vp9' if item['videoCodec']=='vp9' else 'libvpx']
                inputs+=['-i',item['path']]
            factor=min(width/item['width'],height/item['height'])*item['scale']
            target_w=max(2,round(item['width']*factor));target_h=max(2,round(item['height']*factor))
            overlay=f'overlay{number}'
            image=f"[{stream_index}:{item.get('videoStream',0)}]setpts=PTS-STARTPTS+{item['start']:.6f}/TB,scale={target_w}:{target_h},setsar=1,format=rgba"
            if item['chromaKey']:image+=f",colorkey=0x{item['keyColor'][1:]}:0.2:0.05"
            image+=f",colorchannelmixer=aa={item['opacity']:.6f}[{overlay}]";filters.append(image)
            x,y=positions[item['position']]
            filters.append(f"[{current}][{overlay}]overlay=x={x}:y={y}:enable='{enable}':eof_action=pass[{output}]")
            stream_index+=1
        elif item['kind']=='lut':
            name=f'effect-{number}.cube';shutil.copyfile(item['path'],Path(scratch)/name)
            raw,graded=f'raw{number}',f'graded{number}'
            filters.append(f'[{current}]split=2[{raw}][lut{number}]')
            filters.append(f'[lut{number}]lut3d=file={name}:interp=tetrahedral[{graded}]')
            amount=item['lutStrength']
            filters.append(f"[{raw}][{graded}]blend=all_expr='A*{1-amount:.6f}+B*{amount:.6f}':enable='{enable}'[{output}]")
        else:
            operations=[]
            for row in item['filters']:
                kind,value=row['type'],row['value']
                if kind in ('brightness','contrast','saturation'):operations.append(f"eq={kind}={value:.6f}:enable='{enable}'")
                elif kind=='blur':operations.append(f"gblur=sigma={value:.6f}:enable='{enable}'")
                elif kind=='sharpen':operations.append(f"unsharp=luma_amount={value:.6f}:enable='{enable}'")
                else:operations.append(f"vignette=angle={value*.785398:.6f}:enable='{enable}'")
            filters.append(f'[{current}]'+','.join(operations)+f'[{output}]')
        current=output
    return {'inputs':inputs,'filters':filters,'output':current,'count':len(records)}

class EditorAssetsMixin:
    def video_getEditorOptions(self,data):
        load=self._smart_helpers['_load_editor_extension']
        return {'languages':load('local_speech').get_languages(),'subtitlePresets':load('smart_subtitles').get_presets(),
            'speechModel':load('local_speech').get_status(),
            'fontTemplates':load('smart_subtitles').get_font_templates(),
            'bgmTracks':get_bgm_tracks(),'detectionModes':load('smart_vision').get_detection_modes(),'effects':list_effects()}

    def video_importEffect(self,data):
        source=self._smart_helpers['_local_path'](data.get('path'),existing=True)
        return {'effect':import_effect(source,self.api.ctx.ffmpeg_tool())}

    def video_uploadEffect(self,data):
        name=data.get('name');encoded=data.get('base64')
        if not isinstance(name,str) or len(name)>240 or Path(name).suffix.lower() not in _TYPES:_error('拖入文件格式不支持')
        if not isinstance(encoded,str) or len(encoded)>70*1024**2:_error('拖入特效最大50MB，较大文件请点击选择文件')
        try:content=base64.b64decode(encoded,validate=True)
        except (ValueError,TypeError):_error('拖入文件数据无效')
        if not 0<len(content)<=50*1024**2:_error('拖入特效最大50MB')
        staging=_safe(_root()/'uploads');staging.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='effect-',dir=staging) as temporary:
            source=Path(temporary)/('asset'+Path(name).suffix.lower());source.write_bytes(content)
            item=import_effect(source,self.api.ctx.ffmpeg_tool())
        folder=_folder(item['id']);item.pop('path');item['name']=Path(name).stem[:120];item['sourceName']=name
        _write_meta(folder,item)
        return {'effect':resolve_effect(item['id'])}

    def video_removeEffect(self,data):
        item=resolve_effect(data.get('id'));folder=_folder(item['id']);item.pop('path');item['active']=False;_write_meta(folder,item)
        return {'removed':True,'id':item['id']}

    def video_getEffectTemplate(self,data):
        return {'version':1,'name':'明亮清晰','filters':[{'type':'brightness','value':.04},{'type':'contrast','value':1.1},{'type':'saturation','value':1.15}]}
