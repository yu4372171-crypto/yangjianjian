import { d as defineComponent, j as ref, s as computed, a as h, v as watch, K as onBeforeUnmount, u as useApp, l as rpc } from './index-CVDv6sjN.js';
import * as M from './TimelineModel.js';
import { renderProperties, V2_STYLE, VIEWPORT_STYLE } from './TimelineProperties.js';
import { drawTimeline } from './TimelineV2Preview.js';
import { resizeSelection, selectedItems as pickSelectedItems, selectionSpan, autoScrollSpeed, marqueeIntersects } from './TimelineInteraction.js';
import { collectAnchors, mainInsertIndex, nearestSnap, placementPreview } from './TimelinePlacement.js';
import { dbToGain, gainToDb, decodeWaveform } from './TimelineAudio.js';
import FreeAssetLibrary from './FreeAssetLibrary.js';

const tlH=(tag,props,children)=>Array.isArray(props)||typeof props==='string'||typeof props==='number'?h(tag,null,props):h(tag,props,children);
const TIMELINE_KEY='aive-timeline-draft:v1';
const WORKSPACE_KEY='aive-timeline-workspace:v1';
const TL_VIDEO_FILTER='视频素材|*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v;*.mts;*.m2ts|所有文件|*.*';
const TL_VIDEO_EXT=/\.(mp4|mov|mkv|avi|webm|m4v|mts|m2ts)$/i;
const TL_AUDIO_FILTER='音频素材|*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg;*.opus;*.wma|所有文件|*.*';
const TL_AUDIO_EXT=/\.(mp3|wav|m4a|aac|flac|ogg|opus|wma)$/i;
const TL_IMAGE_FILTER='图片素材|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp|所有文件|*.*';
const TL_IMAGE_EXT=/\.(png|jpe?g|webp|gif|bmp)$/i;
const tlClamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const tlName=path=>String(path).split(/[\\/]/).pop()||String(path);
const tlMessage=reason=>reason instanceof Error?reason.message:String(reason||'操作失败，请重试');
const tlClock=value=>{const n=Math.max(0,Number(value)||0),m=Math.floor(n/60);return `${String(m).padStart(2,'0')}:${(n%60).toFixed(2).padStart(5,'0')}`;};
const SKIN_KEY='aive-ui-skin';
const SKINS=[
  {value:'system',label:'跟随系统'},
  {value:'light',label:'冰川银 · 专业工作台'},
  {value:'dark',label:'深空黑 · 影院沉浸'},
  {value:'cyber-blue',label:'星舰蓝 · 指挥舱'},
  {value:'cyber-teal',label:'量子青 · 剪辑台'},
  {value:'cyber-violet',label:'极光紫 · 创作空间'}
];
const skinValues=new Set(SKINS.map(item=>item.value));
function applySkin(value){
  const skin=skinValues.has(value)?value:'cyber-blue',root=typeof document!=='undefined'?document.documentElement:null;
  if(!root)return skin;
  const resolved=skin==='system'?(globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches?'dark':'light'):skin;
  root.dataset.theme=resolved;
  root.dataset.uiSkin=skin;
  globalThis.dispatchEvent?.(new CustomEvent('aive-ui-skin-changed',{detail:{skin}}));
  return skin;
}
const TL_STYLE=`
.timeline-editor{--tl-line:var(--color-border,var(--border,#dbe1eb));--tl-muted:var(--color-text-secondary,var(--text-muted,#7b879c));--tl-panel:var(--color-bg-panel,var(--bg-panel,var(--bg-secondary,#fff)));--tl-text:var(--color-text,var(--text-primary,inherit));color:var(--tl-text);display:grid;gap:14px;margin-top:14px;min-width:0}.timeline-editor button,.timeline-editor input,.timeline-editor select,.timeline-editor textarea{font:inherit}.timeline-editor button{cursor:pointer}.timeline-editor button:disabled{cursor:default;opacity:.45}.timeline-editor button:focus-visible,.timeline-editor input:focus-visible,.timeline-editor select:focus-visible,.timeline-editor textarea:focus-visible{outline:2px solid #7385ff;outline-offset:2px}.tl-header,.tl-actions,.tl-panel-heading,.tl-transport,.tl-time-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.tl-header{justify-content:space-between}.tl-header h2{font-size:20px;margin:0;letter-spacing:-.5px}.tl-subtitle,.tl-help,.tl-saved{font-size:12px;color:var(--tl-muted);line-height:1.65}.tl-subtitle{margin:4px 0 0}.tl-saved{display:flex;align-items:center;gap:5px}.tl-saved:before{content:'';width:6px;height:6px;border-radius:50%;background:#39ac83}.tl-header .primary,.tl-output .primary{background:#6576ef;border-color:#6576ef;color:#fff}.tl-workspace{display:grid;grid-template-columns:minmax(195px,.8fr) minmax(300px,2.05fr) minmax(230px,.95fr);gap:12px;min-height:460px;align-items:stretch}.tl-panel{border:1px solid var(--tl-line);border-radius:12px;background:var(--tl-panel);min-width:0;overflow:hidden}.tl-panel-heading{justify-content:space-between;padding:13px 14px;border-bottom:1px solid var(--tl-line)}.tl-panel-heading h3{font-size:13px;margin:0}.tl-badge{font-size:10px;padding:3px 7px;border-radius:5px;color:var(--tl-muted);background:var(--color-bg-hover,#8190a90e)}.tl-media{display:flex;flex-direction:column}.tl-drop{margin:12px;padding:18px 8px;border:1px dashed var(--tl-line);border-radius:8px;text-align:center;background:var(--color-bg-hover,#8190a908)}.tl-drop.dragging{border-color:#7385ff;background:#7385ff15}.tl-drop strong{display:block;font-size:12px;margin:5px 0}.tl-drop span{font-size:11px;color:var(--tl-muted)}.tl-drop svg{color:#7180d9}.tl-media-list{max-height:470px;overflow:auto;padding:0 12px 12px;display:grid;gap:9px}.tl-asset{border:1px solid var(--tl-line);border-radius:8px;overflow:hidden}.tl-asset img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:#121722}.tl-asset-info{padding:8px}.tl-asset-info strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.tl-asset-info small{font-size:10px;color:var(--tl-muted);display:block;margin:4px 0 7px}.tl-asset .tl-actions{gap:5px}.tl-asset button{font-size:11px;padding:4px 7px;flex:1}.tl-preview{display:flex;flex-direction:column;background:#131722;border-color:#252c3d}.tl-preview .tl-panel-heading{border-color:#2a3042;color:#d3d9e8}.tl-preview .tl-badge{color:#aab4cc;background:#ffffff09}.tl-preview-space{display:flex;align-items:center;justify-content:center;flex:1;min-height:250px;padding:16px;overflow:hidden}.tl-canvas{position:relative;background:#000;width:100%;max-height:370px;overflow:hidden;box-shadow:0 10px 35px #0004;user-select:none}.tl-canvas .tl-main-video{position:absolute;width:100%;height:100%;inset:0;object-fit:contain;background:#000}.tl-preview-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#748096;text-align:center;font-size:12px;gap:12px;padding:20px}.tl-preview-empty strong{font-size:15px;color:#b8c3d8}.tl-overlay-box{position:absolute;touch-action:none;cursor:move;box-sizing:border-box;background:transparent}.tl-overlay-box.selected{outline:2px solid #8c9aff}.tl-overlay-box video{width:100%;height:100%;display:block;object-fit:contain;background:transparent}.tl-text-preview{position:absolute;left:5%;right:5%;white-space:pre;word-break:normal;text-align:center;line-height:1.3;pointer-events:none;text-shadow:0 2px 3px #000,1px 0 #000,-1px 0 #000}.tl-preview-bottom{border-top:1px solid #2a3042;padding:10px 12px;color:#b6c0d6}.tl-transport{justify-content:space-between;gap:10px}.tl-transport button{background:#ffffff0b;border-color:#ffffff17;color:#dce3f2;padding:5px 10px}.tl-transport .tl-play{background:#7180ed;border-color:#7180ed;color:white;min-width:50px}.tl-clock{font-size:11px;font-variant-numeric:tabular-nums;font-family:Consolas,monospace}.tl-preview-bottom input[type=range]{width:100%;margin:8px 0 0;accent-color:#8a98ff}.tl-inspector{max-height:560px;overflow:auto}.tl-properties{padding:13px;display:grid;gap:12px}.tl-properties h4,.tl-output h4{font-size:12px;margin:0}.tl-properties .tl-selected-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600}.tl-field{display:flex;flex-direction:column;gap:5px;font-size:11px;color:var(--tl-muted);min-width:0}.tl-field input,.tl-field select,.tl-field textarea{width:100%;box-sizing:border-box;min-width:0;font-size:12px;color:var(--tl-text)}.tl-field textarea{resize:vertical;min-height:72px}.tl-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.tl-check{display:flex;gap:7px;align-items:center;font-size:11px;color:var(--tl-muted)}.tl-check input{width:auto}.tl-output{padding:13px;border-top:1px solid var(--tl-line);display:grid;gap:11px}.tl-folder{display:flex;gap:6px;align-items:center;min-width:0}.tl-folder span{font-size:11px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;flex:1;color:var(--tl-muted)}.tl-folder button{font-size:11px;padding:5px 7px}.tl-audio{width:100%;height:30px;max-width:100%;margin:0}.tl-timeline{border:1px solid var(--tl-line);border-radius:12px;background:var(--tl-panel);overflow:hidden;min-width:0}.tl-timeline-toolbar{padding:10px 12px;display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;border-bottom:1px solid var(--tl-line)}.tl-time-actions button{font-size:12px;padding:5px 8px}.tl-zoom{display:flex;gap:6px;align-items:center;font-size:11px;color:var(--tl-muted)}.tl-zoom input{width:90px;accent-color:#7484f5}.tl-timeline-scroll{overflow:auto;max-height:380px;position:relative}.tl-track-content{position:relative;padding-bottom:12px;min-width:100%}.tl-ruler{display:flex;height:28px;border-bottom:1px solid var(--tl-line);margin-left:82px;position:relative;cursor:crosshair}.tl-tick{position:absolute;font-family:Consolas,monospace;font-size:9px;color:var(--tl-muted);top:6px;padding-left:5px;border-left:1px solid var(--tl-line);height:22px}.tl-lane{display:grid;grid-template-columns:82px 1fr;min-height:54px;border-bottom:1px solid var(--tl-line)}.tl-lane-label{position:sticky;left:0;z-index:5;background:var(--tl-panel);padding:13px 9px;font-size:10px;color:var(--tl-muted);display:flex;gap:4px;flex-direction:column;border-right:1px solid var(--tl-line)}.tl-lane-label strong{color:var(--tl-text);font-size:11px}.tl-track{position:relative;min-height:52px}.tl-track-empty{font-size:11px;color:var(--tl-muted);position:absolute;top:18px;left:14px;white-space:nowrap}.tl-block{position:absolute;top:7px;height:39px;border-radius:5px;box-sizing:border-box;cursor:pointer;overflow:hidden;display:flex;align-items:center;padding:0 10px;gap:7px;font-size:11px;white-space:nowrap;user-select:none}.tl-main-clip{background:#6579de2a;border:1px solid #7186e2;color:var(--tl-text)}.tl-main-clip.selected{background:#687de950;border-color:#a3b0ff;box-shadow:inset 0 0 0 1px #a3b0ff}.tl-block img{width:38px;height:28px;border-radius:3px;object-fit:cover;flex-shrink:0;pointer-events:none}.tl-block-name{overflow:hidden;text-overflow:ellipsis}.tl-overlay-clip{background:#8e66d62b;border:1px solid #a079e7}.tl-text-clip{background:#cc9c342b;border:1px solid #c5a050}.tl-music-clip{background:#32a98224;border:1px solid #53a98f}.tl-block.selected{outline:1px solid #c5cdfb;outline-offset:-1px}.tl-trim{position:absolute;top:0;bottom:0;width:7px;background:#a6b4ff30;cursor:ew-resize;touch-action:none;z-index:3}.tl-trim.left{left:0}.tl-trim.right{right:0}.tl-trim:after{content:'';position:absolute;top:12px;bottom:12px;width:2px;left:2px;background:#b2bfff}.tl-playhead{position:absolute;top:0;bottom:0;width:1px;background:#ff9a72;pointer-events:none;z-index:6}.tl-playhead:before{content:'';position:absolute;top:1px;left:-4px;width:9px;height:9px;background:#ff9a72;border-radius:2px;transform:rotate(45deg)}.tl-timeline-footer{padding:8px 13px;font-size:10px;color:var(--tl-muted);display:flex;justify-content:space-between;gap:10px}.tl-error{border:1px solid var(--color-danger,#c65b66);border-radius:8px;padding:10px 13px;color:var(--color-danger,#e27982);font-size:12px;white-space:pre-line;overflow-wrap:anywhere}.tl-status{font-size:12px;color:var(--tl-muted);display:flex;gap:10px;align-items:center}.tl-status progress{max-width:140px;height:6px;accent-color:#7282ed}.tl-status button{font-size:11px;padding:3px 7px}.tl-result{padding:12px 14px;border:1px solid var(--tl-line);border-radius:10px;font-size:12px;overflow-wrap:anywhere}.tl-result video{display:block;max-height:300px;width:100%;margin-top:9px;background:#000}.tl-export-task{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.tl-export-task progress{width:100px;height:6px}.tl-export-task button{font-size:11px;padding:3px 7px}@media(min-width:1500px){.tl-preview-space{min-height:330px}.tl-canvas{max-height:440px}.tl-inspector{max-height:640px}}@media(max-width:1100px){.tl-workspace{grid-template-columns:minmax(160px,.7fr) minmax(280px,1.5fr)}.tl-inspector{grid-column:1/-1;max-height:none;display:grid;grid-template-columns:1fr 1fr}.tl-inspector>.tl-panel-heading{grid-column:1/-1}.tl-output{border-top:0;border-left:1px solid var(--tl-line)}.tl-media-list{max-height:380px}}@media(max-width:700px){.tl-workspace{grid-template-columns:1fr}.tl-media-list{grid-template-columns:repeat(2,minmax(0,1fr));max-height:250px}.tl-media .tl-drop{padding:9px}.tl-preview{min-height:330px}.tl-inspector{grid-template-columns:1fr}.tl-output{border-left:0;border-top:1px solid var(--tl-line)}.tl-header h2{font-size:18px}.tl-saved{display:none}.tl-timeline-footer{flex-direction:column}}
.tl-preview .tl-panel-heading h3{color:#d3d9e8}.tl-preview-space{container-type:size;min-height:0}.tl-canvas{container-type:inline-size;max-height:none;flex-shrink:0;width:min(100cqw,calc(100cqh * var(--tl-aspect,1.7778)))}
@media(min-width:1101px){.tl-workspace{height:clamp(340px,42vh,500px);min-height:0}.tl-workspace>.tl-panel{min-height:0;max-height:none}.tl-media-list{flex:1;min-height:0;max-height:none}.tl-inspector{overflow:auto}.tl-preview-space{padding:14px;flex:1;min-height:0}.tl-preview .tl-panel-heading,.tl-preview-bottom{flex-shrink:0}}
@media(max-width:1100px){.tl-preview-space{min-height:270px}.tl-canvas{width:min(100cqw,calc(270px * var(--tl-aspect,1.7778)))}}
`;
const TL_WORKBENCH_STYLE=`
.timeline-editor .tl-library-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:2px;padding:7px;border-bottom:1px solid var(--tl-line)}.tl-library-tabs button{padding:8px 2px;font-size:10px;border:0;border-radius:5px;background:transparent;color:var(--tl-muted)}.tl-library-tabs button.active,.tl-tool-active{background:#7184e52b!important;color:#8092f6!important}.tl-library-content{flex:1;min-height:0;overflow:auto}.tl-library-content .tl-media-list{max-height:none;overflow:visible}.tl-library-content .tl-help{padding:0 12px}.tl-preset-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px}.tl-preset{padding:10px 5px;display:grid;gap:8px;border:1px solid var(--tl-line);border-radius:7px;font-size:11px;min-width:0;background:var(--tl-panel);color:var(--tl-text);text-align:center}.tl-preset-visual{height:43px;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#596ec244,#865dbc44);font-size:20px;border-radius:5px;overflow:hidden}.tl-preset:hover{border-color:#8092f6}.tl-audio-library{display:grid;gap:9px;padding:12px}.tl-audio-item{padding:10px;border:1px solid var(--tl-line);border-radius:7px;display:grid;gap:7px;font-size:11px}.tl-audio-item.active{border-color:#8092f6;background:#7184e512}.tl-empty-library{padding:14px;font-size:12px;line-height:1.7;color:var(--tl-muted)}.tl-track-controls{display:flex;gap:4px;align-items:center}.tl-track-controls button{padding:1px 4px;font-size:9px;line-height:16px}.tl-block.tl-hidden{opacity:.35;background-image:repeating-linear-gradient(135deg,transparent,transparent 7px,#8080801c 7px,#8080801c 10px)}.tl-block-filmstrip{position:absolute;inset:0;display:flex;opacity:.45;overflow:hidden;pointer-events:none;gap:1px}.tl-block-filmstrip img{border-radius:0;width:auto;height:100%;min-width:55px;flex:1;object-fit:cover}.tl-block-name{position:relative;z-index:1;text-shadow:0 1px 3px #0008;pointer-events:none}.tl-block.tl-main-clip,.tl-block.tl-overlay-clip{height:44px;top:5px}.tl-main-clip .tl-block-name,.tl-overlay-clip .tl-block-name{color:#fff;background:#1217279e;padding:2px 4px;border-radius:3px}.tl-timed-block{cursor:grab;touch-action:none}.tl-timed-block:active{cursor:grabbing}.tl-text-clip .tl-trim{background:#dac07328}.tl-overlay-clip .tl-trim{background:#b797ef30}.tl-join{position:absolute;top:13px;height:28px;min-width:18px;border:1px solid #b5befe;background:#5869b8ed;color:#fff;font-size:10px;z-index:4;padding:0 3px;border-radius:4px;overflow:hidden;white-space:nowrap}.tl-join.selected{outline:2px solid #dce2ff}.tl-snap-guide{position:absolute;top:0;bottom:0;border-left:1px dashed #72ddc0;pointer-events:none;z-index:7}.tl-ruler{touch-action:none}.tl-timeline-scroll{min-height:216px}.tl-preview .tl-main-video{will-change:transform,opacity;backface-visibility:hidden}.tl-next-video{pointer-events:none}.tl-check-row{display:flex;gap:12px;flex-wrap:wrap}.tl-transition-info{font-size:11px;color:var(--tl-muted);line-height:1.6}.tl-timeline-toolbar .tl-zoom button{padding:3px 6px;font-size:11px}.tl-audio-clip{background:repeating-linear-gradient(90deg,#40b7a92b 0,#40b7a92b 5px,#40b7a94a 6px,#40b7a94a 8px);border:1px solid #53b7a2}.tl-audio-clip .tl-trim{background:#83d5c330}.tl-block .tl-trim{width:8px}.tl-block-filmstrip+span{max-width:100%}.tl-waveform{position:absolute;inset:5px 10px;display:flex;align-items:center;gap:1px;pointer-events:none;opacity:.8;z-index:0}.tl-waveform i{flex:1;min-width:1px;max-width:3px;border-radius:1px;background:#b8fff0}.tl-volume-line{position:absolute;left:10px;right:10px;height:2px;background:#fff5b8;border-radius:2px;z-index:3;cursor:ns-resize;touch-action:none}.tl-volume-line:before{content:'';position:absolute;left:0;top:-4px;width:7px;height:10px;border-radius:2px;background:#fff5b8}.tl-marquee{position:absolute;border:1px solid #8fa0ff;background:#7184e52c;pointer-events:none;z-index:8;border-radius:3px}.tl-drop-preview{position:absolute;top:0;bottom:0;min-width:3px;border-left:2px solid #6ce1bc;background:#5cd2aa18;pointer-events:none;z-index:8}.tl-drop-preview.blocked{border-color:#ff7f7f;background:#ff4d4d16}.tl-drop-preview.insert{border-color:#ffc85c;background:#ffc85c18}.tl-drop-preview span{position:absolute;left:5px;top:3px;max-width:190px;padding:2px 5px;border-radius:4px;background:#111827e8;color:#eef2ff;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tl-group-selection{position:absolute;top:28px;bottom:0;pointer-events:none;z-index:7;border-left:1px solid #b6c0ff;border-right:1px solid #b6c0ff;background:#8797ff0b}.tl-group-handle{position:absolute;top:5px;bottom:5px;width:10px;border:0;border-radius:4px;background:#9eabff;box-shadow:0 0 0 1px #e1e5ff;pointer-events:auto;cursor:ew-resize;touch-action:none;padding:0}.tl-group-handle.left{left:-5px}.tl-group-handle.right{right:-5px}.tl-group-label{position:absolute;left:4px;top:3px;padding:2px 5px;border-radius:4px;background:#6878df;color:white;font-size:9px;white-space:nowrap}.tl-track{touch-action:none}
`;

