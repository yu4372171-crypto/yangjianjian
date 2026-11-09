// Independent timeline state. All edit functions return a validated new document.
import { ease as curveEase, normalizeEasing } from './TimelineCurve.js';

export const LIMITS={assets:100,clips:200,overlays:20,texts:200,audioAssets:50,audioClips:50,duration:86400,minClip:.05};
const RATIOS=['自动','16:9','9:16','1:1','4:3','3:4','21:9'];
const RESOLUTIONS=['原画','720p','1080p','2K','4K'];
const FPS=[24,25,30,50,60],EPS=1e-7;
export const TRANSITIONS=[{value:'none',label:'无转场'},{value:'fade',label:'淡入淡出'},{value:'dissolve',label:'溶解'},{value:'wipeleft',label:'向左擦除'},{value:'wiperight',label:'向右擦除'},{value:'slideleft',label:'向左滑动'},{value:'slideright',label:'向右滑动'}];
const fail=message=>{throw Error(message);};
const array=(value,maximum,label)=>{if(!Array.isArray(value)||value.length>maximum)fail(`${label}数量无效，最多${maximum}个`);return value;};
function number(value,min,max,label){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)fail(`${label}需要在${min}–${max}之间`);return value;}
function identifier(value){if(typeof value!=='string'||!value||value.length>100||!/^[\w-]+$/.test(value))fail('片段或素材编号无效');return value;}
function absolutePath(value){
  if(typeof value!=='string'||!value||value.length>32000||/[\x00-\x1f]/.test(value)||value.includes('://')||/^[\\/]{2}/.test(value)||!(/^[a-z]:[\\/]/i.test(value)||value.startsWith('/')))fail('请选择完整的本地文件路径');
  return value;
}
const key=path=>String(path).replaceAll('\\','/').toLowerCase();
const basename=path=>String(path).split(/[\\/]/).pop();
let sequence=0;
export function uid(prefix='tl'){return `${prefix}_${Date.now().toString(36)}_${(++sequence).toString(36)}_${Math.random().toString(36).slice(2,8)}`;}
export function newDraft(){return {version:3,assets:[],clips:[],overlays:[],texts:[],audioAssets:[],audioClips:[],tracks:[],markers:[],music:null,settings:{ratio:'自动',resolution:'原画',fps:30},output:{folder:'',filename:'时间线剪辑.mp4'}};}
export function clipDuration(clip){return clip.duration??(clip.trimEnd-clip.trimStart)/clip.speed;}
export function totalDuration(draftOrClips){if(!Array.isArray(draftOrClips)&&draftOrClips.version>=2)return Math.max(0,...allItems(draftOrClips).map(({item})=>(item.start||0)+itemDuration(item)));return layout(draftOrClips).at(-1)?.end||0;}
export function layout(draftOrClips,fps=30){const clips=Array.isArray(draftOrClips)?draftOrClips:draftOrClips.clips;fps=Array.isArray(draftOrClips)?fps:draftOrClips.settings?.fps||fps;const free=!Array.isArray(draftOrClips)&&draftOrClips.version>=2;let position=0;return clips.map((clip,index)=>{const start=free?clip.start:position,duration=clipDuration(clip),join=clip.transitionToNext,requested=join?.type&&join.type!=='none'?join.duration:0,overlap=index<clips.length-1?Math.max(0,Math.floor((Math.min(requested||0,duration*.5,clipDuration(clips[index+1])*.5)+EPS)*fps)/fps):0,end=start+duration;position=end-overlap;return {...clip,index,start,end,duration,overlap:free?Math.min(overlap,Math.max(0,end-(clips[index+1]?.start??end))):overlap};});}
export function locate(clips,time,fps=30){
  const list=Array.isArray(clips)?clips:clips.clips;
  if(!list.length)return null;
  const rows=layout(clips,fps),total=Math.max(...rows.map(r=>r.end));
  const at=Math.max(0,Math.min(total,Number.isFinite(time)?time:0));
  const free=!Array.isArray(clips)&&clips.version>=2,row=rows.find(item=>(!free||at>=item.start)&&at<item.end-EPS)||(free?null:rows.at(-1));if(!row)return null;const clip=list[row.index];
  return {...row,clip,sourceTime:sourceTimeAt(clip,Math.max(0,at-row.start))};
}
function unique(rows,label){const ids=new Set();for(const row of rows){if(ids.has(row.id))fail(`${label}编号重复`);ids.add(row.id);}}
function normalizeAsset(value){
  if(!value||typeof value!=='object')fail('素材信息无效');
  const path=absolutePath(value.path),duration=number(value.duration??(value.kind==='image'?5:undefined),.001,864000,'素材时长');
  const width=number(value.width,1,32768,'素材宽度'),height=number(value.height,1,32768,'素材高度');
  if(!Number.isInteger(width)||!Number.isInteger(height)||typeof value.hasAudio!=='boolean')fail('素材画面或声音信息无效');
  const preview=value.preview??'';
  if(typeof preview!=='string'||preview.length>1500000||(preview&&!/^data:image\/(jpeg|jpg|png|webp);base64,/.test(preview)))fail('素材缩略图无效');
  return {id:identifier(value.id),path,name:typeof value.name==='string'&&value.name?value.name.slice(0,300):basename(path),duration,width,height,hasAudio:value.hasAudio,preview,...(value.kind==='image'?{kind:'image'}:{})};
}
function normalizeClip(value,assets,overlay=false){
  if(!value||typeof value!=='object')fail('片段信息无效');
  const asset=assets.get(value.assetId);if(!asset)fail('片段对应素材不存在，请重新导入');
  const speed=number(value.speed??1,.25,4,'播放倍速'),trimStart=number(value.trimStart??0,0,asset.duration,'裁剪入点'),trimEnd=number(value.trimEnd??asset.duration,0,asset.duration,'裁剪出点');
  if((trimEnd-trimStart)/speed<LIMITS.minClip-EPS)fail('裁剪后片段至少需要0.05秒，出点必须大于入点');
  if(value.muted!==undefined&&typeof value.muted!=='boolean')fail('静音选项无效');
  if(value.hidden!==undefined&&typeof value.hidden!=='boolean')fail('显示选项无效');
  const clip={id:identifier(value.id),assetId:asset.id,trimStart,trimEnd,speed,volume:number(value.volume??(overlay?0:1),0,4,'片段音量'),muted:value.muted??false};
  if(!overlay){const transition=value.transitionToNext??{type:'none',duration:.4};if(!transition||!TRANSITIONS.some(item=>item.value===transition.type))fail('转场类型无效');clip.transitionToNext={type:transition.type,duration:transition.type==='none'?.4:number(transition.duration??.4,.1,2,'转场时长')};}
  if(overlay){
    Object.assign(clip,{hidden:value.hidden??false,start:number(value.start??0,0,LIMITS.duration,'叠加开始时间'),x:number(value.x??.65,0,1,'画面水平位置'),y:number(value.y??.65,0,1,'画面垂直位置'),width:number(value.width??.3,.02,1,'画面宽度'),height:number(value.height??.3,.02,1,'画面高度'),opacity:number(value.opacity??1,0,1,'画面透明度')});
    if(clip.x+clip.width>1+EPS||clip.y+clip.height>1+EPS)fail('画中画位置和大小超出画面范围');
  }
  return clip;
}
function normalizeText(value){
  if(!value||typeof value!=='object'||typeof value.text!=='string'||value.text.length>2000)fail('文字内容无效，最多2000字');
  const start=number(value.start??0,0,LIMITS.duration,'文字开始时间'),end=number(value.end,0,LIMITS.duration,'文字结束时间');
  if(end-start<LIMITS.minClip-EPS)fail('文字结束时间需要晚于开始时间至少0.05秒');
  const font=value.font??'Microsoft YaHei';if(typeof font!=='string'||!font.trim()||font.length>80||/[\x00-\x1f\x7f,{}\\]/.test(font))fail('文字字体名称无效');
  const color=value.color??'#FFFFFF';if(typeof color!=='string'||!/^#[0-9a-f]{6}$/i.test(color))fail('文字颜色需要使用#RRGGBB格式');
  const position=value.position??'bottom';if(!['top','center','bottom'].includes(position))fail('文字位置无效');
  if(value.hidden!==undefined&&typeof value.hidden!=='boolean')fail('显示选项无效');
  return {id:identifier(value.id),text:value.text,start,end,font:font.trim(),size:number(value.size??48,12,120,'文字字号'),color,position,hidden:value.hidden??false};
}
function normalizeAudioAsset(value){
  if(!value||typeof value!=='object')fail('音频素材信息无效');
  const path=absolutePath(value.path),duration=number(value.duration,.001,864000,'音频素材时长');
  const extra={};
  if(value.sourceAssetId!==undefined)extra.sourceAssetId=identifier(value.sourceAssetId);
  if(value.sourceStart!==undefined)extra.sourceStart=number(value.sourceStart,0,LIMITS.duration,'源音频开始位置');
  if(value.sourceEnd!==undefined)extra.sourceEnd=number(value.sourceEnd,0,LIMITS.duration,'源音频结束位置');
  return {id:identifier(value.id),path,name:typeof value.name==='string'&&value.name?value.name.slice(0,300):basename(path),duration,...extra};
}
function normalizeAudioClip(value,assets){
  const {transitionToNext,...clip}=normalizeClip({...value,transitionToNext:undefined},assets);
  return {...clip,start:number(value.start??0,0,LIMITS.duration,'音频开始时间')};
}
export function normalizeDraft(raw){
  if(!raw||typeof raw!=='object'||Array.isArray(raw)||(raw.version!==undefined&&![1,2,3].includes(raw.version)))fail('时间线草稿格式无效');
  const base=newDraft(),assets=array(raw.assets??[],LIMITS.assets,'素材').map(normalizeAsset);unique(assets,'素材');
  if(new Set(assets.map(asset=>key(asset.path))).size!==assets.length)fail('素材路径重复');
  const index=new Map(assets.map(asset=>[asset.id,asset]));
  const clips=array(raw.clips??[],LIMITS.clips,'主轨片段').map(clip=>normalizeClip(clip,index));unique(clips,'主轨片段');
  if(totalDuration({clips,settings:raw.settings})>LIMITS.duration+EPS)fail('时间线总时长不能超过24小时');
  const overlays=array(raw.overlays??[],LIMITS.overlays,'叠加片段').map(clip=>clip.type==='solid'?normalizeSolid(clip):normalizeClip(clip,index,true));unique(overlays,'叠加片段');
  const texts=array(raw.texts??[],LIMITS.texts,'文字').map(normalizeText);unique(texts,'文字');
  if(clips.length+overlays.length+texts.length>200)fail('工程最多支持 200 个视觉图层（主轨、叠加和文字合计）');
  const audioAssets=array(raw.audioAssets??[],LIMITS.audioAssets,'音频素材').map(normalizeAudioAsset);unique(audioAssets,'音频素材');
  if(new Set(audioAssets.map(asset=>key(asset.path))).size!==audioAssets.length)fail('音频素材路径重复');
  const audioIndex=new Map(audioAssets.map(asset=>[asset.id,asset]));
  const audioClips=array(raw.audioClips??[],LIMITS.audioClips,'音频片段').map(clip=>normalizeAudioClip(clip,audioIndex));unique(audioClips,'音频片段');
  const settings={...base.settings,...raw.settings};
  if(!RATIOS.includes(settings.ratio)||!RESOLUTIONS.includes(settings.resolution)||!FPS.includes(settings.fps))fail('画布比例、分辨率或帧率无效');
  const output={...base.output,...raw.output};if(typeof output.folder!=='string'||typeof output.filename!=='string')fail('输出文件位置无效');
  let music=null;
  if(raw.music!==null&&raw.music!==undefined){
    const value=raw.music;if(!value||typeof value!=='object')fail('配乐设置无效');
    const path=value.path?absolutePath(value.path):'',trackId=value.trackId??'';
    if(typeof trackId!=='string'||(!path&&!trackId)||trackId.length>100)fail('请选择配乐文件或内置音乐');
    if(typeof (value.loop??true)!=='boolean')fail('配乐循环选项无效');
    music={path,trackId,volume:number(value.volume??.18,0,1,'配乐音量'),loop:value.loop??true};
  }
  const result={version:raw.version>=2?3:1,assets,clips,overlays,texts,audioAssets,audioClips,music,settings:{ratio:settings.ratio,resolution:settings.resolution,fps:settings.fps},output};
  return raw.version>=2?normalizeV2(raw,result):result;
}
const copy=draft=>JSON.parse(JSON.stringify(draft));
function edit(draft,action){const next=copy(draft);action(next);return normalizeDraft(next);}
const requireIndex=(rows,id,label)=>{const index=rows.findIndex(row=>row.id===id);if(index<0)fail(`${label}已不存在，请重新选择`);return index;};
export function addAsset(draft,metadata){
  if(!metadata||typeof metadata.path!=='string')fail('素材路径无效');
  const existing=draft.assets.find(asset=>key(asset.path)===key(metadata.path));
  if(existing){const fresh=normalizeAsset({...metadata,id:existing.id}),changed=['duration','width','height','hasAudio'].some(field=>fresh[field]!==existing[field]);if(changed&&[...draft.clips,...draft.overlays].some(clip=>clip.assetId===existing.id))fail('素材已变化，请先移除对应片段再重新导入');return edit(draft,next=>{next.assets[next.assets.findIndex(row=>row.id===existing.id)]=fresh;});}
  return edit(draft,next=>next.assets.push({...metadata,id:metadata.id||uid('asset')}));
}
export function appendClip(draft,assetId,index=draft.clips.length){
  return edit(draft,next=>{const asset=next.assets.find(asset=>asset.id===assetId);if(!asset)fail('请选择可用的视频素材');
    next.clips.splice(Math.max(0,Math.min(next.clips.length,Math.trunc(index))),0,{id:uid('clip'),assetId,trimStart:0,trimEnd:asset.duration,speed:1,volume:1,...(next.version>=2?{start:totalDuration(next),trackId:'main'}:{})});});
}
export function updateClip(draft,id,patch){return edit(draft,next=>{const index=requireIndex(next.clips,id,'片段');next.clips[index]={...next.clips[index],...patch,id,assetId:next.clips[index].assetId};});}
export function removeClip(draft,id){return edit(draft,next=>next.clips.splice(requireIndex(next.clips,id,'片段'),1));}
export function moveClip(draft,id,toIndex){return edit(draft,next=>{if(!Number.isInteger(toIndex))fail('片段排序位置无效');const index=requireIndex(next.clips,id,'片段'),[clip]=next.clips.splice(index,1);next.clips.splice(Math.max(0,Math.min(next.clips.length,toIndex)),0,clip);});}
export function duplicateClip(draft,id){return edit(draft,next=>{const index=requireIndex(next.clips,id,'片段');next.clips.splice(index+1,0,{...next.clips[index],id:uid('clip')});});}
export function splitAt(draft,time,clipId){
  number(time,0,LIMITS.duration,'分割时间');
  const position=clipId?layout(draft).find(clip=>clip.id===clipId):locate(draft,time);
  if(!position||time-position.start<LIMITS.minClip-EPS||position.end-time<LIMITS.minClip-EPS)fail('请在片段内部定位后分割，两侧至少各保留0.05秒');
  const next=edit(draft,next=>{const index=position.index,clip=next.clips[index],sourceTime=clip.trimStart+(time-position.start)*clip.speed;next.clips.splice(index,1,{...clip,trimEnd:sourceTime,transitionToNext:{type:'none',duration:.4}},{...clip,id:uid('clip'),trimStart:sourceTime});});
  if(Math.abs(totalDuration(next)-totalDuration(draft))>EPS)fail('此位置分割会改变转场与后续时间，请给转场两侧保留足够时长，或先移除该转场再分割');
  return next;
}
export function addOverlay(draft,assetId,start=0){return edit(draft,next=>{const asset=next.assets.find(a=>a.id===assetId);if(!asset)fail('叠加素材不存在');next.overlays.push({id:uid('overlay'),assetId,trimStart:0,trimEnd:asset.duration,speed:1,volume:0,start,x:.65,y:.65,width:.3,height:.3,opacity:1});});}
export function updateOverlay(draft,id,patch){return edit(draft,next=>{const index=requireIndex(next.overlays,id,'叠加片段');next.overlays[index]={...next.overlays[index],...patch,id,assetId:next.overlays[index].assetId};});}
export function removeOverlay(draft,id){return edit(draft,next=>next.overlays.splice(requireIndex(next.overlays,id,'叠加片段'),1));}
export function addText(draft,values={}){return edit(draft,next=>{const start=values.start??0;next.texts.push({text:'添加标题',start,end:Math.max(start+.05,Math.min(totalDuration(next)||3,start+3)),font:'Microsoft YaHei',size:48,color:'#FFFFFF',position:'bottom',...values,id:uid('text')});});}
export function updateText(draft,id,patch){return edit(draft,next=>{const index=requireIndex(next.texts,id,'文字');next.texts[index]={...next.texts[index],...patch,id};});}
export function removeText(draft,id){return edit(draft,next=>next.texts.splice(requireIndex(next.texts,id,'文字'),1));}
export function addAudioAsset(draft,metadata){
  if(!metadata||typeof metadata.path!=='string')fail('音频素材路径无效');
  const existing=(draft.audioAssets||[]).find(asset=>key(asset.path)===key(metadata.path));
  if(existing){const fresh=normalizeAudioAsset({...metadata,id:existing.id});if(fresh.duration!==existing.duration&&draft.audioClips.some(clip=>clip.assetId===existing.id))fail('音频素材已变化，请先移除对应片段再重新导入');return edit(draft,next=>{next.audioAssets[next.audioAssets.findIndex(row=>row.id===existing.id)]=fresh;});}
  return edit(draft,next=>next.audioAssets.push({...metadata,id:metadata.id||uid('audioasset')}));
}
export function appendAudioClip(draft,assetId,start=0){return edit(draft,next=>{const asset=next.audioAssets.find(row=>row.id===assetId);if(!asset)fail('请选择可用的音频素材');next.audioClips.push({id:uid('audio'),assetId,start,trimStart:0,trimEnd:asset.duration,speed:1,volume:1,muted:false});});}
export function updateAudioClip(draft,id,patch){return edit(draft,next=>{const index=requireIndex(next.audioClips,id,'音频片段');next.audioClips[index]={...next.audioClips[index],...patch,id,assetId:next.audioClips[index].assetId};});}
export function removeAudioClip(draft,id){return edit(draft,next=>next.audioClips.splice(requireIndex(next.audioClips,id,'音频片段'),1));}
export function duplicateAudioClip(draft,id){return edit(draft,next=>{const index=requireIndex(next.audioClips,id,'音频片段');next.audioClips.splice(index+1,0,{...next.audioClips[index],id:uid('audio')});});}
export function splitAudioAt(draft,time,id){
  number(time,0,LIMITS.duration,'分割时间');
  const clip=draft.audioClips.find(row=>row.id===id);
  if(!clip||time-clip.start<LIMITS.minClip-EPS||clip.start+clipDuration(clip)-time<LIMITS.minClip-EPS)fail('请在音频片段内部定位后分割，两侧至少各保留0.05秒');
  return edit(draft,next=>{const index=requireIndex(next.audioClips,id,'音频片段'),sourceTime=clip.trimStart+(time-clip.start)*clip.speed;next.audioClips.splice(index,1,{...clip,trimEnd:sourceTime},{...clip,id:uid('audio'),start:time,trimStart:sourceTime});});
}
function filename(value){if(!value||value.length>200||!/^.+\.mp4$/i.test(value)||/[<>:"/\\|?*\x00-\x1f\x7f]/.test(value)||/[. ]$/.test(value)||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(value))fail('请输入有效的MP4文件名，不得含路径或特殊字符');return value;}
export function buildExport(raw){
  if(raw?.version>=2)return buildExportV2(normalizeDraft(raw));
  const draft=normalizeDraft(raw),duration=totalDuration(draft);if(!draft.clips.length)fail('请先把视频添加到主视频轨');
  const assets=new Map(draft.assets.map(asset=>[asset.id,asset]));
  const source=clip=>({path:assets.get(clip.assetId).path,trimStart:clip.trimStart,trimEnd:clip.trimEnd,speed:clip.speed,volume:clip.muted?0:clip.volume});
  const overlays=draft.overlays.filter(clip=>!clip.hidden).map(clip=>{if(clip.start>=duration-EPS)fail('叠加视频开始时间超过成片时长，请调整范围');return {...source(clip),start:clip.start,x:clip.x,y:clip.y,width:clip.width,height:clip.height,opacity:clip.opacity};});
  const texts=draft.texts.filter(text=>!text.hidden).map(({id,hidden,...text})=>{if(!text.text.trim())fail('文字内容不能为空，请填写文字或删除该条');if(text.start>=duration-EPS)fail('文字开始时间超过成片时长，请调整范围');return {...text,end:Math.min(duration,text.end)};});
  const audioAssets=new Map(draft.audioAssets.map(asset=>[asset.id,asset]));
  const audioClips=draft.audioClips.map(clip=>{if(clip.start>=duration-EPS)fail('音频开始时间超过成片时长，请调整范围');return {path:audioAssets.get(clip.assetId).path,trimStart:clip.trimStart,trimEnd:clip.trimEnd,start:clip.start,speed:clip.speed,volume:clip.muted?0:clip.volume};});
  const folder=absolutePath(draft.output.folder.trim()),name=filename(draft.output.filename.trim());
  const separator=folder.includes('\\')?'\\':'/';
  return {clips:draft.clips.map((clip,index)=>({...source(clip),...(index<draft.clips.length-1?{transitionToNext:{...clip.transitionToNext}}:{})})),overlays,texts,audioClips,music:draft.music?{...draft.music}:null,...draft.settings,output:folder.replace(/[\\/]+$/,'')+separator+name};
}
function signature(draft){return JSON.stringify({...draft,assets:draft.assets.map(({preview,...asset})=>asset)});}
export class TimelineHistory{
  constructor(initial,limit=80){this.limit=Math.max(1,Math.min(100,limit));this.reset(initial);}
  reset(next){this.current=normalizeDraft(next);this.past=[];this.future=[];return copy(this.current);}
  commit(next){const value=normalizeDraft(next);if(signature(value)!==signature(this.current)){this.past.push(copy(this.current));if(this.past.length>this.limit)this.past.shift();this.future=[];}this.current=value;return copy(value);}
  get canUndo(){return this.past.length>0;}
  get canRedo(){return this.future.length>0;}
  undo(){if(this.canUndo){this.future.push(copy(this.current));this.current=this.past.pop();}return copy(this.current);}
  redo(){if(this.canRedo){this.past.push(copy(this.current));this.current=this.future.pop();}return copy(this.current);}
}

// V2 is an independent scene document. Legacy drafts remain on their original clock.
export const KEYFRAME_PROPERTIES=['x','y','scale','opacity','rotation','volume'];
export const EASINGS=['linear','hold','ease-in','ease-out','ease-in-out','bezier'];
export const MASKS=['none','rect','circle','ellipse','rounded','diamond','heart','star','split','cinematic-bars'];
const DEFAULT_EFFECTS={brightness:0,contrast:1,saturation:1,hue:0,blur:0,grayscale:false,sepia:false};
const DEFAULT_CROP={x:0,y:0,width:1,height:1};
const BUCKETS={clip:'clips',overlay:'overlays',text:'texts',audio:'audioClips'};
const color=(value,fallback='#000000')=>typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value)?value:fallback;
const bool=(value,fallback=false)=>value===undefined?fallback:typeof value==='boolean'?value:fail('开关值无效');
export function allItems(draft){return Object.entries(BUCKETS).flatMap(([kind,bucket])=>(draft[bucket]||[]).map(item=>({kind,item})));}
export function itemDuration(item){return item.end!==undefined?item.end-item.start:clipDuration(item);}
export function sourceTimeAt(item,local,fps=30){if(item.freezeAt!==undefined&&item.freezeAt!==null)return item.freezeAt;if(item.freezeTail)local=Math.min(local,Math.max(0,itemDuration(item)-item.freezeTail-1/fps));return item.reverse?Math.max(item.trimStart,item.trimEnd-local*item.speed):Math.min(item.trimEnd,item.trimStart+local*item.speed);}
function normalizeSolid(value){return {id:identifier(value.id),type:'solid',start:number(value.start??0,0,LIMITS.duration,'贴纸开始时间'),duration:number(value.duration??3,.05,LIMITS.duration,'贴纸时长'),color:color(value.color,'#7785ff'),volume:0,muted:true,hidden:bool(value.hidden),x:0,y:0,width:1,height:1,opacity:1};}
function normalizeVisual(value,kind){
 const t=value.transform||{},fallback=kind==='overlay'?{x:value.x??.65,y:value.y??.65,width:value.width??.3,height:value.height??.3}:kind==='text'?{x:.05,y:value.position==='top'?.05:value.position==='center'?.43:.83,width:.9,height:.12}:{x:0,y:0,width:1,height:1};
 const crop={...DEFAULT_CROP,...t.crop};for(const key of ['x','y','width','height'])crop[key]=number(crop[key],key==='width'||key==='height'?.001:0,1,'画面裁剪');if(crop.x+crop.width>1+EPS||crop.y+crop.height>1+EPS)fail('画面裁剪超出素材边界');
 const transform={x:number(t.x??fallback.x,-4,4,'水平位置'),y:number(t.y??fallback.y,-4,4,'垂直位置'),width:number(t.width??fallback.width,.002,4,'画面宽度'),height:number(t.height??fallback.height,.002,4,'画面高度'),rotation:number(t.rotation??0,-3600,3600,'画面旋转'),flipX:bool(t.flipX),flipY:bool(t.flipY),opacity:number(t.opacity??value.opacity??1,0,1,'画面透明度'),fit:t.fit??'contain',crop};
 if(!['contain','cover','stretch'].includes(transform.fit))fail('画面适配方式无效');
 const e={...DEFAULT_EFFECTS,...value.effects};for(const [key,min,max]of[['brightness',-1,1],['contrast',0,3],['saturation',0,3],['hue',-180,180],['blur',0,50]])e[key]=number(e[key],min,max,'效果参数');e.grayscale=bool(e.grayscale);e.sepia=bool(e.sepia);
 const m={type:'none',radius:.1,feather:0,inverted:false,...value.mask};if(!MASKS.includes(m.type))fail('遮罩形状无效');m.radius=number(m.radius,0,.5,'圆角');m.feather=number(m.feather,0,.5,'遮罩羽化');m.inverted=bool(m.inverted);
 return {transform,effects:e,mask:m};
}
function normalizeFrames(value,duration){const frames={};if(value===undefined)return frames;if(!value||typeof value!=='object'||Array.isArray(value))fail('关键帧格式无效');for(const [property,rows]of Object.entries(value)){if(!KEYFRAME_PROPERTIES.includes(property))fail('关键帧属性无效');const sorted=array(rows,200,'关键帧').map(row=>{let easing;try{easing=normalizeEasing(row.easing??'linear');}catch(reason){fail(reason.message);}const bounds=property==='opacity'?[0,1]:property==='volume'?[0,4]:property==='scale'?[.01,8]:property==='rotation'?[-3600,3600]:[-4,4];return {time:number(row.time,0,duration+EPS,'关键帧时间'),value:number(row.value,...bounds,'关键帧数值'),easing};}).sort((a,b)=>a.time-b.time);if(new Set(sorted.map(r=>r.time)).size!==sorted.length)fail('关键帧时间重复');frames[property]=sorted;}return frames;}
function normalizeV2(raw,result){
 if(raw.smartFinishing!==undefined){if(!raw.smartFinishing||!Array.isArray(raw.smartFinishing.effects)||raw.smartFinishing.effects.length>10)fail('后期效果格式无效');result.smartFinishing=copy(raw.smartFinishing);}
 if(result.music){result.music.fadeIn=number(raw.music.fadeIn??0,0,LIMITS.duration,'配乐淡入');result.music.fadeOut=number(raw.music.fadeOut??0,0,LIMITS.duration,'配乐淡出');result.music.ducking=bool(raw.music.ducking);}
  result.version=3;result.settings.background=color(raw.settings?.background);result.output={...result.output,format:raw.output?.format??'mp4',quality:raw.output?.quality??'high',audio:bool(raw.output?.audio,true)};if(!['mp4','webm'].includes(result.output.format)||!['low','medium','high'].includes(result.output.quality))fail('导出格式或质量无效');if(result.music&&raw.music?.duration!==undefined)result.music.duration=number(raw.music.duration,.001,864000,'配乐时长');
 result.tracks=array(raw.tracks??[],100,'轨道').map((t,index)=>({id:identifier(t.id),type:['video','image','text','subtitle','audio','sticker'].includes(t.type)?t.type:'video',name:String(t.name||`轨道 ${index+1}`).slice(0,100),order:number(t.order??index,0,100,'轨道顺序'),muted:bool(t.muted),hidden:bool(t.hidden),locked:bool(t.locked),height:number(t.height??1,.5,3,'轨道高度')}));unique(result.tracks,'轨道');
 const trackIds=new Set(result.tracks.map(t=>t.id));
 for(const {kind,item}of allItems(result)){const value=(raw[BUCKETS[kind]]||[]).find(row=>row.id===item.id)||item;item.start=number(value.start??0,0,LIMITS.duration,'片段开始时间');item.trackId=value.trackId??(kind==='clip'?'main':kind==='text'?'text':kind==='audio'?'audio':'overlay');if(!trackIds.has(item.trackId)){result.tracks.push({id:identifier(item.trackId),type:kind==='audio'?'audio':kind==='text'?'text':'video',name:kind==='clip'?'主视频':kind==='text'?'文字':kind==='audio'?'音频':'叠加',order:result.tracks.length,muted:false,hidden:false,locked:false});trackIds.add(item.trackId);}
  if(kind!=='audio'){let visual=value;if(kind==='text'&&!value.transform){const h=Math.min(1,(value.size??48)*1.4*value.text.split('\n').length/canvasSize(result).height);visual={...value,transform:{x:.05,y:value.position==='top'?.05:value.position==='center'?Math.max(0,(1-h)/2):Math.max(0,.95-h),width:.9,height:h}};}Object.assign(item,normalizeVisual(visual,kind));}
  if(value.duration!==undefined)item.duration=number(value.duration,.05,LIMITS.duration,'图层时长');
  if(kind!=='text'){item.reverse=bool(value.reverse);const asset=result.assets.find(a=>a.id===item.assetId);item.freezeAt=value.freezeAt==null?null:number(value.freezeAt,0,asset?asset.duration-.000001:LIMITS.duration,'定格位置');if(kind!=='audio'&&item.type!=='solid'&&asset?.kind!=='image'){item.freezeTail=number(value.freezeTail??0,0,itemDuration(item),'尾部定格时长');if(item.freezeTail&&item.freezeAt!=null)fail('整段定格与尾部定格不能同时启用');}}
  item.hidden=bool(value.hidden);item.fadeIn=number(value.fadeIn??0,0,itemDuration(item),'声音淡入');item.fadeOut=number(value.fadeOut??0,0,itemDuration(item),'声音淡出');item.keyframes=normalizeFrames(value.keyframes,itemDuration(item));
  if(kind==='text'){const s=value.style||{};item.style={bold:bool(s.bold),italic:bool(s.italic),underline:bool(s.underline),noWrap:bool(s.noWrap),align:s.align??'center',backgroundColor:color(s.backgroundColor),backgroundOpacity:number(s.backgroundOpacity??0,0,1,'文字背景透明度'),borderColor:color(s.borderColor),borderWidth:number(s.borderWidth??0,0,20,'文字描边'),shadowColor:color(s.shadowColor),shadowBlur:number(s.shadowBlur??0,0,30,'文字阴影')};if(!['left','center','right'].includes(item.style.align))fail('文字对齐无效');}
 }
  result.markers=array(raw.markers??[],200,'标记').map(m=>({id:identifier(m.id),time:number(m.time,0,LIMITS.duration,'标记时间'),label:String(m.label||'标记').slice(0,200),note:String(m.note||'').slice(0,2000),color:color(m.color,'#ffb547')}));unique(result.markers,'标记');if(totalDuration(result)>LIMITS.duration+EPS)fail('时间线总时长不能超过24小时');return result;
}
export function enableV2(draft){if(draft.version>=2)return normalizeDraft(draft);const next=copy(draft);next.version=3;next.tracks=[];next.markers=[];const rows=layout(draft);next.clips=next.clips.map((c,i)=>({...c,start:rows[i].start,trackId:'main'}));next.overlays=next.overlays.map(c=>({...c,trackId:'overlay'}));next.texts=next.texts.map(c=>({...c,trackId:'text'}));next.audioClips=next.audioClips.map(c=>({...c,trackId:'audio'}));return normalizeDraft(next);}
function requireItem(draft,kind,id){const bucket=BUCKETS[kind];if(!bucket)fail('片段类型无效');const item=draft[bucket].find(i=>i.id===id);if(!item)fail('片段已不存在');return item;}
export function trackAccepts(track,kind){if(!track)return false;if(kind==='audio')return track.type==='audio';if(kind==='text')return ['text','subtitle','sticker'].includes(track.type);return ['video','image','sticker'].includes(track.type);}
export function updateItem(draft,kind,id,patch){const next=enableV2(draft),item=requireItem(next,kind,id);if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('此轨道已锁定，请先解锁');if(patch.trackId!==undefined){const target=next.tracks.find(t=>t.id===patch.trackId);if(!target)fail('目标轨道不存在');if(target.locked)fail('目标轨道已锁定，请先解锁');if(!trackAccepts(target,kind))fail('轨道类型不匹配，请选择兼容轨道');}for(const [key,value]of Object.entries(patch)){if(['id','assetId'].includes(key))continue;item[key]=['transform','effects','mask','style'].includes(key)?{...item[key],...value,...(key==='transform'&&value.crop?{crop:{...item.transform.crop,...value.crop}}:{})}:value;}if(kind==='text'&&patch.start!==undefined&&patch.end===undefined)item.end+=patch.start-requireItem(draft,kind,id).start;return normalizeDraft(next);}
export function addTrack(draft,type='video',name){const next=enableV2(draft);next.tracks.push({id:uid('track'),type,name:name||`新${type==='audio'?'音频':'画面'}轨道`,order:next.tracks.length});return normalizeDraft(next);}
export function updateTrack(draft,id,patch){const next=enableV2(draft),index=requireIndex(next.tracks,id,'轨道'),old=next.tracks[index];if(patch.order!==undefined){if(!Number.isInteger(patch.order))fail('轨道顺序需要整数');const other=next.tracks.find(t=>t.id!==id&&t.order===patch.order);if(other)other.order=old.order;}next.tracks[index]={...old,...patch,id};return normalizeDraft(next);}
export function removeTrack(draft,id){let next=enableV2(draft);const track=next.tracks.find(t=>t.id===id);if(track?.locked)fail('轨道已锁定');for(const bucket of Object.values(BUCKETS))next[bucket]=next[bucket].filter(item=>item.trackId!==id);next.tracks=next.tracks.filter(t=>t.id!==id);return normalizeDraft(next);}
export function addImage(draft,assetId,start=0){let next=enableV2(draft);const asset=next.assets.find(a=>a.id===assetId);if(asset?.kind!=='image')fail('请选择图片素材');next.overlays.push({id:uid('image'),assetId,start,trimStart:0,trimEnd:asset.duration,speed:1,volume:0,duration:5,x:0,y:0,width:1,height:1});return normalizeDraft(next);}
export function addSticker(draft,shape='star',start=0){const next=enableV2(draft);if(!MASKS.includes(shape))fail('贴纸形状无效');next.overlays.push({id:uid('sticker'),type:'solid',start,duration:3,color:'#7785ff',transform:{x:.35,y:.35,width:.3,height:.3},mask:{type:shape},trackId:'stickers'});return normalizeDraft(next);}
export function ease(progress,easing='linear'){return curveEase(progress,easing);}
export function interpolate(rows,time,fallback){if(!rows?.length)return fallback;if(time<=rows[0].time)return rows[0].value;for(let i=1;i<rows.length;i++)if(time<rows[i].time){const a=rows[i-1],b=rows[i],p=ease((time-a.time)/(b.time-a.time),a.easing);return a.value+(b.value-a.value)*p;}return rows.at(-1).value;}
export function evaluateKeyframes(item,time){const t=item.transform||{},out={x:t.x??0,y:t.y??0,scale:1,opacity:t.opacity??item.opacity??1,rotation:t.rotation??0,volume:item.muted?0:item.volume??1};for(const key of KEYFRAME_PROPERTIES)out[key]=interpolate(item.keyframes?.[key],time,out[key]);if(item.muted||item.freezeAt!=null||(item.freezeTail&&time>=itemDuration(item)-item.freezeTail))out.volume=0;const envelope=Math.min(1,item.fadeIn?Math.max(0,time/item.fadeIn):1,item.fadeOut?Math.max(0,(itemDuration(item)-time)/item.fadeOut):1);out.volume*=envelope;out.opacity*=envelope;return out;}
export function setKeyframe(draft,kind,id,property,time,value,easing='linear'){if(!KEYFRAME_PROPERTIES.includes(property))fail('关键帧属性无效');const next=enableV2(draft),item=requireItem(next,kind,id);if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('此轨道已锁定');item.keyframes[property]=[...(item.keyframes[property]||[]).filter(k=>Math.abs(k.time-time)>EPS),{time,value,easing}];return normalizeDraft(next);}
export function moveKeyframe(draft,kind,id,property,from,to){if(!KEYFRAME_PROPERTIES.includes(property))fail('关键帧属性无效');const next=enableV2(draft),item=requireItem(next,kind,id);if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('此轨道已锁定');const target=number(to,0,itemDuration(item),'关键帧时间'),rows=item.keyframes[property]||[],row=rows.find(k=>Math.abs(k.time-from)<=EPS);if(!row)fail('关键帧已不存在');if(rows.some(k=>Math.abs(k.time-target)<=EPS&&Math.abs(k.time-from)>EPS))fail('该时间已有此属性的关键帧');item.keyframes[property]=rows.map(k=>Math.abs(k.time-from)<=EPS?{...k,time:target}:k);return normalizeDraft(next);}
export function removeKeyframe(draft,kind,id,property,time){const next=enableV2(draft),item=requireItem(next,kind,id);item.keyframes[property]=(item.keyframes[property]||[]).filter(k=>Math.abs(k.time-time)>EPS);return normalizeDraft(next);}
export function splitItem(draft,kind,id,time){const next=enableV2(draft),item=requireItem(next,kind,id),local=time-item.start,length=itemDuration(item),tail=item.freezeTail||0,frozenSource=tail?sourceTimeAt(item,local,next.settings.fps):null;if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('此轨道已锁定');if(local<.05||length-local<.05)fail('请在片段内部进行分割');const right=copy(item);right.id=uid(kind);right.start=time;if(kind==='text')item.end=time;else if(item.duration!==undefined){item.duration=local;right.duration=length-local;}else if(item.reverse){const boundary=item.trimEnd-local*item.speed;item.trimStart=boundary;right.trimEnd=boundary;}else{const boundary=item.trimStart+local*item.speed;item.trimEnd=boundary;right.trimStart=boundary;}if(tail){item.freezeTail=Math.max(0,local-(length-tail));if(local>=length-tail){right.freezeAt=frozenSource;right.freezeTail=0;}else right.freezeTail=tail;}if(item.transitionToNext)item.transitionToNext={type:'none',duration:.4};
 for(const property of KEYFRAME_PROPERTIES){const frames=item.keyframes?.[property];if(!frames?.length)continue;const boundary=interpolate(frames,local,evaluateKeyframes(item,local)[property]),active=frames.filter(k=>k.time<=local).at(-1)?.easing||'linear';item.keyframes[property]=[...frames.filter(k=>k.time<local),{time:local,value:boundary,easing:active}];right.keyframes[property]=[{time:0,value:boundary,easing:active},...frames.filter(k=>k.time>local).map(k=>({...k,time:k.time-local}))];}
 item.fadeIn=Math.min(item.fadeIn,local);item.fadeOut=0;right.fadeIn=0;right.fadeOut=Math.min(right.fadeOut,length-local);const bucket=next[BUCKETS[kind]];bucket.splice(bucket.indexOf(item)+1,0,right);return normalizeDraft(next);}
export function copyItems(draft,selections){const list=selections.map(s=>({kind:s.kind,item:copy(requireItem(draft,s.kind,s.id))}));const first=Math.min(...list.map(s=>s.item.start??layout(draft).find(r=>r.id===s.item.id)?.start??0));return list.map(s=>({...s,item:{...s.item,start:(s.item.start??layout(draft).find(r=>r.id===s.item.id)?.start??0)-first,...(s.kind==='text'?{end:s.item.end-first}:{})}}));}
export function pasteItems(draft,clipboard,time){const next=enableV2(draft);for(const {kind,item:old}of clipboard){const item=copy(old),length=itemDuration(item);item.id=uid(kind);item.start=time+item.start;if(kind==='text')item.end=item.start+length;if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('目标轨道已锁定');next[BUCKETS[kind]].push(item);}return normalizeDraft(next);}
export function deleteItems(draft,selections,ripple=false){const next=enableV2(draft),removed=selections.map(s=>({...s,item:requireItem(next,s.kind,s.id)}));for(const {kind,item}of removed){if(next.tracks.find(t=>t.id===item.trackId)?.locked)fail('此轨道已锁定');next[BUCKETS[kind]]=next[BUCKETS[kind]].filter(i=>i.id!==item.id);}if(ripple)for(const {item}of removed.sort((a,b)=>b.item.start-a.item.start)){const length=itemDuration(item);for(const {item:other}of allItems(next))if(other.trackId===item.trackId&&other.start>=item.start+length-EPS){other.start-=length;if(other.end!==undefined)other.end-=length;}}return normalizeDraft(next);}
export function addMarker(draft,time,label='标记',markerColor='#ffb547',note=''){const next=enableV2(draft);next.markers.push({id:uid('marker'),time:number(time,0,LIMITS.duration,'标记时间'),label:String(label).slice(0,200),note:String(note).slice(0,2000),color:markerColor});return normalizeDraft(next);}
export function canvasSize(draft){const first=draft.assets.find(a=>a.id===draft.clips[0]?.assetId)||draft.assets[0],ratio=draft.settings.ratio==='自动'?(first?first.width/first.height:16/9):draft.settings.ratio.split(':').reduce((a,b)=>a/Number(b)),res=draft.settings.resolution;let width,height;if(res==='原画'){const side=Math.min(3840,Math.max(first?.width||1920,first?.height||1080));[width,height]=ratio>=1?[side,side/ratio]:[side*ratio,side];}else{const side={'720p':720,'1080p':1080,'2K':1440,'4K':2160}[res];[width,height]=ratio>=1?[side*ratio,side]:[side,side/ratio];const scale=Math.min(1,3840/Math.max(width,height));width*=scale;height*=scale;}return {width:Math.max(2,Math.round(width/2)*2),height:Math.max(2,Math.round(height/2)*2)};}
function buildExportV2(draft){
 const duration=totalDuration(draft);if(!duration||!allItems(draft).length)fail('请先添加画面、图片、文字或音频');const assets=new Map(draft.assets.map(a=>[a.id,a])),audioAssets=new Map(draft.audioAssets.map(a=>[a.id,a])),tracks=new Map(draft.tracks.map(t=>[t.id,t])),sound=draft.output.audio!==false;
 const layers=[],audioClips=[];for(const {kind,item}of allItems(draft)){const track=tracks.get(item.trackId);if(item.hidden||track?.hidden)continue;const silent=!sound||item.muted||track?.muted,common={id:item.id,start:item.start,duration:itemDuration(item),track:track?.order??0,trimStart:item.trimStart??0,trimEnd:item.trimEnd??itemDuration(item),speed:item.speed??1,reverse:item.reverse??false,freezeAt:item.freezeAt??null,volume:silent?0:item.volume??0,fadeIn:item.fadeIn,fadeOut:item.fadeOut,keyframes:copy(item.keyframes)};if(silent&&common.keyframes.volume)common.keyframes.volume=common.keyframes.volume.map(k=>({...k,value:0}));
 if(kind==='audio'){audioClips.push({path:audioAssets.get(item.assetId).path,start:common.start,trimStart:common.trimStart,trimEnd:common.trimEnd,speed:common.speed,volume:common.volume,fadeIn:common.fadeIn,fadeOut:common.fadeOut,reverse:common.reverse,keyframes:common.keyframes});continue;}
 const type=kind==='text'?'text':item.type==='solid'?'solid':assets.get(item.assetId)?.kind==='image'?'image':'video';const layer={...common,type,...(type==='video'?{freezeTail:item.freezeTail||0}:{}),...(type==='image'||type==='video'?{path:assets.get(item.assetId).path}:{}),transform:copy(item.transform),effects:copy(item.effects),mask:copy(item.mask)};if(type==='text'){if(!item.text.trim())fail('文字内容不能为空');layer.text=item.text;layer.style={...item.style,font:item.font,size:item.size,color:item.color};}if(type==='solid')layer.color=item.color;if(item.transitionToNext?.type!=='none'&&item.transitionToNext)layer.transitionToNext=copy(item.transitionToNext);layers.push(layer);}
 if(sound&&draft.music?.path){const length=draft.music.duration||duration,span=draft.music.loop?duration:Math.min(length,duration);audioClips.push({path:draft.music.path,start:0,duration:span,trimStart:0,trimEnd:Math.min(length,duration),speed:1,volume:draft.music.volume,fadeIn:Math.min(draft.music.fadeIn,span),fadeOut:Math.min(draft.music.fadeOut,span),ducking:draft.music.ducking,reverse:false,loop:draft.music.loop});}
  const folder=absolutePath(draft.output.folder.trim()),format=draft.output.format||'mp4',name=draft.output.filename.trim();if(!name||name.length>200||!name.toLowerCase().endsWith('.'+format)||/[<>:"/\\|?*\x00-\x1f\x7f]/.test(name)||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name))fail('请输入与格式一致的有效导出文件名');return {...(draft.smartFinishing?{smartFinishing:copy(draft.smartFinishing)}:{}),documentVersion:3,duration,...canvasSize(draft),fps:draft.settings.fps,background:draft.settings.background,layers:layers.sort((a,b)=>a.track-b.track),audioClips,format,quality:draft.output.quality,output:folder.replace(/[\\/]+$/,'')+(folder.includes('\\')?'\\':'/')+name};
}
