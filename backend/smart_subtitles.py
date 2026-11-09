"""Multilingual captions and ASS effects from real narration timestamps."""
import html
import math
import os
from pathlib import Path
import re
import unicodedata


_PRESETS = {
    'classic': {'name':'经典白字', 'color':'#FFFFFF', 'outline':2, 'shadow':1, 'bold':False},
    'yellow': {'name':'醒目黄字', 'color':'#FFD54A', 'outline':3, 'shadow':1, 'bold':True},
    'boxed': {'name':'背景字幕', 'color':'#FFFFFF', 'outline':6, 'shadow':0, 'bold':False},
    'neon': {'name':'霓虹发光', 'color':'#65FFF3', 'outline':3, 'shadow':2, 'bold':True},
    'fade': {'name':'淡入淡出', 'color':'#FFFFFF', 'outline':2, 'shadow':1, 'bold':False},
    'karaoke': {'name':'逐词高亮', 'color':'#FFFFFF', 'outline':2, 'shadow':1, 'bold':True},
    'cinema': {'name':'电影感白字', 'color':'#F4EFE2', 'outline':1, 'shadow':1, 'bold':False},
    'blue': {'name':'清爽蓝字', 'color':'#8DD8FF', 'outline':2, 'shadow':1, 'bold':True},
    'comic': {'name':'综艺大字', 'color':'#FFE34D', 'outline':5, 'shadow':3, 'bold':True},
    'pastel': {'name':'温柔粉字', 'color':'#FFC7DF', 'outline':2, 'shadow':1, 'bold':False},
    'pop': {'name':'弹入强调', 'color':'#FFFFFF', 'outline':3, 'shadow':2, 'bold':True},
    'slide': {'name':'轻盈上浮', 'color':'#FFFFFF', 'outline':2, 'shadow':1, 'bold':False},
    'lace': {'name':'花边字幕', 'color':'#FFF7E8', 'outline':2, 'shadow':1, 'bold':True},
}


def get_presets():
    return [{'id':key,'name':value['name'],'style':{k:v for k,v in value.items() if k!='name'}} for key,value in _PRESETS.items()]


def get_font_templates():
    fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    entries=[('modern','现代黑体','Microsoft YaHei','msyh.ttc',False),
        ('bold','醒目粗黑','Microsoft YaHei','msyhbd.ttc',True),
        ('traditional','书刊宋体','SimSun','simsun.ttc',False),
        ('handwritten','典雅楷体','KaiTi','simkai.ttf',False),
        ('formal','公文仿宋','FangSong','simfang.ttf',False),
        ('clean','清晰等线','DengXian','Deng.ttf',False),
        ('latin','英文简洁','Arial','arial.ttf',False),
        ('interface','国际通用','Segoe UI','segoeui.ttf',False)]
    return [{'id':key,'name':name,'style':{'font':font,'bold':bold,'size':0},'available':(fonts/file).is_file()} for key,name,font,file,bold in entries]


def _style(value):
    if value is None:value={}
    allowed={'preset','font','size','color','outlineColor','position','outline','shadow','bold'}
    if not isinstance(value,dict) or set(value)-allowed:
        raise ValueError('字幕样式参数无效')
    preset=value.get('preset','classic')
    if not isinstance(preset,str) or preset not in _PRESETS:
        raise ValueError('字幕预设无效')
    settings={'preset':preset,'font':'Microsoft YaHei','size':0,'outlineColor':'#141414','position':'bottom',
              **{k:v for k,v in _PRESETS[preset].items() if k!='name'},**value}
    font=settings['font']
    if not isinstance(font,str) or not font.strip() or len(font)>80 or re.search(r'[\x00-\x1f\x7f,{}\\]',font):
        raise ValueError('字幕字体名称无效')
    settings['font']=font.strip()
    for field in ('color','outlineColor'):
        color=settings[field]
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            raise ValueError('字幕颜色需要使用 #RRGGBB 格式')
    size=settings['size']
    if type(size) not in (int,float) or not math.isfinite(size) or (size!=0 and not 12<=size<=120):
        raise ValueError('字幕字号需要自动或 12–120')
    for field in ('outline','shadow'):
        number=settings[field]
        if type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=10:
            raise ValueError('字幕描边和阴影需要在 0–10 之间')
    if type(settings['bold']) is not bool:
        raise ValueError('字幕加粗参数无效')
    if not isinstance(settings['position'],str) or settings['position'] not in ('bottom','center','top'):
        raise ValueError('字幕位置无效')
    return settings


def _time(value,duration):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=duration+.15:
        raise ValueError('语音识别返回无效字幕时间，未生成成片')
    return min(float(value),duration)


def _text(value,strip=True):
    if not isinstance(value,str) or len(value)>4000:
        raise ValueError('语音识别返回无效字幕文字')
    value=re.sub(r'[\x00-\x1f\x7f]',' ',value)
    return value.strip() if strip else value.rstrip()