const TL_COMPACT_STYLE=`
.timeline-editor{gap:10px;margin-top:8px}.tl-header{min-height:32px;justify-content:flex-end}.tl-header>div:first-child{display:none}.tl-header .tl-actions{gap:8px}.tl-header button{padding:6px 11px;font-size:12px}.tl-panel-heading{padding:10px 12px}.tl-library-tabs button{padding:7px 2px}.tl-drop{margin:10px;padding:12px 7px}.tl-media-list{padding:0 10px 10px}.tl-preview-bottom{padding:8px 11px}.tl-preview-space{padding:11px}.tl-properties,.tl-output{padding:11px;gap:9px}.tl-lane{min-height:46px}.tl-track{min-height:46px}.tl-lane-label{padding:7px 8px;gap:3px;font-size:9px;line-height:1.2}.tl-lane-label strong{font-size:10.5px;line-height:1.2}.tl-lane-label>span{max-width:66px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tl-track-controls button{font-size:9px;line-height:14px;padding:0 3px;min-height:16px}.tl-block,.tl-block.tl-main-clip,.tl-block.tl-overlay-clip{height:36px;top:5px}.tl-join{top:10px;height:27px}.tl-trim:after{top:10px;bottom:10px}.tl-timeline-toolbar{padding:8px 10px}.tl-timeline-footer{padding:6px 11px}.tl-timeline-scroll{max-height:clamp(230px,30vh,360px);min-height:200px}.tl-library-content .tl-audio-library{gap:7px;padding:10px}.tl-audio-item{padding:8px;gap:6px}
@media(min-width:1101px){.tl-workspace{height:clamp(260px,36vh,420px);min-height:0}.tl-workspace>.tl-panel{min-height:0}.tl-preview-space{padding:11px;min-height:0}}
@media(max-height:900px) and (min-width:1101px){.tl-workspace{height:260px}.tl-timeline-scroll{max-height:260px}.tl-preview-bottom{padding:6px 10px}.tl-properties,.tl-output{padding:10px;gap:8px}}
`;

const TL_TECH_SKIN_STYLE=`
:root[data-theme=cyber-blue]{color-scheme:dark;--color-primary:#42d9ff;--color-primary-hover:#82e8ff;--color-primary-soft:#0c3550;--color-bg:#06111f;--color-card:#0a1a2b;--color-sidebar:#071728;--color-border:#16384f;--color-text:#e6f9ff;--color-text-secondary:#82a8bc;--color-success:#4ce5b4;--color-warning:#ffc15a;--color-error:#ff7088;--color-bg-panel:#081727;--shadow:0 12px 34px #00142666}
:root[data-theme=cyber-teal]{color-scheme:dark;--color-primary:#3ef0c2;--color-primary-hover:#7bffe0;--color-primary-soft:#0b4037;--color-bg:#041513;--color-card:#08231f;--color-sidebar:#061c19;--color-border:#17483f;--color-text:#e7fff9;--color-text-secondary:#83b9ad;--color-success:#67f7c9;--color-warning:#f4cf68;--color-error:#ff7b8f;--color-bg-panel:#071e1b;--shadow:0 12px 34px #001a1655}
:root[data-theme=cyber-violet]{color-scheme:dark;--color-primary:#b77bff;--color-primary-hover:#d2a8ff;--color-primary-soft:#342353;--color-bg:#100d1d;--color-card:#191329;--color-sidebar:#130f22;--color-border:#352753;--color-text:#f6edff;--color-text-secondary:#b7a5ce;--color-success:#70e8be;--color-warning:#ffd073;--color-error:#ff7e9b;--color-bg-panel:#171126;--shadow:0 12px 34px #09001566}
:root[data-theme=light]{--color-bg-panel:#f7fbff;--color-border:#c7d8e7}
:root[data-theme^=cyber] body{background:radial-gradient(circle at 78% -20%,var(--color-primary-soft),transparent 38%),linear-gradient(145deg,var(--color-bg),color-mix(in srgb,var(--color-bg) 82%,#000 18%))}
:root[data-theme^=cyber] .app-header,:root[data-theme^=cyber] .app-sidebar,:root[data-theme^=cyber] .panel,:root[data-theme^=cyber] .tl-panel{background-image:linear-gradient(135deg,color-mix(in srgb,var(--color-card) 92%,var(--color-primary) 8%),var(--color-card) 58%)}
:root[data-theme^=cyber] .app-header{border-bottom-color:color-mix(in srgb,var(--color-primary) 28%,var(--color-border))}
:root[data-theme^=cyber] .app-sidebar nav a.selected,:root[data-theme^=cyber] .panel{border-color:color-mix(in srgb,var(--color-primary) 20%,var(--color-border));box-shadow:0 0 0 1px color-mix(in srgb,var(--color-primary) 5%,transparent),var(--shadow)}
:root[data-theme^=cyber] button.primary,:root[data-theme^=cyber] .tl-header .primary,:root[data-theme^=cyber] .tl-output .primary{box-shadow:0 0 22px color-mix(in srgb,var(--color-primary) 28%,transparent)}
.tl-skin-picker{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--tl-muted);padding:0 6px;border-left:1px solid var(--tl-line)}
.tl-skin-picker select{width:auto;min-width:88px;height:29px;padding:3px 24px 3px 8px;font-size:11px;background:var(--tl-panel);color:var(--tl-text)}
.video-tools-page.vt-timeline-mode{padding:8px 12px 10px!important}
.vt-timeline-mode>.page-header{display:none}
.vt-timeline-mode>.subnav{margin:0 0 4px!important;min-height:30px;gap:16px;border-bottom-color:color-mix(in srgb,var(--color-border) 72%,transparent)}
.vt-timeline-mode>.subnav button{padding:6px 0 8px;font-size:11px}
.tl-header .tl-actions{gap:6px}.tl-header button{min-height:29px;padding:4px 9px!important}
.tl-workspace{gap:8px}.tl-panel-heading{padding:8px 10px}.tl-badge{padding:2px 6px}
.tl-library-tabs{padding:5px!important}.tl-library-tabs button{padding:6px 2px!important}
.tl-timeline-toolbar{padding:6px 8px!important;gap:6px!important}.tl-time-actions{gap:4px!important}.tl-time-actions button{min-height:26px;padding:3px 7px!important;font-size:10.5px!important}
.tl-zoom{gap:4px!important}.tl-zoom input{width:74px!important}.tl-lane{min-height:42px!important}.tl-track{min-height:42px!important}.tl-lane-label{padding:5px 6px!important}.tl-track-controls{gap:2px!important}.tl-track-controls button{min-width:18px!important;min-height:17px!important;padding:0 2px!important;font-size:8px!important}
.tl-block,.tl-block.tl-main-clip,.tl-block.tl-overlay-clip{height:32px!important;top:5px!important}.tl-track-empty{top:13px;font-size:10px}
.tl-timeline-scroll{max-height:clamp(250px,34vh,390px)!important}.tl-timeline-footer span:first-child{display:none}.tl-timeline-footer{justify-content:flex-end!important}
.tl-lane[data-track-type=audio] .tl-lane-label{box-shadow:inset 3px 0 #36cbb0}.tl-lane[data-track-type=video],.tl-lane[data-track-type=image]{box-shadow:inset 3px 0 #5d8cff}.tl-lane[data-track-type=subtitle],.tl-lane[data-track-type=text]{box-shadow:inset 3px 0 #e5a94c}.tl-lane[data-track-type=sticker]{box-shadow:inset 3px 0 #b988f5}
.tl-free-track:hover,.tl-free-track:focus-within{background:color-mix(in srgb,var(--color-primary) 5%,transparent)}
.tl-free-track.tl-drop-target{outline:1px dashed var(--color-primary);outline-offset:-2px;background:color-mix(in srgb,var(--color-primary) 9%,transparent)}
@media(max-width:1180px){.tl-skin-picker span{display:none}.tl-skin-picker{padding-left:2px}.tl-workspace{grid-template-columns:minmax(150px,.72fr) minmax(280px,1.65fr) minmax(205px,.88fr)!important}}
@media(max-width:900px){.tl-skin-picker{display:none}.video-tools-page.vt-timeline-mode{padding:6px!important}}
`;

const TL_DOWNLOADED_STYLE=`
.tl-downloaded-section{padding:12px;border-bottom:1px solid var(--tl-line)}.tl-downloaded-heading{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px}.tl-downloaded-heading strong{flex:1}.tl-downloaded-heading button{padding:3px 7px;font-size:10px}.tl-downloaded-section .tl-preset-grid{padding:10px 0 0}.tl-downloaded-section .tl-preset{padding:7px;gap:6px}.tl-downloaded-preview{height:76px;display:grid;place-items:center;overflow:hidden;border-radius:5px;background:repeating-conic-gradient(#8190a914 0 25%,#8190a906 0 50%) 0/16px 16px}.tl-downloaded-preview img{max-width:92%;max-height:70px;object-fit:contain}.tl-downloaded-preview video{width:100%;height:100%;object-fit:cover}.tl-downloaded-section .tl-preset small{font-size:9px;color:var(--tl-muted)}.tl-downloaded-section .tl-help{padding:0;margin-bottom:0}.tl-downloaded-error{color:var(--color-danger,#e27982);font-size:11px;line-height:1.6;overflow-wrap:anywhere}.tl-builtin-heading{font-size:11px;color:var(--tl-muted);padding:12px 12px 0;margin:0}
`;

