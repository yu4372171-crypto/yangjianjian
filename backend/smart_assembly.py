"""Bounded local shot assembly and framing; no media or model dependencies."""
import math
from collections import deque

DEFAULTS = {'montageMode':'sequential', 'shotDuration':3., 'fitMode':'contain', 'bgmDucking':False}


def options(data, partial=False):
    result = {key:data[key] for key in DEFAULTS if key in data} if partial else {**DEFAULTS, **{key:data[key] for key in DEFAULTS if key in data}}
    for key, choices in [('montageMode', ('sequential','balanced')), ('fitMode', ('contain','cover','blur'))]:
        if key in result and (not isinstance(result[key], str) or result[key] not in choices):
            raise ValueError('请选择有效的取材方式或画面适配方式')
    if 'shotDuration' in result:
        value=result['shotDuration']
        if type(value) not in (int,float) or not math.isfinite(value) or not .5 <= value <= 30:
            raise ValueError('单个镜头时长必须在 0.5–30 秒之间')
    if 'bgmDucking' in result and type(result['bgmDucking']) is not bool:
        raise ValueError('口播配乐避让必须是开启或关闭')
    return result


def pieces(kept, start, speed, config, target=0, overlap=0):
    """Skip on the kept clock, then alternate sources without reusing a frame.

    Shot duration is on the finished clock. Short targets divide the first
    round among all sources when feasible. Kept ranges remain separate so
    neither splitting nor slowdown can put a removed frame back into a shot.
    """
    remaining=[]
    for index, offset, length in kept:
        skipped=min(start,length);start-=skipped
        if length-skipped > .001:
            remaining.append((index,offset+skipped,length-skipped))
    if config['montageMode']=='sequential':
        return remaining
    grouped={}
    for index, offset, length in remaining:
        grouped.setdefault(index,deque()).append((offset,length))
    shot=config['shotDuration']
    if target and grouped:
        shot=min(shot,max(.5,target/len(grouped)+overlap))
    budget=shot*speed
    result=[]
    while any(grouped.values()):
        for index, ranges in grouped.items():
            if not ranges:continue
            offset,length=ranges.popleft()
            take=min(length,budget)
            result.append((index,offset,take))
            if length-take > .001:ranges.appendleft((offset+take,length-take))
            if len(result)>600:
                raise ValueError('均衡取材超过 600 个镜头，请增大单镜头时长或分批剪辑')
    return result


def fit_filter(width, height, mode, prefix='assembly'):
    contain=f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2'
    cover=f'scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={width}:{height}'
    if mode=='cover':return cover
    if mode=='blur':
        return (f'split=2[{prefix}bg][{prefix}fg];[{prefix}bg]{cover},gblur=sigma=20[{prefix}bed];'
            f'[{prefix}fg]{contain}[{prefix}front];[{prefix}bed][{prefix}front]overlay=(W-w)/2:(H-h)/2:shortest=1')
    return contain+f',pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black'


def summary(config):
    rows=[{'contain':'完整画面，留黑边','cover':'居中裁切，铺满画面','blur':'完整画面，模糊背景填充'}[config.get('fitMode','contain')]]
    if config.get('montageMode')=='balanced':
        rows.append(f'均衡轮换不同素材，单镜头最长 {config.get("shotDuration",3):g} 秒；按时间取材，不作语义精选。')
    if config.get('bgmDucking'):rows.append('有原声音量时自动压低配乐，安静处逐渐恢复；依据信号音量，不区分人声和其他声音。')
    return rows