def _clock(value,precision=1000):
    ticks=round(value*precision)
    seconds,fraction=divmod(ticks,precision)
    minutes,seconds=divmod(seconds,60)
    hours,minutes=divmod(minutes,60)
    return (f'{hours:02d}:{minutes:02d}:{seconds:02d},{fraction:03d}' if precision==1000
            else f'{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}')


def _width(text):
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ('W','F') else 1 for char in text)


def _wrap(text,limit):
    # Space-delimited scripts wrap on word boundaries; CJK can wrap between
    # wide characters. Never cut Latin, Arabic or Indic words in half.
    tokens=[]
    current=''
    for char in text:
        if char.isspace() or unicodedata.east_asian_width(char) in ('W','F'):
            if current:tokens.append(current);current=''
            tokens.append(char)
        else:current+=char
    if current:tokens.append(current)
    lines=[];line=''
    for token in tokens:
        if line.strip() and _width(line+token)>limit and not token.isspace():
            lines.append(line.rstrip());line=token.lstrip()
        else:line+=token
    if line.strip():lines.append(line.rstrip())
    return '\n'.join(lines)


def _captions(transcript,duration,limit):
    segments=transcript.get('segments') if isinstance(transcript,dict) else None
    if not isinstance(segments,list) or not segments or len(segments)>10000:
        raise ValueError('未识别到可用口播或旁白，请确认视频包含清晰语音')
    rows=[];previous=-1.;maximum=min(48,limit*2)
    for segment in segments:
        if not isinstance(segment,dict):raise ValueError('语音识别返回无效字幕段落')
        start,end=_time(segment.get('start'),duration),_time(segment.get('end'),duration)
        text=_text(segment.get('text'))
        if end<=start or not text or start<previous-.1:
            raise ValueError('语音识别字幕顺序或时间无效')
        previous=start
        words=segment.get('words')
        if words is not None and (not isinstance(words,list) or len(words)>10000):
            raise ValueError('语音识别逐字时间无效')
        groups=[];word_end=start
        for word in words or []:
            if not isinstance(word,dict):raise ValueError('语音识别逐字时间无效')
            left,right=_time(word.get('start'),duration),_time(word.get('end'),duration)
            written=_text(word.get('text',word.get('word')),strip=False)
            if not written.strip():continue
            if right<=left or left<start-.15 or right>end+.15 or left<word_end-.02:
                raise ValueError('语音识别逐字时间超出段落或顺序无效')
            left=max(left,start,word_end);right=min(right,end)
            if right<=left:raise ValueError('语音识别逐字时间无效')
            aligned={'start':left,'end':right,'text':written}
            if groups and _width(groups[-1]['text']+written)<=maximum and left-groups[-1]['end']<.7:
                groups[-1]['text']+=written;groups[-1]['end']=right;groups[-1]['words'].append(aligned)
            else:
                groups.append({'start':left,'end':right,'text':written.lstrip(),'words':[aligned]})
            word_end=right
        if groups:rows.extend(groups)
        else:
            # No alignment means one real segment, never uniform invented
            # timings for smaller text fragments or karaoke syllables.
            rows.append({'start':start,'end':end,'text':text,'words':[]})
    for row in rows:row['text']=_wrap(row['text'],limit)
    if not rows:raise ValueError('未识别到可用口播或旁白')
    return rows


def _ass_color(color):
    return '&H00'+color[5:7]+color[3:5]+color[1:3]


def _ass_text(text):
    # Narration is plain text. Only this module may create ASS controls.
    return text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\n',r'\N')


def _karaoke(row,limit):
    if not row['words']:return _ass_text(row['text'])
    output=[];cursor=round(row['start']*100);line_width=0
    for index,word in enumerate(row['words']):
        start,end=round(word['start']*100),round(word['end']*100)
        if start>cursor:output.append(r'{\k'+str(start-cursor)+'}')
        written=word['text'].lstrip() if index==0 else word['text']
        width=_width(written)
        if line_width and line_width+width>limit:
            written='\n'+written.lstrip();line_width=0
        line_width+=_width(written.lstrip('\n'))
        output.append(r'{\kf'+str(max(0,end-start))+'}'+_ass_text(written))
        cursor=end
    return ''.join(output)