const TimelineEditor=defineComponent({
  name:'TimelineEditor',props:{active:{type:Boolean,default:true}},emits:['busy'],
  setup(props,{emit}){
    const store=useApp(),draft=ref(M.enableV2(M.newDraft())),selection=ref({kind:'',id:''}),playhead=ref(0),zoom=ref(45),playing=ref(false);
    const importing=ref(false),exporting=ref(false),dragging=ref(false),error=ref(''),status=ref(''),progress=ref(0),saveState=ref('草稿已保存');
    let savedSkin='cyber-blue';try{savedSkin=localStorage.getItem(SKIN_KEY)||savedSkin;}catch{}const skin=ref(applySkin(savedSkin));
    function syncExternalSkin(event){const value=event.detail?.skin;if(skinValues.has(value)&&value!==skin.value){skin.value=value;applySkin(value);}}
    globalThis.addEventListener?.('aive-ui-skin-changed',syncExternalSkin);
    const catalog=ref([]),urls=ref({}),thumbnails=ref({}),result=ref(''),resultUrl=ref('');
    const downloadedAssets=ref([]),downloadedLoading=ref(false),downloadedError=ref(''),applyingDownloaded=ref('');
    let downloadedRevision=0;
    const downloadedCategory={transitions:'transition',stickers:'sticker',effects:'effect'};
    const installedAssets=category=>downloadedAssets.value.filter(item=>item.category===category);
    async function refreshDownloadedAssets(){
      const revision=++downloadedRevision;downloadedLoading.value=true;
      try{
        const reply=await rpc.invoke('video.getFreeAssetCatalog',{});
        if(!disposed&&revision===downloadedRevision){
          const unique=new Map((reply.items||[]).filter(item=>item.installed&&['transition','sticker','effect'].includes(item.category)).map(item=>[item.id,item]));
          downloadedAssets.value=[...unique.values()];downloadedError.value='';
        }
      }catch(reason){if(!disposed&&revision===downloadedRevision)downloadedError.value=tlMessage(reason);}
      finally{if(!disposed&&revision===downloadedRevision)downloadedLoading.value=false;}
    }
    const library=ref('media'),snapping=ref(true),snapGuide=ref(null),filmstrips=ref({});
    let savedWorkspace={};try{savedWorkspace=JSON.parse(localStorage.getItem(WORKSPACE_KEY)||'{}')||{};}catch{}
    const resourcesOpen=ref(savedWorkspace.resourcesOpen===true),propertiesOpen=ref(savedWorkspace.propertiesOpen===true);
    const persistWorkspace=()=>{try{localStorage.setItem(WORKSPACE_KEY,JSON.stringify({resourcesOpen:resourcesOpen.value,propertiesOpen:propertiesOpen.value}));}catch{}};
    const narrowWorkspace=()=>globalThis.matchMedia?.('(max-width: 760px)').matches===true;
    function toggleResources(){resourcesOpen.value=!resourcesOpen.value;if(resourcesOpen.value&&narrowWorkspace())propertiesOpen.value=false;persistWorkspace();}
    function toggleProperties(){propertiesOpen.value=!propertiesOpen.value;if(propertiesOpen.value&&narrowWorkspace())resourcesOpen.value=false;persistWorkspace();}
    function openLibrary(id,toggle=false){resourcesOpen.value=toggle&&library.value===id?!resourcesOpen.value:true;if(resourcesOpen.value&&narrowWorkspace())propertiesOpen.value=false;library.value=id;persistWorkspace();}
    function fitWorkspacePanels(){if(narrowWorkspace()&&resourcesOpen.value&&propertiesOpen.value){propertiesOpen.value=false;persistWorkspace();}}
    fitWorkspacePanels();globalThis.addEventListener?.('resize',fitWorkspacePanels);
    let timelineScroll=null,nextVideo=null,v2Canvas=null,playClock=0,playStart=0;
    const multiSelection=ref([]),clipboard=ref([]),imagePlayers=new Map();
    const marquee=ref(null),dropPreview=ref(null),waveforms=ref({});
    let autoScrollFrame=0,autoScrollEvent=null,marqueeCleanup=null;
    const waveformJobs=new Map();
    let reverseAudioContext=null;const reverseBuffers=new Map(),reverseNodes=new Map();
    let filmstripQueue=Promise.resolve();
    const thumbnailJobs=new Map(),thumbnailVideos=new Set();
    let disposed=false,transfer=null,gesture=null,frame=0,syncVersion=0,catalogVersion=0,exportVersion=0,currentMain='',pendingSeek=false,pendingURLs=new Map(),mainVideo=null,musicAudio=null,resultVideo=null;
    const overlayVideos=new Map(),audioPlayers=new Map(),mediaPaths=new WeakMap(),sourceRevisions=new Map(),verifiedSources=new Map(),pendingProbes=new Map(),sourceSession=M.uid('source');
    const mediaKey=path=>path+'\0'+(sourceRevisions.get(path)||sourceSession);
    try{const saved=localStorage.getItem(TIMELINE_KEY);if(saved)draft.value=M.normalizeDraft(JSON.parse(saved));}catch(reason){error.value='已保存草稿无法读取：'+tlMessage(reason);saveState.value='草稿读取失败';}
    const history=new M.TimelineHistory(draft.value);
    const duration=computed(()=>M.totalDuration(draft.value)),rows=computed(()=>M.layout(draft.value));
    const activeJoin=computed(()=>{const list=rows.value;for(let i=0;i<list.length-1;i++){const outgoing=list[i],incoming=list[i+1];if(outgoing.overlap>0&&playhead.value>=incoming.start&&playhead.value<outgoing.end)return {outgoing,incoming,progress:tlClamp((playhead.value-incoming.start)/outgoing.overlap,0,1),type:outgoing.transitionToNext.type};}return null;});
    const busy=computed(()=>importing.value||exporting.value),assets=computed(()=>new Map(draft.value.assets.map(asset=>[asset.id,asset])));
    const audioAssets=computed(()=>new Map(draft.value.audioAssets.map(asset=>[asset.id,asset])));
    const selected=computed(()=>selection.value.kind==='clip'?draft.value.clips.find(x=>x.id===selection.value.id):selection.value.kind==='overlay'?draft.value.overlays.find(x=>x.id===selection.value.id):selection.value.kind==='audio'?draft.value.audioClips.find(x=>x.id===selection.value.id):selection.value.kind==='text'?draft.value.texts.find(x=>x.id===selection.value.id):null);
    const selectedRows=computed(()=>pickSelectedItems(draft.value,multiSelection.value,item=>isLocked(item)));
    const selectedBounds=computed(()=>selectionSpan(selectedRows.value));
    const musicPath=computed(()=>draft.value.music?.path||catalog.value.find(track=>track.id===draft.value.music?.trackId)?.path||'');
    const ratioNumber=computed(()=>{if(draft.value.settings.ratio!=='自动'){const [w,h]=draft.value.settings.ratio.split(':').map(Number);return w/h;}const asset=assets.value.get(draft.value.clips[0]?.assetId)||draft.value.assets[0];return asset?asset.width/asset.height:16/9;});
    const ratio=computed(()=>String(ratioNumber.value));
    const canvasWidth=computed(()=>{const aspect=ratioNumber.value,asset=assets.value.get(draft.value.clips[0]?.assetId),resolution=draft.value.settings.resolution;let width,height;if(resolution==='原画'){const side=Math.min(3840,Math.max(asset?.width||1920,asset?.height||1080));[width,height]=aspect>=1?[side,side/aspect]:[side*aspect,side];}else{const side={'720p':720,'1080p':1080,'2K':1440,'4K':2160}[resolution];[width,height]=aspect>=1?[side*aspect,side]:[side,side/aspect];const scale=Math.min(1,3840/Math.max(width,height));width*=scale;}return Math.max(2,Math.round(width/2)*2);});
    const tasks=computed(()=>(store.tasks||[]).filter(task=>task.location?.route==='/video-tools'&&/时间线/.test(task.name||'')).slice(0,3));
    const activeOverlays=computed(()=>draft.value.overlays.filter(clip=>!clip.hidden&&playhead.value>=clip.start&&playhead.value<Math.min(duration.value,clip.start+M.clipDuration(clip))));
    const activeTexts=computed(()=>draft.value.texts.filter(text=>!text.hidden&&playhead.value>=text.start&&playhead.value<Math.min(duration.value,text.end)));
    const trackWidth=computed(()=>Math.max(680,Math.ceil(duration.value*zoom.value+70)));
    const v2Media=()=>new Map([...overlayVideos,...imagePlayers]);
    function drawV2(){if(draft.value.version>=2)drawTimeline(v2Canvas,draft.value,playhead.value,v2Media(),selection.value);}
    function isLocked(item){return draft.value.version>=2&&draft.value.tracks.find(t=>t.id===item?.trackId)?.locked;}
    const trackAccepts=M.trackAccepts;
    function fail(reason){if(!disposed)error.value=tlMessage(reason);}
    function setSkin(value){if(!skinValues.has(value))return;skin.value=value;try{localStorage.setItem(SKIN_KEY,value);}catch{}applySkin(value);status.value=`已切换为${SKINS.find(item=>item.value===value)?.label||value}皮肤`;}
    function save(){try{const persisted={...draft.value,assets:draft.value.assets.map(asset=>({...asset,preview:''}))};localStorage.setItem(TIMELINE_KEY,JSON.stringify(persisted));saveState.value='草稿已保存';}catch{saveState.value='本机存储已满，请保留当前窗口';}}
    const previewOf=asset=>asset?.preview||thumbnails.value[asset?.id]||'';
    async function buildFilmstrip(asset){
      if(asset.kind==='image'||typeof document==='undefined'||filmstrips.value[asset.id]||thumbnailJobs.has(asset.id))return;
      const revision=mediaKey(asset.path),job=filmstripQueue.then(async()=>{let video;try{if(disposed||revision!==mediaKey(asset.path))return;const url=await urlFor(asset.path);if(disposed)return;video=document.createElement('video');thumbnailVideos.add(video);video.muted=true;video.preload='auto';video.crossOrigin='anonymous';
        const wait=type=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>finish(Error('thumbnail timeout')),4000),finish=error=>{clearTimeout(timer);video.removeEventListener(type,onReady);video.removeEventListener('error',onError);error?reject(error):resolve();},onReady=()=>finish(),onError=()=>finish(Error('thumbnail decode'));video.addEventListener(type,onReady,{once:true});video.addEventListener('error',onError,{once:true});});
        const ready=wait('loadeddata');video.src=url;await ready;
        const canvas=document.createElement('canvas');canvas.width=160;canvas.height=Math.max(2,Math.round(160*asset.height/asset.width));const context=canvas.getContext('2d'),images=[];if(!context)return;
        for(let i=0;i<6&&!disposed;i++){const at=Math.min(asset.duration-.02,Math.max(.001,asset.duration*(i+.5)/6));const sought=wait('seeked');video.currentTime=at;await sought;context.drawImage(video,0,0,canvas.width,canvas.height);images.push(canvas.toDataURL('image/jpeg',.62));}
        if(!disposed&&revision===mediaKey(asset.path)&&images.length)filmstrips.value={...filmstrips.value,[asset.id]:images};
      }catch{}finally{if(video){video.pause();video.removeAttribute('src');video.load();thumbnailVideos.delete(video);}thumbnailJobs.delete(asset.id);if(!disposed&&revision!==mediaKey(asset.path)){const latest=draft.value.assets.find(row=>row.id===asset.id);if(latest)buildFilmstrip(latest);}}});thumbnailJobs.set(asset.id,job);filmstripQueue=job.catch(()=>{});
    }
    async function buildWaveform(asset){
      if(!asset?.path||typeof document==='undefined')return;
      const revision=mediaKey(asset.path),existing=waveforms.value[asset.path];
      if(existing?.revision===revision||waveformJobs.has(revision))return;
      const job=decodeWaveform(await urlFor(asset.path),128).then(peaks=>{
        if(!disposed&&revision===mediaKey(asset.path))waveforms.value={...waveforms.value,[asset.path]:{revision,peaks}};
      }).catch(()=>{}).finally(()=>waveformJobs.delete(revision));
      waveformJobs.set(revision,job);
    }
    async function restoreThumbnails(){for(const asset of draft.value.assets.filter(row=>!row.preview)){if(disposed)return;const revision=mediaKey(asset.path);try{const metadata=await ensureSource(asset.path);if(disposed)return;if(revision===mediaKey(asset.path)&&draft.value.assets.some(row=>row.id===asset.id&&row.path===asset.path)&&typeof metadata?.preview==='string'&&metadata.preview.startsWith('data:image/'))thumbnails.value={...thumbnails.value,[asset.id]:metadata.preview};}catch{if(disposed)return;}}}
    function apply(next,commit=true){if(disposed)return;draft.value=commit?history.commit(next):next;playhead.value=tlClamp(playhead.value,0,duration.value);result.value='';resultUrl.value='';error.value='';}
    function edit(action){if(busy.value||gesture)return;try{apply(action(draft.value));}catch(reason){fail(reason);}}
    function select(kind,id,seek=false,event){
      const next={kind,id},ordered=M.allItems(draft.value).sort((a,b)=>(a.item.start||0)-(b.item.start||0)||a.kind.localeCompare(b.kind));
      if(event?.shiftKey&&selection.value.id){
        const from=ordered.findIndex(row=>row.item.id===selection.value.id),to=ordered.findIndex(row=>row.item.id===id);
        if(from>=0&&to>=0){
          const range=ordered.slice(Math.min(from,to),Math.max(from,to)+1).map(row=>({kind:row.kind,id:row.item.id}));
          multiSelection.value=range;
          selection.value=next;
          if(seek)setTime(ordered.find(row=>row.item.id===id)?.item.start||0);
          return;
        }
      }
      selection.value=next;
      if(event?.ctrlKey||event?.metaKey){
        const found=multiSelection.value.some(row=>row.id===id);
        multiSelection.value=found?multiSelection.value.filter(row=>row.id!==id):[...multiSelection.value,next];
      }else multiSelection.value=[next];
      if(seek){const row=ordered.find(item=>item.kind===kind&&item.item.id===id)?.item;if(row)setTime(row.start);}
    }
    function startMarquee(event){
      if(event.button!==0||busy.value||event.target?.closest?.('.tl-block'))return;
      const content=event.currentTarget.closest?.('.tl-track-content');if(!content)return;
      event.preventDefault();event.stopPropagation();pause();
      const additive=event.shiftKey||event.ctrlKey||event.metaKey,initial=additive?[...multiSelection.value]:[];
      if(!additive){multiSelection.value=[];selection.value={kind:'',id:''};}
      const bounds=content.getBoundingClientRect(),origin={x:event.clientX,y:event.clientY},startScroll={left:content.parentElement?.scrollLeft||0,top:content.parentElement?.scrollTop||0};
      const update=current=>{
        const box={left:Math.min(origin.x,current.clientX)-bounds.left,top:Math.min(origin.y,current.clientY)-bounds.top,right:Math.max(origin.x,current.clientX)-bounds.left,bottom:Math.max(origin.y,current.clientY)-bounds.top};
        marquee.value={...box,width:box.right-box.left,height:box.bottom-box.top};
        const matches=[...content.querySelectorAll('[data-kind][data-item-id]')].filter(element=>marqueeIntersects(element.getBoundingClientRect(),{left:Math.min(origin.x,current.clientX),right:Math.max(origin.x,current.clientX),top:Math.min(origin.y,current.clientY),bottom:Math.max(origin.y,current.clientY)})).map(element=>({kind:element.dataset.kind,id:element.dataset.itemId}));
        multiSelection.value=[...new Map([...initial,...matches].map(row=>[`${row.kind}:${row.id}`,row])).values()];
        selection.value=matches[0]||initial[0]||{kind:'',id:''};
      };
      const move=current=>{current.preventDefault();update(current)};
      const end=()=>{stopMarquee();};
      marqueeCleanup=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);event.currentTarget?.releasePointerCapture?.(event.pointerId)};
      window.addEventListener('pointermove',move,{passive:false});window.addEventListener('pointerup',end,{once:true});window.addEventListener('pointercancel',end,{once:true});
    }
    function stopMarquee(){marqueeCleanup?.();marqueeCleanup=null;marquee.value=null;}
    function stopAutoScroll(){if(autoScrollFrame)cancelAnimationFrame(autoScrollFrame);autoScrollFrame=0;autoScrollEvent=null;}
    function moveAutoScroll(event){
      if(!gesture||gesture.pointerId!==event.pointerId||!timelineScroll)return;
      autoScrollEvent=event;const bounds=timelineScroll.getBoundingClientRect();gesture.autoScrollSpeed=autoScrollSpeed(event.clientX,bounds.left,bounds.right);
      if(!gesture.autoScrollSpeed){if(autoScrollFrame)cancelAnimationFrame(autoScrollFrame);autoScrollFrame=0;return;}
      if(autoScrollFrame)return;
      const tick=()=>{
        if(!gesture||!gesture.autoScrollSpeed||!autoScrollEvent){autoScrollFrame=0;return;}
        timelineScroll.scrollLeft=Math.max(0,timelineScroll.scrollLeft+gesture.autoScrollSpeed);
        const g=gesture;gestureMove(g,autoScrollEvent);autoScrollFrame=requestAnimationFrame(tick);
      };
      autoScrollFrame=requestAnimationFrame(tick);
    }
    function patchSelected(key,value){const item=selected.value;if(!item||isLocked(item))return;if(draft.value.version>=2){edit(d=>M.updateItem(d,selection.value.kind,item.id,{[key]:value}));return;}const method=selection.value.kind==='clip'?M.updateClip:selection.value.kind==='overlay'?M.updateOverlay:selection.value.kind==='audio'?M.updateAudioClip:M.updateText;edit(d=>method(d,item.id,{[key]:value}));}
    function advancedPatch(patch){const item=selected.value;if(item)edit(d=>{let next=M.updateItem(d,selection.value.kind,item.id,patch);const local=Math.max(0,Math.min(M.itemDuration(item),playhead.value-(item.start??rows.value.find(r=>r.id===item.id)?.start??0)));for(const property of ['x','y','opacity','rotation'])if(patch.transform?.[property]!==undefined&&item.keyframes?.[property]?.length)next=M.setKeyframe(next,selection.value.kind,item.id,property,local,patch.transform[property]);if(patch.volume!==undefined&&item.keyframes?.volume?.length)next=M.setKeyframe(next,selection.value.kind,item.id,'volume',local,patch.volume);return next;});}
    function numberSelected(key,event){const value=Number(event.target.value);if(event.target.value===''||!Number.isFinite(value)){fail('请输入有效数字');return;}patchSelected(key,value);}
    function undo(){if(busy.value)return;pause();apply(history.undo(),false);}
    function redo(){if(busy.value)return;pause();apply(history.redo(),false);}
    async function ensureSource(path){
      const audio=draft.value.audioAssets.find(asset=>asset.path===path),video=draft.value.assets.find(asset=>asset.path===path),music=musicPath.value===path;
      if(!audio&&!video&&!music)return null;
      const revision=mediaKey(path);if(verifiedSources.has(revision))return verifiedSources.get(revision);
      if(!pendingProbes.has(revision))pendingProbes.set(revision,rpc.invoke(audio||music?'video.audioProbe':video?.kind==='image'?'video.imageProbe':'video.probe',{path}).then(metadata=>{if(disposed)return metadata;const expected=audio||video;if(expected){const fields=audio?['duration']:['duration','width','height','hasAudio'];if(fields.some(field=>metadata[field]!==expected[field]))throw Error('素材已变化，请先移除对应片段再重新导入');}if(revision===mediaKey(path))verifiedSources.set(revision,metadata);return metadata;}).finally(()=>pendingProbes.delete(revision)));
      return pendingProbes.get(revision);
    }
    async function urlFor(path){if(!path)return'';await ensureSource(path);if(urls.value[path])return urls.value[path];const revision=mediaKey(path),requestKey=revision;if(!pendingURLs.has(requestKey))pendingURLs.set(requestKey,rpc.invoke('media.getUrl',{path}).then(value=>{if(typeof value!=='string'||!value)throw Error('无法取得媒体播放地址');const url=value+(value.includes('?')?'&':'?')+'aive_source='+encodeURIComponent(revision.split('\0')[1]);if(!disposed&&revision===mediaKey(path))urls.value={...urls.value,[path]:url};return url;}).finally(()=>pendingURLs.delete(requestKey)));return pendingURLs.get(requestKey);}
    function refreshSource(path,assetId,audio=false){const oldKey=mediaKey(path);sourceRevisions.set(path,M.uid('source'));const nextURLs={...urls.value},nextWaves={...waveforms.value};delete nextURLs[path];delete nextWaves[path];urls.value=nextURLs;waveforms.value=nextWaves;for(const el of [mainVideo,nextVideo,musicAudio,...overlayVideos.values(),...audioPlayers.values()])if(el&&mediaPaths.get(el)===oldKey){stopElement(el);el.removeAttribute('src');el.load();mediaPaths.delete(el);}if(audio){const asset=draft.value.audioAssets.find(row=>row.id===assetId||row.path===path);if(asset)buildWaveform(asset);}else{const nextThumbs={...thumbnails.value},nextStrips={...filmstrips.value};delete nextThumbs[assetId];delete nextStrips[assetId];thumbnails.value=nextThumbs;filmstrips.value=nextStrips;const asset=draft.value.assets.find(row=>row.id===assetId);if(asset)buildFilmstrip(asset);}}
    function stopElement(el){try{el?.pause();}catch{}}
    function stopReverse(id){const node=reverseNodes.get(id);if(node){try{node.source.stop();}catch{}node.source.disconnect();node.gain.disconnect();reverseNodes.delete(id);}}
    function stopAll(){stopElement(mainVideo);stopElement(nextVideo);stopElement(musicAudio);stopElement(resultVideo);for(const el of overlayVideos.values())stopElement(el);for(const el of audioPlayers.values())stopElement(el);for(const id of reverseNodes.keys())stopReverse(id);}
    function pause(){playing.value=false;++syncVersion;if(frame){cancelAnimationFrame(frame);frame=0;}stopAll();}
    function mediaError(event){pause();fail(event?.target?.error?.message||'此素材无法在预览播放器中解码，请使用 MP4（H.264/AAC）素材。导出时会重新检查原始文件。');}
    async function configure(el,path,time,speed,volume,shouldPlay,force,version,loop=false){
      if(!el||!path)return;const url=await urlFor(path);if(disposed||version!==syncVersion||!props.active)return;
      if(mediaPaths.get(el)!==mediaKey(path)){stopElement(el);el.src=url;mediaPaths.set(el,mediaKey(path));force=true;}
      el.playbackRate=speed;el.volume=tlClamp(volume,0,1);el.muted=volume===0;el.loop=loop;
      let sourceTime=Math.max(0,time);if(loop&&Number.isFinite(el.duration)&&el.duration>0)sourceTime%=el.duration;
      if(force||Math.abs((Number(el.currentTime)||0)-sourceTime)>.18)try{el.currentTime=sourceTime;}catch{}
      if(shouldPlay){if(el.paused)try{await el.play();if(disposed||!props.active||!playing.value)stopElement(el);}catch(reason){if(version===syncVersion){pause();fail('预览播放失败：'+tlMessage(reason));}}}else stopElement(el);
    }
    async function syncMedia(force=false){
      if(force)pendingSeek=true;force=pendingSeek;
      const version=++syncVersion;if(disposed||!props.active){stopAll();return;}
      if(draft.value.version>=2){await syncV2Media(force,version);return;}
      const row=M.locate(draft.value,playhead.value),shouldPlay=playing.value&&playhead.value<duration.value;
      if(!row){stopAll();currentMain='';return;}
      const asset=assets.value.get(row.clip.assetId),changed=currentMain!==row.clip.id;currentMain=row.clip.id;
      const join=activeJoin.value,work=[configure(mainVideo,asset.path,row.sourceTime,row.clip.speed,row.clip.muted?0:row.clip.volume*(join?1-join.progress:1),shouldPlay,force||changed,version)];
      if(join){const incoming=join.incoming;work.push(configure(nextVideo,assets.value.get(incoming.assetId).path,incoming.trimStart+(playhead.value-incoming.start)*incoming.speed,incoming.speed,incoming.muted?0:incoming.volume*join.progress,shouldPlay,force,version));}else stopElement(nextVideo);
      for(const clip of draft.value.overlays){const el=overlayVideos.get(clip.id),live=!clip.hidden&&playhead.value>=clip.start&&playhead.value<Math.min(duration.value,clip.start+M.clipDuration(clip));if(!live){stopElement(el);continue;}work.push(configure(el,assets.value.get(clip.assetId).path,clip.trimStart+(playhead.value-clip.start)*clip.speed,clip.speed,clip.muted?0:clip.volume,shouldPlay,force,version));}
      for(const clip of draft.value.audioClips){const el=audioPlayers.get(clip.id),live=playhead.value>=clip.start&&playhead.value<Math.min(duration.value,clip.start+M.clipDuration(clip));if(!live){stopElement(el);continue;}work.push(configure(el,audioAssets.value.get(clip.assetId).path,clip.trimStart+(playhead.value-clip.start)*clip.speed,clip.speed,clip.muted?0:clip.volume,shouldPlay,force,version));}
      if(draft.value.music&&musicPath.value){const exhausted=!draft.value.music.loop&&Number.isFinite(musicAudio?.duration)&&musicAudio.duration>0&&playhead.value>=musicAudio.duration;work.push(configure(musicAudio,musicPath.value,playhead.value,1,draft.value.music.volume,shouldPlay&&!exhausted,force,version,draft.value.music.loop));}else stopElement(musicAudio);
      try{await Promise.all(work);if(version===syncVersion)pendingSeek=false;}catch(reason){if(!disposed&&version===syncVersion){pause();fail(reason);}}
    }
    async function syncV2Media(force,version){
      stopElement(mainVideo);stopElement(nextVideo);const tracks=new Map(draft.value.tracks.map(t=>[t.id,t])),work=[],live=playing.value&&playhead.value<duration.value;
      for(const {kind,item}of M.allItems(draft.value)){const track=tracks.get(item.trackId),active=!item.hidden&&!track?.hidden&&playhead.value>=item.start&&playhead.value<item.start+M.itemDuration(item);if(kind==='text'||item.type==='solid')continue;const asset=(kind==='audio'?audioAssets:assets).value.get(item.assetId);if(!asset)continue;
        if(asset.kind==='image'){if(active)work.push(urlFor(asset.path));continue;}
        const el=kind==='audio'?audioPlayers.get(item.id):overlayVideos.get(item.id);if(!active){stopElement(el);stopReverse(item.id);continue;}const local=playhead.value-item.start,k=M.evaluateKeyframes(item,local),volume=track?.muted||draft.value.output.audio===false?0:k.volume;
        work.push(configure(el,asset.path,M.sourceTimeAt(item,local,draft.value.settings.fps),item.speed,item.reverse?0:volume,live&&!item.reverse&&item.freezeAt==null&&(!item.freezeTail||local<M.itemDuration(item)-item.freezeTail),force||item.reverse,version));
        if(item.reverse&&(kind==='audio'||asset.hasAudio))work.push(syncReverseAudio(item,asset,local,volume,live,force,version));else stopReverse(item.id);
      }
      if(draft.value.music&&musicPath.value)work.push(configure(musicAudio,musicPath.value,playhead.value,1,draft.value.output.audio===false?0:draft.value.music.volume,live,force,version,draft.value.music.loop));else stopElement(musicAudio);
      try{await Promise.all(work);if(version===syncVersion){pendingSeek=false;drawV2();}}catch(reason){if(!disposed&&version===syncVersion){pause();fail(reason);}}
    }
    async function syncReverseAudio(item,asset,local,volume,live,force,version){
      if(!live||volume<=0){stopReverse(item.id);return;}const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;if(!Audio)throw Error('当前浏览器不支持倒放音频预览');if(!reverseAudioContext)reverseAudioContext=new Audio();await reverseAudioContext.resume();const cacheKey=mediaKey(asset.path);if(!reverseBuffers.has(cacheKey))reverseBuffers.set(cacheKey,(async()=>{const response=await fetch(await urlFor(asset.path));if(!response.ok)throw Error('倒放音频读取失败');const buffer=await reverseAudioContext.decodeAudioData(await response.arrayBuffer());for(let channel=0;channel<buffer.numberOfChannels;channel++)buffer.getChannelData(channel).reverse();return buffer;})().catch(reason=>{reverseBuffers.delete(cacheKey);throw reason;}));const buffer=await reverseBuffers.get(cacheKey);if(disposed||!playing.value||version!==syncVersion)return;let node=reverseNodes.get(item.id);if(force||!node||node.cacheKey!==cacheKey){stopReverse(item.id);const source=reverseAudioContext.createBufferSource(),gain=reverseAudioContext.createGain();source.buffer=buffer;source.playbackRate.value=item.speed;source.connect(gain);gain.connect(reverseAudioContext.destination);const offset=Math.max(0,buffer.duration-item.trimEnd+local*item.speed),length=Math.min(buffer.duration-offset,(M.itemDuration(item)-local)*item.speed);if(length<=0)return;source.start(0,offset,length);node={source,gain,cacheKey};reverseNodes.set(item.id,node);}node.gain.gain.setValueAtTime(tlClamp(volume,0,1),reverseAudioContext.currentTime);
    }
    function nextFrame(){
      frame=0;if(disposed||!props.active||!playing.value)return;
      if(draft.value.version>=2){const at=playStart+(performance.now()-playClock)/1000;playhead.value=Math.min(duration.value,at);drawV2();if(at>=duration.value){pause();return;}frame=requestAnimationFrame(nextFrame);return;}
      const row=M.locate(draft.value,playhead.value);
      if(!row){pause();return;}
      if(mainVideo&&currentMain===row.clip.id&&mediaPaths.get(mainVideo)===mediaKey(assets.value.get(row.clip.assetId).path)&&!mainVideo.seeking&&mainVideo.readyState>=2){
        const at=row.start+(mainVideo.currentTime-row.clip.trimStart)/row.clip.speed;
        if(mainVideo.ended||at>=row.end-.012){if(row.end>=duration.value-.012){playhead.value=duration.value;pause();syncMedia(true);return;}playhead.value=row.end;syncMedia(true);}
        else if(at>=row.start-.05)playhead.value=tlClamp(at,row.start,row.end);
      }
      frame=requestAnimationFrame(nextFrame);
    }
    async function togglePlay(){if(!duration.value||!props.active)return;if(playing.value){pause();return;}error.value='';if(playhead.value>=duration.value-.01)playhead.value=0;playing.value=true;playStart=playhead.value;playClock=performance.now();await syncMedia(true);if(playing.value&&!disposed&&!frame)frame=requestAnimationFrame(nextFrame);}
    function setTime(value){playhead.value=tlClamp(Number(value)||0,0,duration.value);syncMedia(true);}
    function videoEnded(){if(!playing.value)return;const row=M.locate(draft.value,playhead.value);if(row&&row.end<duration.value-.01){playhead.value=row.end;syncMedia(true);}else{playhead.value=duration.value;pause();}}
    function addMain(assetId){if(assets.value.get(assetId)?.kind==='image'){addImage(assetId);return;}edit(d=>M.appendClip(d,assetId));const last=draft.value.clips.at(-1);if(last)select('clip',last.id);}
    function addOverlay(assetId){if(assets.value.get(assetId)?.kind==='image'){addImage(assetId);return;}edit(d=>M.addOverlay(d,assetId,Math.min(playhead.value,Math.max(0,duration.value-.05))));const last=draft.value.overlays.at(-1);if(last)select('overlay',last.id);}
    function addText(){edit(d=>M.addText(d,{start:Math.min(playhead.value,Math.max(0,duration.value-.05))}));const last=draft.value.texts.at(-1);if(last)select('text',last.id);}
    function split(){if(selected.value&&draft.value.version>=2){edit(d=>M.splitItem(d,selection.value.kind,selection.value.id,playhead.value));return;}edit(d=>selection.value.kind==='audio'?M.splitAudioAt(d,playhead.value,selection.value.id):selection.value.kind==='overlay'||selection.value.kind==='text'?M.splitItem(d,selection.value.kind,selection.value.id,playhead.value):M.splitAt(d,playhead.value));}
    function removeSelected(ripple=false){const item=selected.value;if(!item)return;if(draft.value.version>=2||ripple||multiSelection.value.length>1)edit(d=>M.deleteItems(d,multiSelection.value.length?multiSelection.value:[selection.value],ripple));else edit(d=>(selection.value.kind==='clip'?M.removeClip:selection.value.kind==='overlay'?M.removeOverlay:selection.value.kind==='audio'?M.removeAudioClip:M.removeText)(d,item.id));selection.value={kind:'',id:''};multiSelection.value=[];}
    function copySelection(cut=false){if(!selected.value)return;try{clipboard.value=M.copyItems(draft.value,multiSelection.value.length?multiSelection.value:[selection.value]);if(cut)removeSelected();}catch(reason){fail(reason);}}
    function pasteSelection(){if(clipboard.value.length)edit(d=>M.pasteItems(d,clipboard.value,playhead.value));}
    function duplicate(){const item=selected.value;if(!item)return;if(draft.value.version>=2){try{const copied=M.copyItems(draft.value,multiSelection.value.length?multiSelection.value:[selection.value]);edit(d=>M.pasteItems(d,copied,item.start+M.itemDuration(item)));}catch(reason){fail(reason);}return;}if(selection.value.kind==='clip'){edit(d=>M.duplicateClip(d,item.id));return;}if(selection.value.kind==='audio'){edit(d=>M.duplicateAudioClip(d,item.id));return;}if(selection.value.kind==='text'){edit(d=>M.addText(d,{...item,start:item.start,end:item.end}));return;}edit(d=>{let next=M.addOverlay(d,item.assetId,item.start);return M.updateOverlay(next,next.overlays.at(-1).id,{...item,id:next.overlays.at(-1).id});});}
    function moveSelected(delta){const index=draft.value.clips.findIndex(x=>x.id===selection.value.id);if(index>=0&&index+delta>=0&&index+delta<draft.value.clips.length)edit(d=>M.moveClip(d,selection.value.id,index+delta));}
    function fitTimeline(){zoom.value=tlClamp(Math.floor(((timelineScroll?.clientWidth||950)-110)/Math.max(1,duration.value)),2,160);if(timelineScroll)timelineScroll.scrollLeft=0;}
    function snapTime(value,kind,id,length=0){
      const base=gesture?.base||draft.value,fps=base.settings.fps,rounded=Math.round(value*fps)/fps;snapGuide.value=null;if(!snapping.value)return rounded;
      const anchors=[0,playhead.value,M.totalDuration(base),...(base.markers||[]).map(m=>m.time)];for(const row of M.layout(base))if(kind!=='clip'||row.id!==id)anchors.push(row.start,row.end);for(const row of base.overlays)if(kind!=='overlay'||row.id!==id)anchors.push(row.start,row.start+M.clipDuration(row));for(const row of base.audioClips)if(kind!=='audio'||row.id!==id)anchors.push(row.start,row.start+M.clipDuration(row));for(const row of base.texts)if(kind!=='text'||row.id!==id)anchors.push(row.start,row.end);
      let best=8/zoom.value,answer=rounded;for(const anchor of anchors)for(const edge of length?[0,length]:[0]){const distance=Math.abs(anchor-(rounded+edge));if(distance<best){best=distance;answer=anchor-edge;snapGuide.value=anchor;}}return answer;
    }
    function startTimed(event,item,kind,edge='move'){
      if(event.button!==0||busy.value||isLocked(item))return;event.stopPropagation();event.preventDefault();pause();if(!(event.ctrlKey||event.metaKey)&&!multiSelection.value.some(s=>s.id===item.id))select(kind,item.id);gesture={kind:'timed',item:{...item},itemKind:kind,edge,multi:multiSelection.value.length>1,base:draft.value,x:event.clientX,pointerId:event.pointerId,scrollLeft:timelineScroll?.scrollLeft||0};event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    function startVisual(event){if(event.button!==0||busy.value)return;const bounds=event.currentTarget.getBoundingClientRect(),x=(event.clientX-bounds.left)/bounds.width,y=(event.clientY-bounds.top)/bounds.height,tracks=new Map(draft.value.tracks.map(t=>[t.id,t]));const candidates=M.allItems(draft.value).filter(({kind,item})=>kind!=='audio'&&!item.hidden&&!tracks.get(item.trackId)?.hidden&&playhead.value>=item.start&&playhead.value<item.start+M.itemDuration(item)).sort((a,b)=>(tracks.get(b.item.trackId)?.order||0)-(tracks.get(a.item.trackId)?.order||0)||b.item.start-a.item.start);for(const {kind,item}of candidates){const t=item.transform,k=M.evaluateKeyframes(item,playhead.value-item.start),cx=k.x+t.width/2,cy=k.y+t.height/2,angle=-k.rotation*Math.PI/180,dx=x-cx,dy=(y-cy)/ratioNumber.value,rx=(dx*Math.cos(angle)-dy*Math.sin(angle))/k.scale,ry=(dx*Math.sin(angle)+dy*Math.cos(angle))*ratioNumber.value/k.scale;if(Math.abs(rx)<=t.width/2&&Math.abs(ry)<=t.height/2){select(kind,item.id);if(isLocked(item))return;event.preventDefault();pause();gesture={kind:'visual',itemKind:kind,item:{...item,transform:{...item.transform,x:k.x,y:k.y}},base:draft.value,x:event.clientX,y:event.clientY,bounds,pointerId:event.pointerId,resize:Math.abs(rx-t.width/2)<12/bounds.width&&Math.abs(ry-t.height/2)<12/bounds.height};event.currentTarget.setPointerCapture?.(event.pointerId);drawV2();return;}}selection.value={kind:'',id:''};multiSelection.value=[];drawV2();}
    function moveTimed(g,event){
      const item=g.item,delta=(event.clientX-g.x+((Number(timelineScroll?.scrollLeft)||0)-(g.scrollLeft||0)))/zoom.value,isText=g.itemKind==='text',end=isText?item.end:item.start+M.clipDuration(item),length=end-item.start,patch={};
      if(g.edge==='move')patch.start=tlClamp(snapTime(item.start+delta,g.itemKind,item.id,length),0,86400-length);
      else if(isText){if(g.edge==='left')patch.start=tlClamp(snapTime(item.start+delta,g.itemKind,item.id),0,end-.05);else patch.end=tlClamp(snapTime(end+delta,g.itemKind,item.id),item.start+.05,86400);}
      else if(g.edge==='left'){const start=tlClamp(snapTime(item.start+delta,g.itemKind,item.id),Math.max(0,item.start-item.trimStart/item.speed),end-.05);patch.start=start;patch.trimStart=item.trimStart+(start-item.start)*item.speed;}
      else{const asset=(g.itemKind==='audio'?audioAssets:assets).value.get(item.assetId),at=tlClamp(snapTime(end+delta,g.itemKind,item.id),item.start+.05,item.start+(asset.duration-item.trimStart)/item.speed);patch.trimEnd=item.trimStart+(at-item.start)*item.speed;}
      if(isText&&g.edge==='move')patch.end=patch.start+length;
      if(item.duration!==undefined&&g.edge!=='move'){if(g.edge==='left'){patch.start=tlClamp(snapTime(item.start+delta,g.itemKind,item.id),0,end-.05);patch.duration=end-patch.start;delete patch.trimStart;}else{patch.duration=Math.max(.05,end+delta-item.start);delete patch.trimEnd;}}
      if(g.base.version>=2&&g.edge==='move'&&g.multi){let next=g.base;const change=patch.start-item.start;for(const {kind,item:row}of pickSelectedItems(g.base,multiSelection.value,item=>isLocked(item)))next=M.updateItem(next,kind,row.id,{start:Math.max(0,row.start+change)});apply(next,false);}else apply(g.base.version>=2?M.updateItem(g.base,g.itemKind,item.id,patch):(isText?M.updateText:g.itemKind==='audio'?M.updateAudioClip:M.updateOverlay)(g.base,item.id,patch),false);
    }
    function startTrim(event,clip,edge){if(event.button!==0||busy.value)return;event.stopPropagation();event.preventDefault();pause();selection.value={kind:'clip',id:clip.id};gesture={kind:'trim',base:draft.value,clip:{...clip},row:rows.value.find(row=>row.id===clip.id),edge,x:event.clientX,pointerId:event.pointerId,scrollLeft:timelineScroll?.scrollLeft||0};event.currentTarget.setPointerCapture?.(event.pointerId);}
    function startOverlayMove(event,clip){if(event.button!==0||busy.value)return;event.stopPropagation();event.preventDefault();pause();selection.value={kind:'overlay',id:clip.id};const bounds=event.currentTarget.parentElement?.getBoundingClientRect();if(!bounds?.width||!bounds?.height)return;gesture={kind:'rect',base:draft.value,clip:{...clip},x:event.clientX,y:event.clientY,bounds,pointerId:event.pointerId};event.currentTarget.setPointerCapture?.(event.pointerId);}
    function snapGroupTime(value){
      const base=gesture?.base||draft.value,excluded=selectedRows.value.map(row=>row.id),items=M.allItems(base).map(row=>row.item);
      const anchors=collectAnchors(items,excluded,[playhead.value,M.totalDuration(base),...(base.markers||[]).map(marker=>marker.time)]);
      const result=nearestSnap(value,anchors,8/zoom.value,base.settings.fps);snapGuide.value=result.anchor;return result.time;
    }
    function applyGroupResize(base,changes){
      let next=base;
      for(const change of changes||[]){
        const old=M.allItems(base).find(row=>row.kind===change.kind&&row.item.id===change.id)?.item;if(!old)continue;
        const duration=Math.max(.05,change.end-change.start),patch={start:change.start};
        if(old.duration!==undefined)patch.duration=duration;
        else if(change.kind==='text')patch.end=change.end;
        else patch.trimEnd=old.trimStart+duration*old.speed;
        next=M.updateItem(next,change.kind,change.id,patch);
      }
      return next;
    }
    function groupSourceLimit(items,span){
      let scale=Infinity;
      for(const {kind,item}of items||[]){
        if(kind==='text'||item.duration!==undefined)continue;
        const asset=(kind==='audio'?audioAssets:assets).value.get(item.assetId),current=M.itemDuration(item),speed=Number(item.speed)||1;
        if(!asset||!(current>0)||!(asset.duration>0)||!(speed>0)||item.freezeAt!=null||item.freezeTail)continue;
        const available=Math.max(0,(asset.duration-(Number(item.trimStart)||0))/speed);
        scale=Math.min(scale,available/current);
      }
      if(!Number.isFinite(scale))return {minimum:-Infinity,maximum:Infinity};
      const duration=span.duration*Math.max(0,scale);
      return {minimum:span.end-duration,maximum:span.start+duration};
    }
    function startGroupResize(event,edge){
      if(event.button!==0||busy.value||selectedRows.value.length<2)return;
      event.stopPropagation();event.preventDefault();pause();
      gesture={kind:'group-resize',edge,span:selectedBounds.value,items:selectedRows.value.map(row=>({kind:row.kind,item:{...row.item}})),base:draft.value,x:event.clientX,pointerId:event.pointerId,scrollLeft:timelineScroll?.scrollLeft||0};
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    function moveGroupResize(g,event){
      if(!g.span)return;
      const delta=(event.clientX-g.x+((Number(timelineScroll?.scrollLeft)||0)-(g.scrollLeft||0)))/zoom.value;
      const limit=groupSourceLimit(g.items,g.span),raw=g.edge==='left'?g.span.start+delta:g.span.end+delta;
      const at=tlClamp(snapGroupTime(raw),g.edge==='left'?limit.minimum:g.span.start+.05,g.edge==='left'?g.span.end-.05:limit.maximum);
      apply(applyGroupResize(g.base,resizeSelection(g.items,g.edge,at,g.base.settings.fps,.05)),false);
    }
    function startVolume(event,item,kind){
      if(event.button!==0||busy.value||isLocked(item))return;
      event.stopPropagation();event.preventDefault();pause();
      gesture={kind:'volume',base:draft.value,item:{...item},itemKind:kind,bounds:event.currentTarget.parentElement.getBoundingClientRect(),pointerId:event.pointerId};
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    function moveVolume(g,event){
      const ratio=tlClamp((event.clientY-g.bounds.top)/Math.max(1,g.bounds.height),0,1),db=12-ratio*72,volume=dbToGain(db);
      apply(M.updateItem(g.base,g.itemKind,g.item.id,{volume}),false);
    }
    function gestureMove(event){const g=gesture;if(!g||g.pointerId!==event.pointerId)return;event.stopPropagation();try{if(['timed','trim','group-resize'].includes(g.kind))moveAutoScroll(event);if(g.kind==='timed')moveTimed(g,event);else if(g.kind==='group-resize')moveGroupResize(g,event);else if(g.kind==='volume')moveVolume(g,event);else if(g.kind==='visual'){const t=g.item.transform,dx=(event.clientX-g.x)/g.bounds.width,dy=(event.clientY-g.y)/g.bounds.height;const patch=g.resize?{width:tlClamp(t.width+dx,.002,4),height:tlClamp(t.height+dy,.002,4)}:{x:tlClamp(t.x+dx,-4,4),y:tlClamp(t.y+dy,-4,4)};let next=M.updateItem(g.base,g.itemKind,g.item.id,{transform:patch});for(const property of ['x','y'])if(patch[property]!==undefined&&g.item.keyframes?.[property]?.length)next=M.setKeyframe(next,g.itemKind,g.item.id,property,playhead.value-g.item.start,patch[property]);apply(next,false);}else if(g.kind==='trim'){const clip=g.clip,asset=assets.value.get(clip.assetId),delta=(event.clientX-g.x+(timelineScroll?.scrollLeft-(g.scrollLeft||0)))/zoom.value,edge=snapTime(g.row.end+(g.edge==='left'?-delta:delta),'clip',clip.id),change=(edge-g.row.end)*clip.speed,key=g.edge==='left'?'trimStart':'trimEnd';const value=g.edge==='left'?tlClamp(clip.trimStart-change,0,clip.trimEnd-.05*clip.speed):tlClamp(clip.trimEnd+change,clip.trimStart+.05*clip.speed,asset.duration);apply(M.updateClip(g.base,clip.id,{[key]:value}),false);}else if(g.kind==='rect'){apply(M.updateOverlay(g.base,g.clip.id,{x:tlClamp(g.clip.x+(event.clientX-g.x)/g.bounds.width,0,1-g.clip.width),y:tlClamp(g.clip.y+(event.clientY-g.y)/g.bounds.height,0,1-g.clip.height)}),false);}}catch(reason){fail(reason);}}
    function gestureEnd(event,cancel=false){if(!gesture||gesture.pointerId!==event.pointerId)return;stopAutoScroll();if(cancel)draft.value=gesture.base;else{gestureMove(event);const g=gesture,trackId=draft.value.version>=2&&typeof document!=='undefined'?document.elementFromPoint?.(event.clientX,event.clientY)?.closest('[data-track-id]')?.getAttribute('data-track-id'):null;if(draft.value.version>=2&&g.kind==='timed'&&g.edge==='move'&&trackId)try{const target=draft.value.tracks.find(track=>track.id===trackId);if(target?.locked)throw Error('目标轨道已锁定');const rows=pickSelectedItems(draft.value,g.multi?multiSelection.value:[{kind:g.itemKind,id:g.item.id}],item=>isLocked(item));const movable=g.multi&&rows.length>1&&rows.every(row=>trackAccepts(target,row.kind))?rows:[{kind:g.itemKind,item:g.item}];for(const row of movable)draft.value=M.updateItem(draft.value,row.kind,row.item.id,{trackId});}catch(reason){fail(reason);}draft.value=history.commit(draft.value);}gesture=null;snapGuide.value=null;event.currentTarget.releasePointerCapture?.(event.pointerId);}
    function dragAsset(event,asset){event.dataTransfer?.setData('application/x-timeline-asset',asset.id);if(event.dataTransfer)event.dataTransfer.effectAllowed='copy';}
    function dragClip(event,clip){event.dataTransfer?.setData('application/x-timeline-clip',clip.id);if(event.dataTransfer)event.dataTransfer.effectAllowed='move';}
    function dragPayload(event){
      const transfer=event.dataTransfer;return {clip:transfer?.getData('application/x-timeline-clip')||'',asset:transfer?.getData('application/x-timeline-asset')||'',audio:transfer?.getData('application/x-timeline-audio')||''};
    }
    function showDropPreview(event,{track=null,main=false}={}){
      const payload=dragPayload(event);if(!payload.clip&&!payload.asset&&!payload.audio)return;
      const bounds=event.currentTarget.getBoundingClientRect(),content=event.currentTarget.closest('.tl-track-content'),contentBounds=content?.getBoundingClientRect()||bounds;
      const raw=Math.max(0,(event.clientX-bounds.left)/zoom.value),fps=draft.value.settings.fps;
      const moving=payload.clip?M.allItems(draft.value).find(row=>row.item.id===payload.clip)?.item:null;
      const asset=payload.asset?assets.value.get(payload.asset):null,audio=payload.audio?audioAssets.value.get(payload.audio):null;
      const duration=moving?M.itemDuration(moving):asset?(asset.kind==='image'?5:asset.duration):audio?.duration||0;
      let start=Math.round(raw*fps)/fps,index=null;
      if(main){index=mainInsertIndex(rows.value,raw);start=index<rows.value.length?rows.value[index].start:M.totalDuration(draft.value);}
      const targetId=main?'main':track?.id||'overlay';
      const preview=placementPreview({items:M.allItems(draft.value).map(row=>row.item),trackId:targetId,start,end:start+duration,excludeIds:payload.clip?[payload.clip]:[],main,trackLocked:!!track?.locked});
      dropPreview.value={left:(bounds.left-contentBounds.left)+start*zoom.value,top:(bounds.top-contentBounds.top),height:bounds.height,status:preview.status,label:preview.message,index};
      if(event.dataTransfer)event.dataTransfer.dropEffect=preview.status==='blocked'?'none':payload.clip?'move':'copy';
    }
    function clearDropPreview(){dropPreview.value=null;}
    function dropClip(event){
      const payload=dragPayload(event);if(!payload.clip&&!payload.asset)return;
      event.preventDefault();event.stopPropagation();const bounds=event.currentTarget.getBoundingClientRect(),at=Math.max(0,(event.clientX-bounds.left)/zoom.value),index=mainInsertIndex(rows.value,at);
      if(payload.clip){const current=draft.value.clips.findIndex(clip=>clip.id===payload.clip);if(current>=0)edit(d=>M.moveClip(d,payload.clip,index>current?index-1:index));}
      else edit(d=>M.appendClip(d,payload.asset,index));
      clearDropPreview();status.value=payload.clip?'片段已移动':'片段已插入主轨';
    }
    function dropFree(event,track){
      event.preventDefault();event.stopPropagation();if(track.locked){clearDropPreview();fail('此轨道已锁定');return;}
      const bounds=event.currentTarget.getBoundingClientRect(),start=Math.max(0,Math.round((event.clientX-bounds.left)/zoom.value*draft.value.settings.fps)/draft.value.settings.fps),payload=dragPayload(event);
      const targetKind=payload.audio?'audio':payload.asset?'video':'';
      if(targetKind&&!trackAccepts(track,targetKind)){clearDropPreview();fail(targetKind==='audio'?'请把音频放到音频轨道':'请把视频或图片放到画面轨道');return;}
      if(payload.asset)edit(d=>{let next=assets.value.get(payload.asset)?.kind==='image'?M.addImage(d,payload.asset,start):M.appendClip(d,payload.asset);const kind=assets.value.get(payload.asset)?.kind==='image'?'overlay':'clip',item=kind==='clip'?next.clips.at(-1):next.overlays.at(-1);return M.updateItem(next,kind,item.id,{start,trackId:track.id});});
      else if(payload.audio)edit(d=>{let next=M.appendAudioClip(d,payload.audio,start);return M.updateItem(next,'audio',next.audioClips.at(-1).id,{trackId:track.id});});
      clearDropPreview();
    }
    function rulerSeek(event){const bounds=event.currentTarget.getBoundingClientRect();setTime((event.clientX-bounds.left)/zoom.value);}
    function guardImport(job){if(disposed||job.cancelled||!props.active)throw Error('素材导入已取消');}
    async function abortUpload(job){if(job?.uploadId){const uploadId=job.uploadId;job.uploadId='';try{await rpc.invoke('video.uploadAbort',{uploadId});}catch{}}}
    async function cancelImport(){if(!transfer)return;transfer.cancelled=true;await abortUpload(transfer);status.value='正在取消导入…';}
    async function registerPath(path,job){guardImport(job);const metadata=await rpc.invoke('video.probe',{path});guardImport(job);let next=M.addAsset(draft.value,metadata);const normalized=String(metadata.path).replaceAll('\\','/').toLowerCase(),asset=next.assets.find(a=>String(a.path).replaceAll('\\','/').toLowerCase()===normalized);const repeated=draft.value.assets.some(row=>row.id===asset.id);next=M.appendClip(next,asset.id);apply(next);if(repeated)refreshSource(asset.path,asset.id);verifiedSources.set(mediaKey(asset.path),metadata);selection.value={kind:'clip',id:next.clips.at(-1).id};}
    function addImage(assetId){edit(d=>M.addImage(d,assetId,playhead.value));const item=draft.value.overlays.at(-1);if(item)select('overlay',item.id);}
    function addSticker(shape){edit(d=>M.addSticker(d,shape,playhead.value));const item=draft.value.overlays.at(-1);if(item)select('overlay',item.id);}
    async function registerImage(path,job,preset=null){guardImport(job);const metadata={...await rpc.invoke('video.imageProbe',{path}),kind:'image',duration:5,hasAudio:false,...(preset?.name?{name:preset.name}:{})};guardImport(job);let next=M.addAsset(draft.value,metadata);const asset=next.assets.find(a=>a.path.toLowerCase().replaceAll('\\','/')===metadata.path.toLowerCase().replaceAll('\\','/'));next=M.addImage(next,asset.id,playhead.value);if(preset){const item=next.overlays.at(-1),scale=preset.defaults?.scale||.3,position=preset.defaults?.position||'center';next=M.updateItem(next,'overlay',item.id,{transform:{...item.transform,opacity:preset.defaults?.opacity??1,x:position.includes('right')?1-scale:position.includes('left')?0:(1-scale)/2,y:position.startsWith('top')?0:position.startsWith('bottom')?1-scale:(1-scale)/2,width:scale,height:scale}});}apply(next);verifiedSources.set(mediaKey(asset.path),metadata);select('overlay',next.overlays.at(-1).id);}
    async function applyFreeAsset(payload){
      if(busy.value)return;
      error.value='';
      if(payload.transition){
        try{
          const candidates=draft.value.version>=2?draft.value.clips.filter(clip=>!isLocked(clip)&&draft.value.clips.some(next=>next.id!==clip.id&&next.trackId===clip.trackId&&next.start>clip.start)):draft.value.clips.slice(0,-1);
          const outgoing=candidates.find(clip=>clip.id===selection.value.id)||candidates[0];
          if(!outgoing)throw Error('请先在同一视频轨道放入至少两个片段，再应用转场。');
          select('clip',outgoing.id);setTransition(payload.transition.type,payload.transition.duration);
          status.value=`已应用“${payload.item.name}”，可在属性面板调整转场时长。`;
        }catch(reason){fail(reason);}
        return;
      }
      if(payload.effect?.kind!=='image'){fail('此素材请在智能剪辑的特效库中使用。');return;}
      const job={cancelled:false,uploadId:''};transfer=job;importing.value=true;pause();
      try{
        await registerImage(payload.effect.path,job,payload.item);
        status.value=`已将“${payload.item.name}”添加到图片轨道，可拖动、裁剪并设置关键帧。`;
      }catch(reason){if(!job.cancelled&&!disposed)fail(reason);}
      finally{if(transfer===job)transfer=null;if(!disposed)importing.value=false;}
    }
    async function applyDownloadedAsset(item){
      if(busy.value||applyingDownloaded.value)return;
      applyingDownloaded.value=item.id;
      try{
        const payload=await rpc.invoke('video.getFreeAsset',{id:item.id});
        if(!disposed&&props.active)await applyFreeAsset(payload);
      }catch(reason){if(!disposed){fail(reason);await refreshDownloadedAssets();}}
      finally{if(!disposed)applyingDownloaded.value='';}
    }
    async function chooseImages(){if(busy.value)return;const job={cancelled:false,uploadId:''};transfer=job;importing.value=true;error.value='';pause();try{const paths=await rpc.invoke('file.select',{multiple:true,filter:TL_IMAGE_FILTER});guardImport(job);for(const path of paths||[]){if(!TL_IMAGE_EXT.test(path))throw Error('请选择PNG、JPG、WebP等图片');await registerImage(path,job);}status.value=paths?.length?`已导入 ${paths.length} 张图片`:'';}catch(reason){if(!job.cancelled&&!disposed)fail(reason);}finally{if(transfer===job)transfer=null;if(!disposed)importing.value=false;}}
    async function chooseVideos(){if(busy.value)return;const job={cancelled:false,uploadId:''};transfer=job;importing.value=true;error.value='';pause();try{const paths=await rpc.invoke('file.select',{multiple:true,filter:TL_VIDEO_FILTER});guardImport(job);if((paths||[]).length+draft.value.assets.length>100)throw Error('素材库最多100个视频，请分批整理');for(let i=0;i<(paths||[]).length;i++){if(!TL_VIDEO_EXT.test(paths[i]))throw Error('请选择支持的视频文件');status.value=`正在读取 ${i+1}/${paths.length}：${tlName(paths[i])}`;await registerPath(paths[i],job);}status.value=paths?.length?`已导入 ${paths.length} 个视频`:'';}catch(reason){if(!job.cancelled&&!disposed)fail(reason);}finally{if(transfer===job)transfer=null;if(!disposed)importing.value=false;}}
    async function importFiles(files,audio=false){if(busy.value||!files.length)return;const job={cancelled:false,uploadId:''};transfer=job;importing.value=true;error.value='';progress.value=0;pause();try{if(files.length+(audio?draft.value.audioAssets:draft.value.assets).length>(audio?50:100))throw Error(audio?'音频素材库最多50个素材':'素材库最多100个视频');for(const file of files){if(!(audio?TL_AUDIO_EXT.test(file.name):TL_VIDEO_EXT.test(file.name)||TL_IMAGE_EXT.test(file.name)))throw Error(`不支持的文件：${file.name}`);if(!Number.isSafeInteger(file.size)||file.size<=0||file.size>4*1024**3)throw Error('单个素材需大于0且不超过4GB');}for(let i=0;i<files.length;i++){guardImport(job);const file=files[i];status.value=`正在导入 ${i+1}/${files.length}：${file.name}`;let path=file.path;if(!path){const start=await rpc.invoke('video.uploadBegin',{scope:'tools',name:file.name,size:file.size});job.uploadId=start.uploadId;guardImport(job);const chunkSize=Math.min(1024*1024,Number(start.chunkSize)||262144);if(!job.uploadId||!Number.isSafeInteger(chunkSize)||chunkSize<=0)throw Error('素材上传通道不可用');for(let offset=0;offset<file.size;offset+=chunkSize){guardImport(job);const bytes=new Uint8Array(await file.slice(offset,Math.min(file.size,offset+chunkSize)).arrayBuffer());let binary='';for(let k=0;k<bytes.length;k+=8192)binary+=String.fromCharCode(...bytes.subarray(k,k+8192));guardImport(job);const reply=await rpc.invoke('video.uploadChunk',{uploadId:job.uploadId,offset,base64:btoa(binary)});if(reply.received!==offset+bytes.length)throw Error('接收的素材长度不一致，请重试');progress.value=Math.round(100*(i+reply.received/file.size)/files.length);}guardImport(job);const finished=await rpc.invoke('video.uploadFinish',{uploadId:job.uploadId});job.uploadId='';path=finished.path;}await (audio?registerAudio:TL_IMAGE_EXT.test(file.name)?registerImage:registerPath)(path,job);}progress.value=100;status.value=`已导入 ${files.length} 个${audio?'音频':'素材'}`;}catch(reason){await abortUpload(job);if(job.cancelled&&!disposed)status.value='导入已取消';else if(!disposed)fail(reason);}finally{if(transfer===job)transfer=null;if(!disposed){importing.value=false;dragging.value=false;}}}
    async function dropFiles(event){event.preventDefault();dragging.value=false;await importFiles(Array.from(event.dataTransfer?.files||[]));}
    async function registerAudio(path,job){guardImport(job);const metadata=await rpc.invoke('video.audioProbe',{path});guardImport(job);let next=M.addAudioAsset(draft.value,metadata);const normalized=String(metadata.path).replaceAll('\\','/').toLowerCase(),asset=next.audioAssets.find(row=>String(row.path).replaceAll('\\','/').toLowerCase()===normalized);const repeated=draft.value.audioAssets.some(row=>row.id===asset.id);next=M.appendAudioClip(next,asset.id,Math.min(playhead.value,Math.max(0,duration.value-.05)));apply(next);if(repeated)refreshSource(asset.path,asset.id,true);verifiedSources.set(mediaKey(asset.path),metadata);selection.value={kind:'audio',id:next.audioClips.at(-1).id};}
    async function chooseAudio(){if(busy.value)return;const job={cancelled:false,uploadId:''};transfer=job;importing.value=true;error.value='';pause();try{const paths=await rpc.invoke('file.select',{multiple:true,filter:TL_AUDIO_FILTER});guardImport(job);if((paths||[]).length+draft.value.audioAssets.length>M.LIMITS.audioAssets)throw Error('音频素材库最多50个素材');for(let i=0;i<(paths||[]).length;i++){if(!TL_AUDIO_EXT.test(paths[i]))throw Error('请选择支持的音频文件');status.value=`正在读取音频 ${i+1}/${paths.length}：${tlName(paths[i])}`;await registerAudio(paths[i],job);}status.value=paths?.length?`已导入 ${paths.length} 个音频`:'';}catch(reason){if(!job.cancelled&&!disposed)fail(reason);}finally{if(transfer===job)transfer=null;if(!disposed)importing.value=false;}}
    async function dropAudio(event){event.preventDefault();dragging.value=false;await importFiles(Array.from(event.dataTransfer?.files||[]),true);}
    function addAudio(assetId,start=Math.min(playhead.value,Math.max(0,duration.value-.05))){edit(d=>M.appendAudioClip(d,assetId,start));const last=draft.value.audioClips.at(-1);if(last)select('audio',last.id);}
    function dragAudio(event,asset){event.dataTransfer?.setData('application/x-timeline-audio',asset.id);if(event.dataTransfer)event.dataTransfer.effectAllowed='copy';}
    function dropAudioAsset(event){const assetId=event.dataTransfer?.getData('application/x-timeline-audio');if(!assetId)return;event.preventDefault();event.stopPropagation();const bounds=event.currentTarget.getBoundingClientRect(),start=tlClamp(Math.round((event.clientX-bounds.left)/zoom.value*draft.value.settings.fps)/draft.value.settings.fps,0,Math.max(0,duration.value-.05));addAudio(assetId,start);}
    async function extractAudio(){
      const item=selection.value.kind==='clip'?selected.value:null,source=item&&assets.value.get(item.assetId);
      if(!item||!source||!source.hasAudio){fail('请选择带原声的视频片段');return;}
      if(busy.value)return;
      try{
        pause();const metadata=await rpc.invoke('video.audioProbe',{path:source.path});if(disposed||!props.active)return;
        let next=M.addAudioAsset(draft.value,metadata);
        const normalized=String(metadata.path).replaceAll('\\','/').toLowerCase();
        const asset=next.audioAssets.find(row=>String(row.path).replaceAll('\\','/').toLowerCase()===normalized);
        if(!asset)throw Error('原声素材加入失败');
        let track=next.tracks.find(row=>row.type==='audio'&&!row.locked);
        if(!track){next=M.addTrack(next,'audio','原声音轨');track=next.tracks.at(-1);}
        next=M.appendAudioClip(next,asset.id,item.start);
        const audio=next.audioClips.at(-1);
        next=M.updateItem(next,'audio',audio.id,{trackId:track.id,trimStart:item.trimStart,trimEnd:item.trimEnd,speed:item.speed,volume:item.volume,muted:false,reverse:item.reverse,sourceAssetId:item.assetId,keyframes:{volume:item.keyframes?.volume||[]}});
        next=M.updateItem(next,'clip',item.id,{muted:true});
        apply(next);verifiedSources.set(mediaKey(asset.path),metadata);buildWaveform(asset);select('audio',audio.id);status.value='已提取原声到独立音轨，原视频片段已静音';
      }catch(reason){fail(reason);}
    }
    async function chooseMusic(){if(busy.value)return;try{const paths=await rpc.invoke('file.select',{multiple:false,filter:'音频文件|*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg|所有文件|*.*'});if(disposed||!props.active||!paths?.[0])return;edit(d=>M.normalizeDraft({...d,music:{path:paths[0],trackId:'',volume:d.music?.volume??.18,loop:true}}));refreshSource(paths[0],null,true);}catch(reason){fail(reason);}}
    function setMusicTrack(event){const trackId=event.target.value;edit(d=>M.normalizeDraft({...d,music:trackId?{path:'',trackId,volume:d.music?.volume??.18,loop:true}:null}));}
    function musicPatch(key,value){edit(d=>M.normalizeDraft({...d,music:d.music?{...d.music,[key]:value}:null}));}
    function setting(key,value){edit(d=>M.normalizeDraft({...d,settings:{...d.settings,[key]:value}}));}
    function setTransition(type,duration){const item=selected.value;if(selection.value.kind!=='clip'||!item)return;const transition={type:type??item.transitionToNext.type,duration:duration??item.transitionToNext.duration??.4};if(draft.value.version>=2){edit(d=>{let next=M.updateItem(d,'clip',item.id,{transitionToNext:transition});const trackClips=next.clips.filter(c=>c.trackId===item.trackId).sort((a,b)=>a.start-b.start),index=trackClips.findIndex(c=>c.id===item.id),incoming=trackClips[index+1];if(!incoming&&transition.type!=='none')throw Error('请先在同一轨道添加后续视频，再设置转场');if(incoming){const overlap=transition.type==='none'?0:Math.floor(Math.min(transition.duration,M.clipDuration(item)/2,M.clipDuration(incoming)/2)*next.settings.fps)/next.settings.fps;next=M.updateItem(next,'clip',incoming.id,{start:item.start+M.clipDuration(item)-overlap});}return next;});return;}patchSelected('transitionToNext',transition);}
    function applyTransition(type){let item=selection.value.kind==='clip'?selected.value:null;if(!item||draft.value.clips.at(-1)?.id===item.id){const row=M.locate(draft.value,playhead.value);item=row&&draft.value.clips[row.index+1]?row.clip:draft.value.clips[0];}if(!item||draft.value.clips.length<2){fail('请先添加至少两个主轨片段，再选择片段间转场');return;}select('clip',item.id);setTransition(type);}
    function toggleAll(kind,key){const list=kind==='clip'?draft.value.clips:kind==='text'?draft.value.texts:draft.value.overlays,value=!list.every(item=>item[key]);edit(d=>{let next=d;for(const item of list)next=(kind==='clip'?M.updateClip:kind==='text'?M.updateText:M.updateOverlay)(next,item.id,{[key]:value});return next;});}
    function transitionStyle(incoming=false){const join=activeJoin.value;if(!join)return incoming?{display:'none'}:{};const p=join.progress,type=join.type,style={display:'block',opacity:1};if(incoming){if(type==='fade')style.opacity=p;else if(type==='wipeleft')style.clipPath=`inset(0 0 0 ${(1-p)*100}%)`;else if(type==='wiperight')style.clipPath=`inset(0 ${(1-p)*100}% 0 0)`;else if(type==='slideleft')style.transform=`translateX(${(1-p)*100}%)`;else if(type==='slideright')style.transform=`translateX(${-(1-p)*100}%)`;else if(type==='dissolve'){let rects='';for(let i=0;i<240;i++)if(((i*73+19)%241)/241<=p)rects+=`<rect x="${i%20}" y="${Math.floor(i/20)}" width="1" height="1"/>`;style.maskImage=`url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 12" preserveAspectRatio="none"><g fill="white">${rects}</g></svg>`)}")`;style.maskSize='100% 100%';}}else if(type==='slideleft')style.transform=`translateX(${-p*100}%)`;else if(type==='slideright')style.transform=`translateX(${p*100}%)`;return style;}
    async function chooseOutput(){if(busy.value)return;try{const folder=await rpc.invoke('folder.select');if(!disposed&&props.active&&folder)edit(d=>M.normalizeDraft({...d,output:{...d.output,folder}}));}catch(reason){fail(reason);}}
    async function exportVideo(){if(busy.value)return;let payload;try{let snapshot=draft.value;if(snapshot.version>=2&&snapshot.music&&musicPath.value){const metadata=await rpc.invoke('video.audioProbe',{path:musicPath.value});snapshot={...snapshot,music:{...snapshot.music,path:musicPath.value,duration:metadata.duration}};}payload=M.buildExport(snapshot);}catch(reason){fail(reason);return;}pause();error.value='';exporting.value=true;const version=++exportVersion;try{const reply=await store.runJob('video.timelineExport',payload,false);if(disposed||version!==exportVersion)return;if(!reply?.path)throw Error('导出任务未返回成片，请查看任务中心');result.value=reply.path;resultUrl.value=await urlFor(reply.path);if(!disposed)store.toast('时间线成片已导出');}catch(reason){if(!disposed&&version===exportVersion)fail(reason);}finally{if(!disposed&&version===exportVersion)exporting.value=false;}}
    function saveProject(){try{const persisted={...draft.value,assets:draft.value.assets.map(a=>({...a,preview:''}))},url=URL.createObjectURL(new Blob([JSON.stringify(persisted,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='时间线项目.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(reason){fail(reason);}}
    function importProject(){const input=document.createElement('input');input.type='file';input.accept='.json,application/json';input.onchange=async()=>{try{const file=input.files?.[0];if(!file)return;if(file.size>5*1024*1024)throw Error('项目文件过大');const next=M.normalizeDraft(JSON.parse(await file.text()));pause();apply(next);selection.value={kind:'',id:''};multiSelection.value=[];status.value='项目已恢复，请确保本地原始素材仍在原位置';restoreThumbnails();}catch(reason){fail(reason);}};input.click();}
    async function cancelTask(task){try{await rpc.invoke('task.cancel',{taskId:task.taskId});}catch(reason){fail(reason);}}
    function keydown(event){const tag=event.target?.tagName?.toLowerCase();if(['input','textarea','select'].includes(tag)||event.target?.isContentEditable)return;const modifier=event.ctrlKey||event.metaKey,key=event.key.toLowerCase();if(modifier&&key==='z'){event.preventDefault();event.shiftKey?redo():undo();}else if(modifier&&key==='y'){event.preventDefault();redo();}else if(modifier&&['c','x','v','a'].includes(key)){event.preventDefault();if(key==='c'||key==='x')copySelection(key==='x');else if(key==='v')pasteSelection();else multiSelection.value=M.allItems(draft.value).map(({kind,item})=>({kind,id:item.id}));}else if(event.code==='Space'){event.preventDefault();togglePlay();}else if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();removeSelected(event.shiftKey);}else if(key==='m'){event.preventDefault();edit(d=>M.addMarker(d,playhead.value));}else if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();pause();setTime(playhead.value+(event.key==='ArrowLeft'?-1:1)/draft.value.settings.fps);}}
    watch(draft,()=>{save();syncMedia(true);},{deep:true});
    watch(playhead,()=>syncMedia(false));
    watch(selection,drawV2);
    watch(musicPath,path=>{if(path)urlFor(path).catch(fail);syncMedia(true);});
    watch(busy,value=>emit('busy',value),{immediate:true});
    watch(()=>props.active,value=>{if(!value){pause();if(transfer){transfer.cancelled=true;abortUpload(transfer);}}else{syncMedia(true);void refreshDownloadedAssets();}});
    watch(()=>`${library.value}:${resourcesOpen.value}`,()=>{if(resourcesOpen.value&&downloadedCategory[library.value])void refreshDownloadedAssets();});
    watch(()=>JSON.stringify((store.tasks||[]).filter(task=>task.name?.startsWith('下载免费素材：')).map(task=>[task.taskId,task.status])),()=>{void refreshDownloadedAssets();});
    void refreshDownloadedAssets();
    const catalogRequest=++catalogVersion;rpc.invoke('video.getEditorOptions').then(options=>{if(!disposed&&catalogRequest===catalogVersion)catalog.value=Array.isArray(options?.bgmTracks)?options.bgmTracks:[];}).catch(reason=>{if(!disposed)fail(reason);});
    try{
      const pending=localStorage.getItem('aive-timeline-import');
      if(pending){
        const project=JSON.parse(pending),next=M.normalizeDraft(project.draft);
        localStorage.setItem('aive-timeline-previous',JSON.stringify(draft.value));
        pause();apply(next);selection.value={kind:'',id:''};multiSelection.value=[];
        localStorage.removeItem('aive-timeline-import');
        status.value='已打开自动剪辑工程，原始片段、字幕和音乐可继续修改。'+(project.warnings||[]).join(' ');
      }
    }catch(reason){fail(reason);}
    restoreThumbnails();
    for(const asset of draft.value.assets)buildFilmstrip(asset);
    for(const asset of draft.value.audioAssets)buildWaveform(asset);
    watch(()=>draft.value.assets.map(asset=>asset.id).join(','),()=>{for(const asset of draft.value.assets)buildFilmstrip(asset);});
    watch(()=>draft.value.audioAssets.map(asset=>`${asset.id}:${asset.path}`).join(','),()=>{for(const asset of draft.value.audioAssets)buildWaveform(asset);});
    onBeforeUnmount(()=>{globalThis.removeEventListener?.('resize',fitWorkspacePanels);globalThis.removeEventListener?.('aive-ui-skin-changed',syncExternalSkin);save();disposed=true;downloadedRevision++;reverseBuffers.clear();reverseAudioContext?.close().catch(()=>{});catalogVersion++;exportVersion++;pause();if(transfer){transfer.cancelled=true;abortUpload(transfer);}for(const video of thumbnailVideos){video.pause();video.removeAttribute('src');video.load();}thumbnailVideos.clear();stopAll();overlayVideos.clear();audioPlayers.clear();emit('busy',false);});

    const button=(id,label,onClick,disabled=false,extra={})=>tlH('button',{id,type:'button',disabled:disabled||busy.value,onClick,...extra},label);
    const field=(id,label,value,onChange,type='number',extra={})=>tlH('label',{class:'tl-field',for:id},[tlH('span',label),tlH('input',{id,type,value,disabled:busy.value,onChange,...extra})]);
    const selectField=(id,label,value,options,onChange,extra={})=>tlH('label',{class:'tl-field',for:id},[tlH('span',label),tlH('select',{id,value,disabled:busy.value,onChange,...extra},options.map(item=>tlH('option',{value:typeof item==='object'?item.value:item},typeof item==='object'?item.label:item)))]);
    const numeric=(id,label,key,min,max,step=.05)=>field(id,label,selected.value?.[key]??0,event=>numberSelected(key,event),'number',{min,max,step});
    function inspector(){const item=selected.value,kind=selection.value.kind,asset=item&&(kind==='audio'?audioAssets:assets).value.get(item.assetId);return tlH('div',{class:'tl-properties'},[
      item?tlH('div',{class:'tl-selected-name',title:asset?.name},kind==='text'?'文字图层':`${kind==='overlay'?'叠加视频':kind==='audio'?'独立音轨':'主轨片段'} · ${asset?.name||''}`):tlH('div',{class:'tl-help'},'选中时间线片段，调整裁剪、倍速和画面。'),
      item&&kind!=='text'&&asset&&asset.kind!=='image'?tlH('div',{class:'tl-fields'},[numeric('timeline-trim-start','源入点（秒）','trimStart',0,asset.duration),numeric('timeline-trim-end','源出点（秒）','trimEnd',.05,asset.duration),numeric('timeline-speed','播放倍速','speed',.25,4,.25),numeric('timeline-volume',`${kind==='audio'?'音轨音量':'原声音量'}（${gainToDb(item.muted?0:item.volume).toFixed(1)} dB）`,'volume',0,4,.05),kind==='clip'&&asset.hasAudio?button('timeline-extract-audio','提取原声到独立音轨',extractAudio,busy.value||isLocked(item)):null]):null,
      item?tlH('div',{class:'tl-check-row'},[kind!=='text'?tlH('label',{class:'tl-check'},[tlH('input',{id:'timeline-selected-muted',type:'checkbox',checked:item.muted,disabled:busy.value,onChange:event=>patchSelected('muted',event.target.checked)}),'静音']):null,['overlay','text'].includes(kind)?tlH('label',{class:'tl-check'},[tlH('input',{id:'timeline-selected-visible',type:'checkbox',checked:!item.hidden,disabled:busy.value,onChange:event=>patchSelected('hidden',!event.target.checked)}),'显示图层']):null]):null,
      item&&kind==='audio'?[numeric('timeline-audio-start','音轨开始时间（秒）','start',0,86400),tlH('p',{class:'tl-help'},'拖动音频条移动位置，两端裁剪；音轨按主视频时长截断，不延长成片。')]:null,
      item&&kind==='clip'?tlH('div',{class:'tl-transition-controls'},[tlH('h4','片尾转场'),selectField('timeline-transition-type','转场到下一段',item.transitionToNext.type,M.TRANSITIONS,event=>setTransition(event.target.value),{disabled:busy.value||draft.value.clips.at(-1)?.id===item.id}),field('timeline-transition-duration','转场时长（秒）',item.transitionToNext.duration,event=>setTransition(null,Number(event.target.value)),'number',{min:.1,max:2,step:.05,disabled:busy.value||item.transitionToNext.type==='none'||draft.value.clips.at(-1)?.id===item.id}),tlH('p',{class:'tl-transition-info'},draft.value.clips.at(-1)?.id===item.id?'最后一段没有片尾转场。':`实际重叠 ${(rows.value.find(row=>row.id===item.id)?.overlap||0).toFixed(3)} 秒 · 自动限制为两段各一半，按输出帧率对齐。`)]):null,
      item&&kind==='overlay'&&draft.value.version<2?tlH('div',{class:'tl-fields'},[numeric('timeline-overlay-start','开始时间（秒）','start',0,86400),numeric('timeline-overlay-opacity','透明度','opacity',0,1,.05),numeric('timeline-overlay-x','水平位置（0–1）','x',0,1,.01),numeric('timeline-overlay-y','垂直位置（0–1）','y',0,1,.01),numeric('timeline-overlay-width','宽度（0–1）','width',.02,1,.01),numeric('timeline-overlay-height','高度（0–1）','height',.02,1,.01)]):null,
      item&&kind==='overlay'?tlH('p',{class:'tl-help'},'可在预览中拖动画中画。位置和大小按画布比例设置，视频等比放入框内。'):null,
      item&&kind==='text'?[
        tlH('label',{class:'tl-field',for:'timeline-text-content'},[tlH('span','文字内容'),tlH('textarea',{id:'timeline-text-content',value:item.text,maxlength:2000,disabled:busy.value,onChange:event=>patchSelected('text',event.target.value)})]),
        tlH('div',{class:'tl-fields'},[numeric('timeline-text-start','开始时间（秒）','start',0,86400),numeric('timeline-text-end','结束时间（秒）','end',.05,86400),numeric('timeline-text-size','字号','size',12,120,1),field('timeline-text-color','文字颜色',item.color,event=>patchSelected('color',event.target.value),'color')]),
        field('timeline-text-font','字体',item.font,event=>patchSelected('font',event.target.value),'text'),
        selectField('timeline-text-position','文字位置',item.position,[{value:'top',label:'顶部'},{value:'center',label:'居中'},{value:'bottom',label:'底部'}],event=>patchSelected('position',event.target.value))
      ]:null,
      item&&kind==='clip'&&draft.value.version<2?tlH('div',{class:'tl-actions'},[button('timeline-move-left','← 前移',()=>moveSelected(-1),draft.value.clips[0]?.id===item.id),button('timeline-move-right','后移 →',()=>moveSelected(1),draft.value.clips.at(-1)?.id===item.id)]):null,
      item?renderProperties({h:tlH,item:M.allItems(M.enableV2(draft.value)).find(row=>row.item.id===item.id)?.item,kind,draft:M.enableV2(draft.value),time:playhead.value,busy:busy.value||isLocked(item),patch:advancedPatch,commit:edit}):null,
      tlH('h4','配乐'),selectField('timeline-music-track','内置音乐',draft.value.music?.trackId||'',[{value:'',label:draft.value.music?.path?'已选择本地音乐':'不添加配乐'},...catalog.value.map(track=>({value:track.id,label:track.name}))],setMusicTrack),
      button('timeline-music-file',draft.value.music?.path?tlName(draft.value.music.path):'选择本地音乐',chooseMusic),
      draft.value.music?tlH('div',{class:'tl-fields'},[field('timeline-music-volume','配乐音量',draft.value.music.volume,event=>musicPatch('volume',Number(event.target.value)),'number',{min:0,max:1,step:.05}),field('timeline-music-fade-in','淡入（秒）',draft.value.music.fadeIn,event=>musicPatch('fadeIn',Number(event.target.value)),'number',{min:0,max:24*3600,step:.1}),field('timeline-music-fade-out','淡出（秒）',draft.value.music.fadeOut,event=>musicPatch('fadeOut',Number(event.target.value)),'number',{min:0,max:24*3600,step:.1}),tlH('label',{class:'tl-check'},[tlH('input',{id:'timeline-music-loop',type:'checkbox',checked:draft.value.music.loop,disabled:busy.value,onChange:event=>musicPatch('loop',event.target.checked)}),'循环配乐']),tlH('label',{class:'tl-check'},[tlH('input',{id:'timeline-music-ducking',type:'checkbox',checked:draft.value.music.ducking,disabled:busy.value,onChange:event=>musicPatch('ducking',event.target.checked)}),'旁白出现时自动降低配乐'])]):null,
      tlH('audio',{id:'timeline-music-preview',class:'tl-audio',ref:el=>{musicAudio=el;},src:musicPath.value?urls.value[musicPath.value]||undefined:undefined,controls:true,preload:'metadata',style:{display:draft.value.music?'block':'none'},onLoadedmetadata:()=>syncMedia(true),onError:()=>{if(draft.value.music)fail('配乐无法预览，请检查音频文件是否可用');}})
    ]);}
    function outputPanel(){const output=draft.value.output,format=output.format||'mp4',advancedOutput=patch=>edit(d=>{const next=M.enableV2(d);return M.normalizeDraft({...next,output:{...next.output,...patch}});});return tlH('div',{class:'tl-output'},[tlH('h4','画布与导出'),tlH('div',{class:'tl-fields'},[selectField('timeline-ratio','画布比例',draft.value.settings.ratio,['自动','16:9','9:16','1:1','4:3','3:4','21:9'],event=>setting('ratio',event.target.value)),selectField('timeline-resolution','输出清晰度',draft.value.settings.resolution,['原画','720p','1080p','2K','4K'],event=>setting('resolution',event.target.value)),selectField('timeline-fps','帧率',draft.value.settings.fps,[24,25,30,50,60],event=>setting('fps',Number(event.target.value))),field('timeline-background','画布背景',draft.value.settings.background||'#000000',event=>edit(d=>{const next=M.enableV2(d);return M.normalizeDraft({...next,settings:{...next.settings,background:event.target.value}});}),'color'),selectField('timeline-output-format','导出格式',format,[{value:'mp4',label:'MP4 · H.264'},{value:'webm',label:'WebM · VP9'}],event=>advancedOutput({format:event.target.value,filename:output.filename.replace(/\.(mp4|webm)$/i,'')+'.'+event.target.value})),selectField('timeline-output-quality','画质',output.quality||'high',[{value:'high',label:'高质量'},{value:'medium',label:'均衡'},{value:'low',label:'小体积'}],event=>advancedOutput({quality:event.target.value}))]),tlH('label',{class:'tl-check'},[tlH('input',{id:'timeline-include-audio',type:'checkbox',checked:output.audio!==false,onChange:event=>advancedOutput({audio:event.target.checked})}),'包含声音（关闭后导出静音视频）']),tlH('div',{class:'tl-folder'},[tlH('span',{title:output.folder},output.folder||'选择成片保存位置'),button('timeline-output-folder','选择文件夹',chooseOutput)]),field('timeline-output-name',`${format.toUpperCase()} 文件名`,output.filename,event=>edit(d=>M.normalizeDraft({...d,output:{...d.output,filename:event.target.value}})),'text',{maxlength:200}),button('timeline-export',exporting.value?'正在导出…':`导出 ${format.toUpperCase()}`,exportVideo,!M.allItems(draft.value).length,{class:'primary'}),tlH('span',{class:'tl-help'},'导出进度与成片同步保存在任务中心。')]);}
    function downloadedPanel(category){
      const items=installedAssets(category),label={transition:'转场',sticker:'贴纸',effect:'效果'}[category];
      return tlH('section',{class:'tl-downloaded-section','aria-label':`已下载的${label}`},[
        tlH('div',{class:'tl-downloaded-heading'},[
          tlH('strong',`已下载 · ${items.length}`),
          tlH('button',{id:`timeline-downloaded-refresh-${category}`,type:'button',disabled:downloadedLoading.value,onClick:refreshDownloadedAssets},downloadedLoading.value?'同步中…':'刷新'),
          button(`timeline-downloaded-more-${category}`,'下载更多',()=>openLibrary('free')),
        ]),
        downloadedError.value?tlH('p',{class:'tl-downloaded-error',role:'alert'},`素材列表同步失败：${downloadedError.value}`):null,
        items.length?tlH('div',{class:'tl-preset-grid'},items.map(item=>tlH('button',{
          id:`timeline-downloaded-apply-${item.id}`,key:item.id,'data-downloaded-asset-id':item.id,type:'button',class:'tl-preset',
          disabled:busy.value||!!applyingDownloaded.value||(category==='transition'&&draft.value.clips.length<2),
          title:`${item.name} · 已下载，点击应用${category==='transition'?` · ${item.recipe?.duration||.4} 秒`:''}`,
          onClick:()=>applyDownloadedAsset(item),
        },[
          tlH('span',{class:'tl-downloaded-preview'},[item.preview?.endsWith('.mp4')?
            tlH('video',{src:'/assets/'+item.preview,muted:true,loop:true,autoplay:true,playsinline:true,preload:'metadata','aria-label':`${item.name}转场预览`}):
            tlH('img',{src:'/assets/'+item.preview,alt:item.name,loading:'lazy'})]),
          tlH('span',item.name),
          tlH('small',applyingDownloaded.value===item.id?'正在添加…':category==='transition'?`${item.recipe?.duration||.4} 秒 · 点击应用`:'已下载 · 点击添加'),
        ]))):tlH('p',{class:'tl-help'},downloadedLoading.value?'正在读取已下载素材…':`下载的${label}会自动显示在这里，可从“免费素材”下载。`),
      ]);
    }
    function libraryBadge(){
      const category=downloadedCategory[library.value];
      if(category)return `${installedAssets(category).length} 已下载 · ${{transition:M.TRANSITIONS.length,sticker:6,effect:4}[category]} 内置`;
      if(library.value==='images')return `${draft.value.assets.filter(asset=>asset.kind==='image').length} 张图片`;
      return `${library.value==='audio'?draft.value.audioAssets.length:draft.value.assets.length} 个素材`;
    }
    function libraryPanel(){
      const tabs=[['media','素材'],['images','图片'],['stickers','贴纸'],['text','文字'],['audio','音频'],['transitions','转场'],['effects','效果'],['adjustments','调色'],['masks','遮罩'],['tracks','轨道'],['markers','标记'],['free','免费素材']];
      let content;
      if(library.value==='media')content=[tlH('div',{id:'timeline-drop',class:`tl-drop${dragging.value?' dragging':''}`,onDragover:event=>{event.preventDefault();dragging.value=true;},onDragleave:()=>dragging.value=false,onDrop:dropFiles},[tlH('strong','导入视频或图片'),tlH('span','拖入本地素材 · 单个 ≤ 4GB')]),tlH('div',{class:'tl-media-list'},draft.value.assets.map(asset=>tlH('article',{class:'tl-asset',key:asset.id,draggable:!busy.value,onDragstart:event=>dragAsset(event,asset)},[tlH('img',{src:previewOf(asset)||undefined,alt:asset.name,draggable:false}),tlH('div',{class:'tl-asset-info'},[tlH('strong',{title:asset.name},asset.name),tlH('small',`${tlClock(asset.duration)} · ${asset.width}×${asset.height}`),tlH('div',{class:'tl-actions'},[button(`timeline-main-add-${asset.id}`,'＋ 主轨',()=>addMain(asset.id)),button(`timeline-overlay-add-${asset.id}`,'＋ 叠加',()=>addOverlay(asset.id),!draft.value.clips.length)])])]))),!draft.value.assets.length?tlH('p',{class:'tl-empty-library'},'导入第一段视频后，拖动主轨两端裁剪，或点击「＋ 叠加」制作画中画。'):null];
      else if(library.value==='text')content=[tlH('div',{class:'tl-preset-grid'},[{title:'默认文字',text:'添加标题',size:48,position:'bottom'},{title:'大标题',text:'你的故事，从这里开始',size:72,position:'center'},{title:'顶部说明',text:'记录每一个精彩瞬间',size:36,position:'top'},{title:'字幕',text:'输入你的字幕',size:32,position:'bottom'}].map((preset,index)=>tlH('button',{id:`timeline-text-preset-${index}`,class:'tl-preset',disabled:busy.value,onClick:()=>{edit(d=>M.addText(d,{...preset,start:Math.min(playhead.value,Math.max(0,duration.value-.05))}));const last=draft.value.texts.at(-1);if(last)select('text',last.id);}},[tlH('span',{class:'tl-preset-visual',style:{fontSize:index===1?'24px':'17px'}},'Aa'),tlH('span',preset.title)]))),tlH('p',{class:'tl-help'},'添加后直接拖动文字条定位，两端可裁剪；字体、颜色和位置在右侧属性调整。')];
      else if(library.value==='audio')content=[tlH('div',{id:'timeline-audio-drop',class:`tl-drop${dragging.value?' dragging':''}`,onDragover:event=>{event.preventDefault();dragging.value=true;},onDragleave:()=>dragging.value=false,onDrop:dropAudio},[tlH('strong','拖入音乐、旁白或音效'),tlH('span','MP3 · WAV · M4A · AAC · FLAC · OGG · OPUS'),button('timeline-audio-import','＋ 导入音频',chooseAudio)]),tlH('div',{class:'tl-audio-library'},[...draft.value.audioAssets.map(asset=>tlH('article',{class:'tl-audio-item',key:asset.id,draggable:!busy.value,onDragstart:event=>dragAudio(event,asset)},[tlH('strong',{title:asset.name},`♫ ${asset.name}`),tlH('small',tlClock(asset.duration)),button(`timeline-audio-add-${asset.id}`,'＋ 加入音轨',()=>addAudio(asset.id),!draft.value.clips.length)])),tlH('strong','内置背景音乐'),...catalog.value.map(track=>tlH('div',{class:`tl-audio-item${draft.value.music?.trackId===track.id?' active':''}`},[tlH('strong',`♫ ${track.name}`),button(`timeline-audio-${track.id}`,'使用配乐',()=>setMusicTrack({target:{value:track.id}}))])),draft.value.music?button('timeline-remove-music','移除配乐',()=>edit(d=>M.normalizeDraft({...d,music:null}))):null]),tlH('p',{class:'tl-help'},'音频素材可重复添加或拖到音轨；选择音频条调整音量、静音、倍速和裁剪。内置配乐可覆盖成片并循环。')];
      else if(library.value==='transitions')content=[downloadedPanel('transition'),tlH('h4',{class:'tl-builtin-heading'},'内置转场'),tlH('div',{class:'tl-preset-grid'},M.TRANSITIONS.map((preset,index)=>tlH('button',{id:`timeline-transition-preset-${preset.value}`,class:'tl-preset',disabled:busy.value||draft.value.clips.length<2,onClick:()=>applyTransition(preset.value)},[tlH('span',{class:'tl-preset-visual'},['│','◐','░','◀','▶','⇠','⇢'][index]),tlH('span',preset.label)]))),tlH('p',{class:'tl-help'},'先选择主轨片段，再点转场；时间线上交叠处显示转场块。右侧可修改时长，预览与导出使用同一时钟。')];
      else if(library.value==='images')content=[tlH('div',{id:'timeline-image-drop',class:'tl-drop',onDragover:event=>event.preventDefault(),onDrop:dropFiles},[tlH('strong','拖入图片或透明贴纸'),button('timeline-image-import','＋ 导入图片',chooseImages)]),tlH('p',{class:'tl-help'},'PNG · JPG · WebP · GIF首帧 · BMP，支持透明图片。添加后可设置时长、变换、遮罩与动画。'),...draft.value.assets.filter(a=>a.kind==='image').map(asset=>tlH('article',{class:'tl-asset'},[tlH('img',{src:previewOf(asset)||urls.value[asset.path],alt:asset.name}),tlH('div',[tlH('strong',asset.name),button(`timeline-image-add-${asset.id}`,'＋ 添加画面',()=>addImage(asset.id))])]))];
      else if(library.value==='stickers')content=[downloadedPanel('sticker'),tlH('h4',{class:'tl-builtin-heading'},'内置图形'),tlH('div',{class:'tl-preset-grid'},[['circle','●','圆形'],['rounded','▣','圆角卡片'],['diamond','◆','菱形'],['heart','♥','心形'],['star','★','星形'],['rect','■','矩形']].map(([shape,symbol,label])=>tlH('button',{id:`timeline-sticker-${shape}`,class:'tl-preset',disabled:busy.value,onClick:()=>addSticker(shape)},[tlH('span',{class:'tl-sticker-tile'},symbol),tlH('span',label)]))),tlH('p',{class:'tl-help'},'内置图形可改变颜色、位置、透明度和关键帧。也可导入透明 PNG 作为贴纸。')];
      else if(library.value==='effects'||library.value==='adjustments')content=[library.value==='effects'?downloadedPanel('effect'):null,library.value==='effects'?tlH('h4',{class:'tl-builtin-heading'},'内置效果'):null,tlH('div',{class:'tl-preset-grid'},(library.value==='effects'?[['柔焦',{blur:6}],['灰度',{grayscale:true}],['复古棕褐',{sepia:true}],['清除效果',{brightness:0,contrast:1,saturation:1,hue:0,blur:0,grayscale:false,sepia:false}]]:[['明亮',{brightness:.15}],['鲜艳',{saturation:1.4}],['柔和',{contrast:.8,saturation:.8}],['高对比',{contrast:1.4}]]).map(([label,effects],i)=>tlH('button',{id:`timeline-effect-preset-${library.value}-${i}`,class:'tl-preset',disabled:busy.value||!selected.value||selection.value.kind==='audio',onClick:()=>advancedPatch({effects})},[tlH('span',{class:'tl-preset-visual'},library.value==='effects'?'◉':'◐'),tlH('span',label)]))),tlH('p',{class:'tl-help'},'选中画面或文字后应用；右侧可调整每个参数、删除效果。预览与导出使用同一组数值。')];
      else if(library.value==='masks')content=[tlH('div',{class:'tl-preset-grid'},M.MASKS.map((type,i)=>tlH('button',{id:`timeline-mask-${type}`,class:'tl-preset',disabled:busy.value||!selected.value||selection.value.kind==='audio',onClick:()=>advancedPatch({mask:{type}})},[tlH('span',{class:'tl-preset-visual'},['□','▣','●','⬭','▢','◆','♥','★','◧','▰'][i]),tlH('span',['无','矩形','圆形','椭圆','圆角','菱形','心形','星形','半幅','电影黑边'][i])]))),tlH('p',{class:'tl-help'},'支持形状、羽化与反向遮罩。画面变换用于控制遮罩所在图层的位置和大小。')];
      else if(library.value==='tracks'){const next=M.enableV2(draft.value);content=[tlH('div',{class:'tl-actions'},[button('timeline-track-add-video','＋ 画面轨',()=>edit(d=>M.addTrack(d,'video','画面轨'))),button('timeline-track-add-audio','＋ 音频轨',()=>edit(d=>M.addTrack(d,'audio','音频轨'))),button('timeline-track-add-subtitle','＋ 字幕轨',()=>edit(d=>M.addTrack(d,'subtitle','字幕轨')))]),...next.tracks.slice().sort((a,b)=>b.order-a.order).map(track=>tlH('div',{class:'tl-track-item'},[tlH('input',{type:'text',value:track.name,'aria-label':'轨道名称',onChange:e=>edit(d=>M.updateTrack(d,track.id,{name:e.target.value}))}),tlH('div',{class:'tl-actions'},[button(`timeline-track-up-${track.id}`,'↑',()=>edit(d=>M.updateTrack(d,track.id,{order:Math.min(100,track.order+1)}))),button(`timeline-track-down-${track.id}`,'↓',()=>edit(d=>M.updateTrack(d,track.id,{order:Math.max(0,track.order-1)}))),...['hidden','muted','locked'].map((key,i)=>button(`timeline-track-${key}-${track.id}`,track[key]?['显示','有声','解锁'][i]:['隐藏','静音','锁定'][i],()=>edit(d=>M.updateTrack(d,track.id,{[key]:!track[key]})))),button(`timeline-track-delete-${track.id}`,'删除轨道',()=>edit(d=>M.removeTrack(d,track.id)),track.locked)])])),tlH('p',{class:'tl-help'},'轨道按画面、字幕和声音分类；拖入兼容轨道后可继续前后移动、裁剪和排序，锁定轨道会阻止编辑。')];}
      else if(library.value==='markers')content=[button('timeline-marker-add','＋ 播放头标记',()=>edit(d=>M.addMarker(d,playhead.value))),...(draft.value.markers||[]).map(marker=>tlH('div',{class:'tl-marker-row'},[button(`timeline-marker-jump-${marker.id}`,tlClock(marker.time),()=>setTime(marker.time)),tlH('input',{type:'text',value:marker.label,'aria-label':'标记备注',onChange:e=>edit(d=>M.normalizeDraft({...d,markers:d.markers.map(m=>m.id===marker.id?{...m,label:e.target.value}:m)}))}),tlH('input',{type:'color',value:marker.color,'aria-label':'标记颜色',onChange:e=>edit(d=>M.normalizeDraft({...d,markers:d.markers.map(m=>m.id===marker.id?{...m,color:e.target.value}:m)}))}),button(`timeline-marker-remove-${marker.id}`,'×',()=>edit(d=>M.normalizeDraft({...d,markers:d.markers.filter(m=>m.id!==marker.id)})))])),tlH('p',{class:'tl-help'},'按 M 在播放头添加标记；点击时间跳转。标记与项目一起保存。')];
      else if(library.value==='free')content=[tlH(FreeAssetLibrary,{disabled:busy.value,categories:['transition','sticker','effect'],onApply:applyFreeAsset,onChanged:refreshDownloadedAssets})];
      else content=[];
      const icons=['▣','▧','◇','T','♫','⋈','◉','◐','◒','☷','⚑','⇩'];
      return [tlH('style',TL_DOWNLOADED_STYLE),tlH('nav',{class:'tl-library-tabs','aria-label':'编辑资源'},tabs.map(([id,label],index)=>tlH('button',{id:`timeline-library-${id}`,class:library.value===id&&resourcesOpen.value?'active':'','aria-pressed':library.value===id&&resourcesOpen.value,'aria-expanded':library.value===id&&resourcesOpen.value,'aria-controls':'timeline-library-content',title:label,onClick:()=>openLibrary(id,true)},[tlH('span',{class:'tl-library-icon','aria-hidden':'true'},icons[index]),tlH('span',label)]))),tlH('div',{id:'timeline-library-drawer',class:'tl-library-drawer',hidden:!resourcesOpen.value},[tlH('div',{class:'tl-panel-heading'},[tlH('div',[tlH('h3',tabs.find(([id])=>id===library.value)?.[1]||'创作资源'),tlH('span',{id:'timeline-library-badge',class:'tl-badge'},libraryBadge())]),button('timeline-resources-close','‹',toggleResources,false,{'aria-label':'收起创作资源',title:'收起创作资源'})]),tlH('div',{id:'timeline-library-content',key:library.value,class:'tl-library-content'},content)])];
    }
    function renderTimeline(){
      const free=draft.value.version>=2,scale=zoom.value,width=trackWidth.value,tickStep=scale>=65?1:scale>=25?5:scale>=8?10:60,ticks=[];
      for(let at=0;at<=duration.value+tickStep&&ticks.length<250;at+=tickStep)ticks.push(tlH('span',{class:'tl-tick',style:{left:`${at*scale}px`}},tlClock(at).slice(0,-3)));
      const block=(item,kind,start,end,index)=>{
        const asset=(kind==='audio'?audioAssets:assets).value.get(item.assetId);
        const sel=multiSelection.value.some(row=>row.id===item.id)||selection.value.kind===kind&&selection.value.id===item.id;
        const frames=kind==='audio'?[]:filmstrips.value[asset?.id]||[previewOf(asset)].filter(Boolean);
        const count=Math.min(45,Math.max(1,Math.ceil((end-start)*scale/64)));
        const peaks=kind==='audio'?waveforms.value[asset?.path]?.peaks||[]:[];
        const sound=kind==='audio'||asset?.hasAudio;
        const volumeTop=tlClamp((12-gainToDb(item.muted?0:item.volume??1))/72,0,1)*100;
        const handle=edge=>tlH('span',{class:`tl-trim ${edge}`,role:'separator','aria-label':kind==='clip'?`拖动裁剪${edge==='left'?'入':'出'}点`:`拖动${kind==='text'?'文字':kind==='audio'?'音频':'叠加'}${edge==='left'?'入':'出'}点`,onPointerdown:event=>kind==='clip'&&!free?startTrim(event,item,edge):startTimed(event,item,kind,edge),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)});
        return tlH('div',{
          id:`timeline-${kind}-${item.id}`,key:item.id,
          class:`tl-block ${kind==='clip'?'tl-main-clip':kind==='overlay'?'tl-overlay-clip tl-timed-block':kind==='audio'?'tl-audio-clip tl-timed-block':'tl-text-clip tl-timed-block'}${sel?' selected':''}${item.hidden?' tl-hidden':''}`,
          role:'button',tabindex:0,'data-kind':kind,'data-item-id':item.id,
          'aria-label':`${kind==='clip'?'主轨':kind==='overlay'?'叠加':kind==='audio'?'音频':'文字'} ${asset?.name||item.text||'贴纸'} ${tlClock(start)}至${tlClock(end)}`,
          style:{left:`${start*scale}px`,width:`${Math.max(16,(end-start)*scale)}px`},
          draggable:kind==='clip'&&!free&&!busy.value,
          ...(kind==='clip'&&!free?{onDragstart:event=>dragClip(event,item),onDragover:event=>event.preventDefault(),onDrop:event=>dropClip(event,index)}:{onPointerdown:event=>startTimed(event,item,kind),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)}),
          onClick:event=>select(kind,item.id,false,event),onDblclick:()=>setTime(start),
          onKeydown:event=>{if(event.key==='Enter')select(kind,item.id,true);}
        },[
          frames.length?tlH('div',{class:'tl-block-filmstrip'},Array.from({length:count},(_,bar)=>tlH('img',{src:frames[Math.min(frames.length-1,Math.floor(bar/count*frames.length))],alt:'',draggable:false}))):null,
          peaks.length?tlH('div',{class:'tl-waveform','aria-hidden':'true'},peaks.map((peak,bar)=>tlH('i',{key:bar,style:{height:`${Math.max(2,Math.round(peak*94))}%`}}))):null,
          sound?tlH('button',{type:'button',class:'tl-volume-line',style:{top:`${volumeTop}%`},title:`音量 ${gainToDb(item.muted?0:item.volume??1).toFixed(1)} dB`,'aria-label':'拖动调整音量',onPointerdown:event=>startVolume(event,item,kind),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)}):null,
          handle('left'),
          tlH('span',{class:'tl-block-name'},`${item.muted?'♫̸ ':''}${asset?.name||item.text||'图形贴纸'}`),
          handle('right')
        ]);
      };
      const lane=(label,sub,children,extra={},controls=[],laneAttrs={})=>tlH('div',{class:'tl-lane',...laneAttrs},[tlH('div',{class:'tl-lane-label'},[tlH('strong',label),sub?tlH('span',sub):null,controls.length?tlH('div',{class:'tl-track-controls'},controls):null]),tlH('div',{class:'tl-track',onPointerdown:startMarquee,...extra},children)]);
      const main=rows.value.map((item,index)=>block(item,'clip',item.start,item.end,index));
      const freeLanes=free?draft.value.tracks.slice().sort((a,b)=>b.order-a.order).map(track=>lane(`${track.locked?'🔒 ':''}${track.name}`,`${M.allItems(draft.value).filter(i=>i.item.trackId===track.id).length} 个片段`,M.allItems(draft.value).filter(i=>i.item.trackId===track.id).map(({kind,item})=>block(item,kind,item.start,item.start+M.itemDuration(item))),{'data-track-id':track.id,class:'tl-track tl-free-track',onDragover:event=>{event.preventDefault();event.currentTarget.classList.add('tl-drop-target');showDropPreview(event,{track});},onDragleave:event=>{if(!event.currentTarget.contains(event.relatedTarget)){event.currentTarget.classList.remove('tl-drop-target');clearDropPreview();}},onDrop:event=>{event.currentTarget.classList.remove('tl-drop-target');dropFree(event,track)}},[button(`timeline-lane-hidden-${track.id}`,track.hidden?'◉':'○',()=>edit(d=>M.updateTrack(d,track.id,{hidden:!track.hidden})),false,{title:track.hidden?'显示轨道':'隐藏轨道'}),button(`timeline-lane-muted-${track.id}`,track.muted?'🔇':'🔊',()=>edit(d=>M.updateTrack(d,track.id,{muted:!track.muted})),false,{title:track.muted?'恢复声音':'静音轨道'}),button(`timeline-lane-lock-${track.id}`,track.locked?'🔒':'🔓',()=>edit(d=>M.updateTrack(d,track.id,{locked:!track.locked})),false,{title:track.locked?'解锁轨道':'锁定轨道'})],{id:`timeline-track-lane-${track.id}`,'data-track-type':track.type})):[];
      for(const row of rows.value)if(row.overlap>0)main.push(tlH('button',{id:`timeline-join-${row.id}`,class:`tl-join${selection.value.id===row.id?' selected':''}`,style:{left:`${(row.end-row.overlap)*scale}px`,width:`${Math.max(18,row.overlap*scale)}px`},title:`${M.TRANSITIONS.find(t=>t.value===row.transitionToNext.type)?.label} ${row.overlap.toFixed(3)}秒`,onClick:()=>{select('clip',row.id);setTime(row.end-row.overlap/2);openLibrary('transitions');}},'⋈'));
      return tlH('section',{class:'tl-timeline','aria-label':'多轨时间线'},[
      tlH('div',{class:'tl-timeline-toolbar'},[
        tlH('div',{class:'tl-time-actions'},[
          button('timeline-undo','↶',undo,!history.canUndo,{'aria-label':'撤销',title:'撤销 Ctrl+Z'}),
          button('timeline-redo','↷',redo,!history.canRedo,{'aria-label':'重做',title:'重做 Ctrl+Shift+Z'}),
          button('timeline-split','✂ 分割',split,!draft.value.clips.length),
          button('timeline-delete','删除',()=>removeSelected(),!selected.value),
          button('timeline-add-text','＋ 文字',addText),
          button('timeline-snap','⌁ 吸附',()=>snapping.value=!snapping.value,false,{class:snapping.value?'tl-tool-active':'','aria-pressed':snapping.value}),
          tlH('details',{id:'timeline-edit-tools',class:'tl-toolbar-menu'},[
            tlH('summary','更多编辑'),
            tlH('div',{class:'tl-toolbar-menu-content'},[
              tlH('span',{class:'tl-menu-heading'},'片段操作'),
              button('timeline-duplicate','复制片段',duplicate,!selected.value),
              button('timeline-copy','复制到剪贴板',()=>copySelection(),!selected.value),
              button('timeline-cut','剪切',()=>copySelection(true),!selected.value),
              button('timeline-paste','粘贴',pasteSelection,!clipboard.value.length),
              button('timeline-ripple-delete','波纹删除',()=>removeSelected(true),!selected.value),
              tlH('span',{class:'tl-menu-heading'},'轨道与标记'),
              button('timeline-add-track','＋ 画面轨',()=>{edit(d=>M.addTrack(d,'video','画面轨'));openLibrary('tracks');}),
              button('timeline-add-audio-track','＋ 音频轨',()=>{edit(d=>M.addTrack(d,'audio','音频轨'));openLibrary('tracks');}),
              button('timeline-add-subtitle-track','＋ 字幕轨',()=>{edit(d=>M.addTrack(d,'subtitle','字幕轨'));openLibrary('tracks');}),
              button('timeline-add-marker','＋ 标记',()=>edit(d=>M.addMarker(d,playhead.value)))
            ])
          ])
        ]),
        tlH('div',{class:'tl-zoom'},[button('timeline-zoom-out','−',()=>zoom.value=tlClamp(Math.round(zoom.value/1.25),2,160),false,{'aria-label':'缩小时间线'}),tlH('label',{for:'timeline-zoom'},'缩放'),tlH('input',{id:'timeline-zoom',type:'range',min:2,max:160,step:1,value:zoom.value,onInput:event=>zoom.value=Number(event.target.value)}),button('timeline-zoom-in','＋',()=>zoom.value=tlClamp(Math.round(zoom.value*1.25),2,160),false,{'aria-label':'放大时间线'}),button('timeline-fit','适应',fitTimeline),tlH('span',`${zoom.value}px/s`)])
      ]),
      tlH('div',{class:'tl-timeline-scroll',ref:el=>timelineScroll=el},[tlH('div',{class:'tl-track-content',style:{width:`${width+82}px`}},[
        tlH('div',{class:'tl-ruler',style:{width:`${width}px`},onPointerdown:rulerSeek},[...ticks,...(draft.value.markers||[]).map(marker=>tlH('button',{class:'tl-marker-tick',style:{left:`${marker.time*scale}px`,color:marker.color},title:marker.label,onPointerdown:event=>event.stopPropagation(),onClick:()=>setTime(marker.time)},'◆'))]),
        ...freeLanes,
        ...(!free?[
          lane('主视频',`${draft.value.clips.length} 个片段`,draft.value.clips.length?main:tlH('span',{class:'tl-track-empty'},'从素材库添加视频，或将素材拖到这里'),{id:'timeline-main-track','data-track-id':'main',onDragover:event=>{event.preventDefault();showDropPreview(event,{main:true});},onDragleave:event=>{if(!event.currentTarget.contains(event.relatedTarget))clearDropPreview();},onDrop:event=>dropClip(event)},[button('timeline-main-mute',draft.value.clips.length&&draft.value.clips.every(c=>c.muted)?'取消静音':'静音',()=>toggleAll('clip','muted'),!draft.value.clips.length)]),
          ...draft.value.overlays.map((clip,index)=>lane(`叠加 ${index+1}`,'画中画',[block(clip,'overlay',clip.start,clip.start+M.clipDuration(clip))],{},[button(`timeline-overlay-visible-${clip.id}`,clip.hidden?'显示':'隐藏',()=>edit(d=>M.updateOverlay(d,clip.id,{hidden:!clip.hidden})))])),
          lane('文字',`${draft.value.texts.length} 个图层`,draft.value.texts.length?draft.value.texts.map(text=>block(text,'text',text.start,text.end)):tlH('span',{class:'tl-track-empty'},'点击「＋ 文字」添加标题与说明'),{},[button('timeline-text-visible',draft.value.texts.length&&draft.value.texts.every(t=>t.hidden)?'显示':'隐藏',()=>toggleAll('text','hidden'),!draft.value.texts.length)]),
          ...draft.value.audioClips.map((clip,index)=>lane(`音轨 ${index+1}`,audioAssets.value.get(clip.assetId)?.name||'本地音频',[block(clip,'audio',clip.start,clip.start+M.clipDuration(clip))],{},[button(`timeline-audio-muted-${clip.id}`,clip.muted?'取消静音':'静音',()=>edit(d=>M.updateAudioClip(d,clip.id,{muted:!clip.muted})))])),
          lane('添加音轨','音乐 / 旁白',tlH('span',{class:'tl-track-empty'},'从音频素材库拖入，或导入本地音频'),{id:'timeline-audio-track','data-track-id':'audio',onDragover:event=>event.preventDefault(),onDrop:dropAudioAsset})
        ]:[]),
        lane('配乐',draft.value.music?'已启用':'未添加',draft.value.music?tlH('div',{class:'tl-block tl-music-clip',style:{left:0,width:`${Math.max(16,duration.value*scale)}px`}},draft.value.music.path?tlName(draft.value.music.path):catalog.value.find(x=>x.id===draft.value.music.trackId)?.name||'内置配乐'):tlH('span',{class:'tl-track-empty'},'在属性面板选择内置音乐或本地音频')),
        selectedRows.value.length>1&&selectedBounds.value?tlH('div',{class:'tl-group-selection',style:{left:`${82+selectedBounds.value.start*scale}px`,width:`${Math.max(8,selectedBounds.value.duration*scale)}px`}},[tlH('span',{class:'tl-group-label'},`已选 ${selectedRows.value.length} 项`),tlH('button',{type:'button',class:'tl-group-handle left','aria-label':'成组缩放左边界',onPointerdown:event=>startGroupResize(event,'left'),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)}),tlH('button',{type:'button',class:'tl-group-handle right','aria-label':'成组缩放右边界',onPointerdown:event=>startGroupResize(event,'right'),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)})]):null,
        tlH('div',{id:'timeline-playhead',class:'tl-playhead',style:{left:`${82+playhead.value*scale}px`}}),
        snapGuide.value!==null?tlH('div',{class:'tl-snap-guide',style:{left:`${82+snapGuide.value*scale}px`}}):null,
        dropPreview.value?tlH('div',{class:`tl-drop-preview ${dropPreview.value.status}`,style:{left:`${dropPreview.value.left}px`,top:`${dropPreview.value.top}px`,height:`${dropPreview.value.height}px`}},[tlH('span',dropPreview.value.label)]):null,
        marquee.value?tlH('div',{class:'tl-marquee',style:{left:`${marquee.value.left}px`,top:`${marquee.value.top}px`,width:`${marquee.value.width}px`,height:`${marquee.value.height}px`}}):null
      ])]),tlH('div',{class:'tl-timeline-footer'},[tlH('span','主轨拖动排序 · 文字与叠加拖动定位 · 两端裁剪 · 空格播放 · 方向键逐帧'),tlH('span',`总时长 ${tlClock(duration.value)} · ${draft.value.settings.fps} fps`)])
    ]);}
    return()=>tlH('section',{id:'timeline-editor',class:`timeline-editor tl-foldable-workspace${resourcesOpen.value?' tl-resources-open':''}${propertiesOpen.value?' tl-properties-open':''}`,tabindex:-1,onKeydown:keydown},[
      tlH('style',TL_STYLE+TL_WORKBENCH_STYLE+TL_COMPACT_STYLE+TL_TECH_SKIN_STYLE+V2_STYLE+VIEWPORT_STYLE),tlH('header',{class:'tl-header'},[tlH('div',[tlH('h2','时间线剪辑'),tlH('p',{class:'tl-subtitle'},'自由组合画面、文字与声音，把每一段素材剪成故事。')]),tlH('div',{class:'tl-actions'},[button('timeline-resources-toggle',resourcesOpen.value?'收起资源':'创作资源',toggleResources,false,{'aria-expanded':resourcesOpen.value,'aria-controls':'timeline-library-drawer'}),button('timeline-properties-toggle',propertiesOpen.value?'收起属性':'属性与导出',toggleProperties,false,{'aria-expanded':propertiesOpen.value,'aria-controls':'timeline-inspector-content'}),tlH('label',{class:'tl-skin-picker'},[tlH('span','皮肤'),tlH('select',{id:'timeline-skin','aria-label':'界面皮肤',value:skin.value,onChange:event=>setSkin(event.target.value)},SKINS.map(item=>tlH('option',{value:item.value},item.label)))]),tlH('span',{class:'tl-saved'},saveState.value),button('timeline-project-save','保存项目',saveProject),button('timeline-project-open','导入项目',importProject),draft.value.version<2?button('timeline-enable-free','启用自由轨道',()=>edit(M.enableV2)):null,button('timeline-import','＋ 导入视频',chooseVideos,false,{class:'primary'})])]),
      error.value?tlH('div',{class:'tl-error',role:'alert'},error.value):null,
      status.value||importing.value?tlH('div',{class:'tl-status','aria-live':'polite'},[tlH('span',status.value||'正在导入…'),importing.value?tlH('progress',{value:progress.value,max:100}):null,importing.value?tlH('button',{id:'timeline-cancel-import',onClick:cancelImport},'取消导入'):null]):null,
      tlH('div',{class:'tl-workspace'},[
        tlH('aside',{class:'tl-panel tl-media'},libraryPanel()),
        tlH('article',{class:'tl-panel tl-preview'},[tlH('div',{class:'tl-panel-heading'},[tlH('h3','画面预览'),tlH('span',{class:'tl-badge'},`${draft.value.settings.ratio} · ${draft.value.settings.resolution}`)]),tlH('div',{class:'tl-preview-space'},[tlH('div',{id:'timeline-canvas',class:'tl-canvas',style:{aspectRatio:ratio.value,'--tl-aspect':ratioNumber.value}},[
          tlH('video',{id:'timeline-video',class:'tl-main-video',style:draft.value.version>=2?{display:'none'}:transitionStyle(false),ref:el=>{if(el!==mainVideo){mainVideo=el;if(el)syncMedia(true);}},preload:'auto',playsinline:true,onLoadedmetadata:()=>syncMedia(true),onEnded:videoEnded,onError:mediaError,'aria-label':'时间线连续视频预览'}),
          tlH('video',{id:'timeline-video-next',class:'tl-main-video tl-next-video',style:draft.value.version>=2?{display:'none'}:transitionStyle(true),ref:el=>{if(el!==nextVideo){nextVideo=el;if(el)syncMedia(true);}},preload:'auto',playsinline:true,onLoadedmetadata:()=>syncMedia(true),onError:mediaError,'aria-label':'转场下一段视频预览'}),
          draft.value.version>=2?tlH('canvas',{id:'timeline-v2-canvas',class:'tl-v2-canvas',ref:el=>{v2Canvas=el;if(el)drawV2();},onPointerdown:startVisual,onPointermove:gestureMove,onPointerup:gestureEnd,onPointercancel:event=>gestureEnd(event,true),'aria-label':'多轨画面合成预览，可拖动位置与右下角大小'}):null,
          ...(draft.value.version>=2?[...draft.value.clips,...draft.value.overlays].filter(item=>item.type!=='solid').map(item=>{const asset=assets.value.get(item.assetId);return asset?.kind==='image'?tlH('img',{key:item.id,class:'tl-native-hidden',crossorigin:'anonymous',src:urls.value[asset.path],alt:'',ref:el=>{if(el)imagePlayers.set(item.id,el);else imagePlayers.delete(item.id);},onLoad:drawV2}):tlH('video',{key:item.id,class:'tl-native-hidden',crossorigin:'anonymous',ref:el=>{if(el){if(overlayVideos.get(item.id)!==el){overlayVideos.set(item.id,el);syncMedia(true);}}else{stopElement(overlayVideos.get(item.id));overlayVideos.delete(item.id);}},preload:'auto',playsinline:true,onLoadedmetadata:()=>syncMedia(true),onSeeked:drawV2,onLoadeddata:drawV2,onError:mediaError});}):[]),
          !M.allItems(draft.value).some(row=>row.kind!=='audio')?tlH('div',{class:'tl-preview-empty'},[tlH('strong','从第一段画面开始'),tlH('span','导入视频、图片或添加文字，开始自由创作。')]):null,
          ...(draft.value.version>=2?[]:draft.value.overlays.map(clip=>tlH('div',{key:clip.id,class:`tl-overlay-box${selection.value.kind==='overlay'&&selection.value.id===clip.id?' selected':''}`,style:{display:activeOverlays.value.some(x=>x.id===clip.id)?'block':'none',left:`${clip.x*100}%`,top:`${clip.y*100}%`,width:`${clip.width*100}%`,height:`${clip.height*100}%`,opacity:clip.opacity},onPointerdown:event=>startOverlayMove(event,clip),onPointermove:gestureMove,onPointerup:event=>gestureEnd(event),onPointercancel:event=>gestureEnd(event,true)},[tlH('video',{ref:el=>{if(el){if(overlayVideos.get(clip.id)!==el){overlayVideos.set(clip.id,el);syncMedia(true);}}else{stopElement(overlayVideos.get(clip.id));overlayVideos.delete(clip.id);}},preload:'auto',playsinline:true,onLoadedmetadata:()=>syncMedia(true),onError:mediaError,'aria-label':`叠加预览 ${assets.value.get(clip.assetId)?.name||''}`})]))),
          ...(draft.value.version>=2?[]:activeTexts.value.map(text=>tlH('div',{key:text.id,class:'tl-text-preview',style:{fontFamily:text.font,fontSize:`${text.size/canvasWidth.value*100}cqw`,left:`${800/canvasWidth.value}%`,right:`${800/canvasWidth.value}%`,color:text.color,top:text.position==='top'?'4.5%':text.position==='center'?'50%':'auto',bottom:text.position==='bottom'?'4.5%':'auto',transform:text.position==='center'?'translateY(-50%)':undefined}},text.text)))
        ])]),tlH('div',{class:'tl-preview-bottom'},[tlH('div',{class:'tl-transport'},[tlH('div',{class:'tl-actions'},[button('timeline-back-frame','‹',()=>{pause();setTime(playhead.value-1/draft.value.settings.fps);},!duration.value,{'aria-label':'上一帧'}),button('timeline-play',playing.value?'暂停':'播放',togglePlay,!duration.value,{class:'tl-play'}),button('timeline-next-frame','›',()=>{pause();setTime(playhead.value+1/draft.value.settings.fps);},!duration.value,{'aria-label':'下一帧'})]),tlH('span',{class:'tl-clock'},`${tlClock(playhead.value)} / ${tlClock(duration.value)}`)]),tlH('input',{id:'timeline-seek',type:'range',min:0,max:duration.value||0,step:1/draft.value.settings.fps,value:playhead.value,'aria-label':'播放头位置（秒）',disabled:!duration.value,onInput:event=>setTime(event.target.value),onChange:event=>setTime(event.target.value)})])]),
        tlH('aside',{class:'tl-panel tl-inspector'},[button('timeline-inspector-toggle',propertiesOpen.value?'›':'‹ 属性',toggleProperties,false,{class:'tl-inspector-fold','aria-label':propertiesOpen.value?'收起属性与导出':'展开属性与导出','aria-expanded':propertiesOpen.value,'aria-controls':'timeline-inspector-content'}),tlH('div',{id:'timeline-inspector-content',class:'tl-inspector-content',hidden:!propertiesOpen.value},[tlH('div',{class:'tl-panel-heading'},[tlH('h3','属性与导出'),tlH('span',{class:'tl-badge'},selected.value?selection.value.kind==='clip'?'主轨':selection.value.kind==='overlay'?'叠加':selection.value.kind==='audio'?'音频':'文字':'画布')]),inspector(),outputPanel()])])
      ]),...draft.value.audioClips.map(clip=>tlH('audio',{key:clip.id,id:`timeline-audio-preview-${clip.id}`,ref:el=>{if(el){if(audioPlayers.get(clip.id)!==el){audioPlayers.set(clip.id,el);syncMedia(true);}}else{stopElement(audioPlayers.get(clip.id));audioPlayers.delete(clip.id);}},preload:'auto',style:{display:'none'},onLoadedmetadata:()=>syncMedia(true),onError:()=>{pause();fail('此音频无法预览，请尝试 WAV、MP3 或 AAC 文件。导出时会检查原始文件。');},'aria-label':`独立音轨预览 ${audioAssets.value.get(clip.assetId)?.name||''}`})),renderTimeline(),
      tasks.value.length?tlH('div',{class:'tl-result'},tasks.value.map(task=>tlH('div',{class:'tl-export-task'},[tlH('strong',task.name),tlH('span',task.message||task.status),tlH('progress',{max:100,value:task.progress||0}),['queued','running','paused'].includes(task.status)?tlH('button',{onClick:()=>cancelTask(task)},'取消任务'):null]))):null,
      result.value?tlH('div',{id:'timeline-export-result',class:'tl-result'},[tlH('strong','导出完成'),tlH('p',result.value),resultUrl.value?tlH('video',{src:resultUrl.value,controls:true,preload:'metadata','aria-label':'时间线导出成片',ref:el=>{if(resultVideo!==el)stopElement(resultVideo);resultVideo=el;if(el&&!props.active)stopElement(el);}}):null]):null
    ]);
  }
});
export default TimelineEditor;
