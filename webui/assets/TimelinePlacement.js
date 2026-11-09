const EPS=1e-7;

export function frameTime(value,fps=30){
  const rate=Math.max(1,Number(fps)||30);
  return Math.round((Number(value)||0)*rate)/rate;
}

export function clampFrame(value,minimum,maximum,fps=30){
  return frameTime(Math.max(minimum,Math.min(maximum,value)),fps);
}

export function collectAnchors(items,excludeIds=[],extra=[]){
  const excluded=new Set(excludeIds),anchors=new Set([0,...extra]);
  for(const item of items){
    if(excluded.has(item.id))continue;
    const start=Number(item.start)||0;
    const duration=item.end!==undefined?Number(item.end)-start:Number(item.duration)||0;
    anchors.add(start);
    anchors.add(start+duration);
    for(const frames of Object.values(item.keyframes||{})){
      for(const keyframe of frames||[])anchors.add(start+(Number(keyframe.time)||0));
    }
  }
  return [...anchors].filter(Number.isFinite).sort((a,b)=>a-b);
}

export function nearestSnap(value,anchors,threshold,fps=30){
  const at=frameTime(value,fps),tolerance=Math.max(0,Number(threshold)||0);
  let answer=at,distance=tolerance,anchor=null;
  for(const candidate of anchors||[]){
    const current=Math.abs(frameTime(candidate,fps)-at);
    if(current<=distance){
      distance=current;
      answer=frameTime(candidate,fps);
      anchor=answer;
    }
  }
  return {time:answer,anchor,distance};
}

export function overlappingItems(items,{trackId,start,end,excludeIds=[],allowOverlap=false}){
  if(allowOverlap)return [];
  const excluded=new Set(excludeIds),from=Number(start),to=Number(end);
  return items.filter(item=>{
    if(excluded.has(item.id)||item.trackId!==trackId)return false;
    const itemStart=Number(item.start)||0;
    const itemEnd=item.end!==undefined?Number(item.end):itemStart+(Number(item.duration)||0);
    return itemStart<to-EPS&&itemEnd>from+EPS;
  });
}

export function placementPreview({items,trackId,start,end,excludeIds=[],main=false,trackLocked=false}){
  if(trackLocked)return {status:'blocked',message:'轨道已锁定',conflicts:[]};
  const conflicts=overlappingItems(items,{trackId,start,end,excludeIds,allowOverlap:!main});
  if(conflicts.length&&main)return {status:'insert',message:'将插入并后移后续片段',conflicts};
  return {status:'valid',message:'可放置',conflicts};
}

export function mainInsertIndex(rows,time){
  const midpoint=Number(time)||0;
  const index=rows.findIndex(row=>midpoint<row.start+(row.end-row.start)/2);
  return index<0?rows.length:index;
}
