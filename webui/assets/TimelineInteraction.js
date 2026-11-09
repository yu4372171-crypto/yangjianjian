import { frameTime } from './TimelinePlacement.js';

const EPS=1e-7;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

export function itemSpan(item){
  const start=Number(item?.start)||0;
  const explicitDuration=Number(item?.duration);
  const trimStart=Number(item?.trimStart);
  const trimEnd=Number(item?.trimEnd);
  const speed=Number(item?.speed)||1;
  const sourceDuration=Number.isFinite(trimStart)&&Number.isFinite(trimEnd)&&speed>0
    ?Math.max(0,(trimEnd-trimStart)/speed)
    :0;
  const duration=Number.isFinite(explicitDuration)?Math.max(0,explicitDuration):sourceDuration;
  const end=item?.end!==undefined?Number(item.end):start+duration;
  return {start,end,duration:Math.max(0,end-start)};
}

export function selectionSpan(items){
  const spans=(items||[]).map(row=>itemSpan(row?.item||row)).filter(span=>span.duration>0);
  if(!spans.length)return null;
  const start=Math.min(...spans.map(span=>span.start));
  const end=Math.max(...spans.map(span=>span.end));
  return {start,end,duration:end-start};
}

export function selectedItems(draft,selections,lockResolver=()=>false){
  const buckets={clip:'clips',overlay:'overlays',text:'texts',audio:'audioClips'};
  return (selections||[]).flatMap(selection=>{
    const rows=draft?.[buckets[selection.kind]]||[];
    const item=rows.find(row=>row.id===selection.id);
    return item&&!lockResolver(item)?[{kind:selection.kind,item}] : [];
  });
}

export function marqueeIntersects(rect,box){
  return !(rect.right<box.left||rect.left>box.right||rect.bottom<box.top||rect.top>box.bottom);
}

export function autoScrollSpeed(pointerX,left,right,{edge=52,max=22}={}){
  const distance=Math.max(1,Number(edge)||52),speed=Math.max(1,Number(max)||22);
  if(pointerX<left+distance)return -speed*(1-clamp((pointerX-left)/distance,0,1));
  if(pointerX>right-distance)return speed*(1-clamp((right-pointerX)/distance,0,1));
  return 0;
}

export function resizeSelection(items,edge,targetTime,fps=30,minDuration=.05){
  const span=selectionSpan(items);
  if(!span||!['left','right'].includes(edge))return null;
  const minimum=Math.max(minDuration,frameTime(minDuration,fps));
  let start=span.start,end=span.end;
  if(edge==='left')start=Math.min(frameTime(targetTime,fps),end-minimum);
  else end=Math.max(frameTime(targetTime,fps),start+minimum);
  const oldDuration=Math.max(EPS,span.end-span.start),newDuration=end-start;
  const scale=newDuration/oldDuration;
  return items.map(row=>{
    const item=row?.item||row,current=itemSpan(item),offset=current.start-span.start;
    return {
      kind:row?.kind||'',
      id:item.id,
      start:frameTime(start+offset*scale,fps),
      end:frameTime(start+(offset+current.duration)*scale,fps)
    };
  });
}