def _lace_path(row,width,height,bottom_margin,font_size,position='bottom'):
    """Layer a scalloped ribbon behind the real narration caption."""
    plain=row['text'].replace('\n',' ')
    text_width=max(18,min(width-20,round(_width(plain)*font_size*.53)))
    ribbon_width=text_width+max(16,round(font_size*.5))
    ribbon_height=max(14,round(font_size*.46))
    # ASS positions are measured from the chosen alignment edge. Keep the
    # ribbon behind the readable caption for every top/center/bottom setting.
    center_y={'top':max(ribbon_height,max(10,round(height*.045))+font_size//2),
              'center':height//2,
              'bottom':max(ribbon_height,height-bottom_margin-font_size//2)}[position]
    left=max(2,(width-ribbon_width)//2)
    step=max(10,round(ribbon_width/18))
    top=center_y-ribbon_height//2
    bottom=center_y+ribbon_height//2
    # ASS vector drawings require a move followed by explicit line segments.
    # Absolute x/y coordinates keep the ribbon centered over the real caption,
    # while the repeated scallops give a visible lace-like edge.
    path=[f'm {left+4} {top}']
    for index in range(0,ribbon_width+1,step):
        x=left+min(index,ribbon_width)
        peak=top-(4 if (index//step)%2 else 0)
        path.append(f'l {x} {peak}')
    path.append(f'l {left+ribbon_width} {bottom}')
    for index in range(ribbon_width,-1,-step):
        x=left+index
        dip=bottom+(4 if (index//step)%2 else 0)
        path.append(f'l {x} {dip}')
    path.append('l '+str(left)+' '+str(top))
    return (r'{\an7\pos(0,0)\p1\bord0\shad0\1c&H8C4AFF&\3c&H8C4AFF&'
            r'\t(0,1200,\1c&H5AD8D1&\3c&H5AD8D1&)}'
            +' '.join(path)+r'{\p0}')


def prepare_subtitles(transcript,duration,width,height,folder,style=None,reserve_bottom=False):
    settings=_style(style)
    if type(reserve_bottom) is not bool:
        raise ValueError('字幕避让参数无效')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
        raise ValueError('成片时长无效，无法同步字幕')
    if type(width) is not int or type(height) is not int or width<2 or height<2:
        raise ValueError('成片画面尺寸无效')
    font_size=settings['size'] or max(16,min(90,round(height*.052)))
    margin=max(8,round(width*.045))
    # Fixed compliance text occupies the lowest part of the frame. Keep
    # narration clear of it instead of stacking two readable lines together.
    bottom_margin=round(height*.18) if reserve_bottom and settings['position']=='bottom' else max(10,round(height*.045))
    limit=max(12,min(44,int((width-2*margin)/(font_size*.55))))
    rows=_captions(transcript,float(duration),limit)
    srt='\n\n'.join(f'{i+1}\n{_clock(row["start"])} --> {_clock(row["end"])}\n'+html.escape(row['text'],quote=False) for i,row in enumerate(rows))+'\n'
    preset=settings['preset'];alignment={'bottom':2,'center':5,'top':8}[settings['position']]
    primary=_ass_color('#FFE34D' if preset=='karaoke' else settings['color'])
    secondary=_ass_color(settings['color'])
    outline=_ass_color(settings['outlineColor']);border=3 if preset=='boxed' else 1
    header=(f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Default,{settings["font"]},{font_size:g},{primary},{secondary},{outline},&H60000000,{-1 if settings["bold"] else 0},0,0,0,100,100,0,0,{border},{settings["outline"]:g},{settings["shadow"]:g},{alignment},{margin},{margin},{bottom_margin},1\n\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    events=[]
    for row in rows:
        written=_karaoke(row,limit) if preset=='karaoke' else _ass_text(row['text'])
        if preset=='fade':
            fade=min(180,max(0,round((row['end']-row['start'])*500)))
            written=r'{\fad('+str(fade)+','+str(fade)+')}'+written
        if preset=='pop':
            animation=min(180,round((row['end']-row['start'])*500))
            written=r'{\fscx75\fscy75\t(0,'+str(animation)+r',\fscx100\fscy100)}'+written
        if preset=='slide':
            animation=min(240,round((row['end']-row['start'])*500))
            y={'bottom':height-bottom_margin,'center':height//2,'top':max(10,round(height*.045))}[settings['position']]
            written=r'{\move('+f'{width//2},{y+10},{width//2},{y},0,{animation}'+r')}'+written
        if preset=='lace':
            lace_border=_lace_path(row,width,height,bottom_margin,font_size,settings['position'])
        else:
            lace_border=''
        prefix=f'{_clock(row["start"],100)},{_clock(row["end"],100)},Default,,0,0,0,,'
        if preset=='lace':
            events.append('Dialogue: 0,'+_clock(row['start'],100)+','+_clock(row['end'],100)
                          +',Default,lace-border,0,0,0,,'+lace_border)
        if preset=='neon':
            glow=r'{\blur4\bord7\shad0\alpha&H88&\3c'+_ass_color(settings['color'])+'&}'
            events.append('Dialogue: 0,'+prefix+glow+written)
        events.append('Dialogue: 1,'+prefix+written)
    # All option, text and timing validation occurs before either sidecar write.
    folder=Path(folder)
    srt_path,ass_path=folder/'subtitles.srt',folder/'subtitles.ass'
    srt_path.write_text(srt,encoding='utf-8-sig')
    ass_path.write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
    return {'srtPath':str(srt_path),'assPath':str(ass_path),'count':len(rows),'segments':rows,
            'language':transcript.get('language',''),'style':settings}
