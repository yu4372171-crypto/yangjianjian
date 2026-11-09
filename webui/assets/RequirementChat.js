import {d as defineComponent,j as ref,a as h,v as watch,K as onBeforeUnmount,u as useApp} from './index-CVDv6sjN.js';

const copy=v=>v==null?v:JSON.parse(JSON.stringify(v));
const describe=op=>{
  const names={transform:'画面变换',effects:'调色与效果',mask:'遮罩',keyframes:'动画关键帧',addText:'添加文字',reverse:'倒放',freeze:'末尾定格',audioFade:'声音淡入淡出',trim:'裁剪区间',removeRange:'删除区间',reorder:'素材排序',duplicate:'重复素材',background:'画布背景'};
  const labels={x:'横向位置',y:'纵向位置',width:'宽度',height:'高度',rotation:'旋转',opacity:'透明度',fit:'画面适配',flipX:'水平翻转',flipY:'垂直翻转',brightness:'亮度',contrast:'对比度',saturation:'饱和度',hue:'色相',blur:'模糊',grayscale:'黑白',sepia:'复古',text:'文字',start:'开始秒数',end:'结束秒数',position:'位置',duration:'秒数',fadeIn:'淡入秒数',fadeOut:'淡出秒数',count:'总份数',color:'颜色'};
  const values={contain:'完整显示',cover:'铺满画面',stretch:'拉伸',top:'顶部',center:'居中',bottom:'底部'};
  const details=Object.entries(op.params||{}).map(([key,value])=>key==='order'?`顺序 ${value.map(i=>i+1).join('、')}`:key==='points'?`${value.length} 个关键帧`:key==='crop'?'裁剪画面':typeof value==='object'?null:`${labels[key]||({property:'动画属性',type:'类型',radius:'圆角',feather:'羽化',inverted:'反向'})[key]||key} ${typeof value==='boolean'?(value?'开启':'关闭'):values[value]||value}`).filter(Boolean).join('，');
  return `${names[op.op]||op.op}${Number.isInteger(op.target)?`（素材 ${op.target+1}）`:op.target==='music'?'（配乐）':''}：${details}`;
};
const RequirementChat=defineComponent({
  name:'RequirementChat',props:{text:String,modelId:String,contextKey:String,context:Object,defaults:Object,disabled:Boolean,storageKey:String,compact:Boolean},emits:['adopt','execute','busy'],
  setup(props,{emit,expose}){
    const store=useApp();
    const messages=ref([]),accepted=ref(null),snapshots=ref([]),reply=ref(null),waiting=ref(false),error=ref('');let disposed=false,version=0,lastText='',requestText='';
    function persist(){if(!props.storageKey)return;try{localStorage.setItem(props.storageKey,JSON.stringify({contextKey:props.contextKey,messages:messages.value,accepted:accepted.value,snapshots:snapshots.value,lastText}));}catch{}}
    function reset(){
      version++;requestText='';messages.value=[];snapshots.value=[];reply.value=null;error.value='';lastText='';
      let restored=null;
      try{const saved=JSON.parse(localStorage.getItem(props.storageKey)||'null');if(saved?.contextKey===props.contextKey&&Array.isArray(saved.messages)&&saved.accepted){messages.value=saved.messages.slice(-24);restored=saved.accepted;snapshots.value=Array.isArray(saved.snapshots)?saved.snapshots.slice(-15):[];lastText=typeof saved.lastText==='string'?saved.lastText:'';}}
      catch{}
      accepted.value=restored;emit('adopt',copy(restored));
    }
    async function prepare(){
      if(waiting.value)return null;if(!props.text?.trim()){error.value='请先填写需求。';return null;}
      if(lastText===props.text.trim()&&accepted.value&&reply.value?.status!=='clarify'&&reply.value?.status!=='unsupported')return {status:'ready',plan:copy(accepted.value)};
      const n=++version,key=props.contextKey,text=props.text.trim(),previous=copy(accepted.value),history=copy(messages.value);
      requestText=text;reply.value=null;waiting.value=true;emit('busy',true);error.value='';
      try{
        const response=await store.runJob('video.requirementPrepare',{text,messages:history,previousPlan:previous,context:props.context||{},defaults:props.defaults||{},requirementModelId:props.modelId},false);
        if(disposed||n!==version||key!==props.contextKey||props.text?.trim()!==text)return null;
        messages.value=[...history,{role:'user',content:text},{role:'assistant',content:response.assistant}].slice(-24);reply.value=response;
        if(response.status==='ready'&&response.plan){snapshots.value=[...snapshots.value,{plan:previous,messages:history,lastText}].slice(-15);accepted.value=copy(response.plan);lastText=text;persist();emit('adopt',copy(response.plan));}
        else if(response.plan&&JSON.stringify(response.plan)!==JSON.stringify(previous)){accepted.value=copy(response.plan);emit('adopt',copy(response.plan));}
        persist();return response;
      }catch(e){if(!disposed&&n===version&&props.text?.trim()===text)error.value=e.message||String(e);return null;}
      finally{if(!disposed&&n===version){requestText='';waiting.value=false;emit('busy',false);}}
    }
    function undo(){if(waiting.value||!snapshots.value.length)return;const state=snapshots.value.at(-1);snapshots.value=snapshots.value.slice(0,-1);accepted.value=copy(state.plan);messages.value=copy(state.messages);lastText=state.lastText||'';reply.value=null;emit('adopt',copy(accepted.value));persist();}
    watch(()=>props.text,text=>{if(reply.value&&text?.trim()!==requestText)reply.value=null;});
    watch(()=>props.contextKey,()=>{waiting.value=false;emit('busy',false);reset();},{immediate:true});
    onBeforeUnmount(()=>{disposed=true;version++;emit('busy',false);});expose({prepare,getPlan:()=>copy(accepted.value),getPlanForText:text=>lastText===String(text||'').trim()?copy(accepted.value):null});
    return()=>h('section',{id:'requirement-chat','aria-label':'与剪辑助手对话'},[
      h('style',null,'.requirement-conversation{max-height:260px;overflow:auto;display:grid;gap:8px;margin:10px 0}.requirement-bubble{padding:9px 11px;border-radius:9px;background:var(--bg-hover,#f4f6fb);white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;font-size:12px}.requirement-bubble.user{margin-left:22px;background:#647cff16}.requirement-bubble.assistant{margin-right:15px}.requirement-chat-plan{border:1px solid var(--border,#dfe5f0);padding:10px;border-radius:9px;font-size:12px;line-height:1.8}.requirement-chat-plan ul{padding-left:18px;margin:6px 0}'),
      !props.compact?h('p',{class:'smart-help'},'可以继续说“再亮一点”“字幕改成黄字”，保留此前要求。'):null,
      !props.compact||snapshots.value.length?h('div',{class:'smart-actions'},[
        !props.compact?h('button',{id:'requirement-chat-send',disabled:props.disabled||waiting.value||!props.text?.trim(),onClick:prepare},waiting.value?'正在理解…':'发送需求'):null,
        h('button',{id:'requirement-chat-undo',disabled:props.disabled||waiting.value||!snapshots.value.length,onClick:undo},'撤回修改'),
      ]):null,
      messages.value.length?h('div',{class:'requirement-conversation','aria-live':'polite'},messages.value.map((message,index)=>h('div',{key:index,class:`requirement-bubble ${message.role}`},`${message.role==='user'?'我':'剪辑助手'}：${message.content}`))):null,
      reply.value?.status==='clarify'?h('p',{class:'smart-help',id:'requirement-chat-questions'},(reply.value.questions||[]).join(' ')):null,
      reply.value?.status==='unsupported'?h('p',{class:'smart-error',role:'alert'},(reply.value.unsupported||[]).join('；')):null,
      accepted.value?h('div',{class:'requirement-chat-plan',id:'requirement-chat-plan'},[
        h('strong',null,'剪辑计划'),h('div',null,`${accepted.value.settings.duration?`目标 ${accepted.value.settings.duration} 秒`:'使用全部素材'} · ${accepted.value.settings.ratio} · ${accepted.value.settings.speed} 倍速`),
        h('div',null,[accepted.value.subtitles?'口播同步字幕':'',accepted.value.visualCleanup?'检测并删去异常画面':'',accepted.value.settings.bgm?'添加配乐':''].filter(Boolean).join(' · ')),
        h('div',null,[accepted.value.options?.montageMode==='balanced'?`均衡取材 · 单镜头最长 ${accepted.value.options?.shotDuration||3} 秒`:'顺序完整',({contain:'完整画面留黑边',cover:'裁切铺满画幅',blur:'完整画面配模糊背景'})[accepted.value.options?.fitMode||'contain'],accepted.value.options?.bgmDucking?'口播配乐避让':''].filter(Boolean).join(' · ')),
        accepted.value.operations?.length?h('ul',null,accepted.value.operations.map((op,i)=>h('li',{key:i},describe(op)))):null,
      ]):null,
      error.value?h('p',{class:'smart-error',role:'alert'},error.value):null,
    ]);
  },
});
export default RequirementChat;
