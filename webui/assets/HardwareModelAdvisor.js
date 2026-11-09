import {d as defineComponent,j as ref,a as h,K as onBeforeUnmount,l as rpc} from './index-CVDv6sjN.js';

const capacity=value=>Number.isFinite(value)&&value>=0?`${(value/1024**3).toFixed(1).replace(/\.0$/,'')} GB`:'未知';
const fitLabel={recommended:'推荐',possible:'可以尝试',insufficient:'配置不足',unknown:'信息不足'};
const HardwareModelAdvisor=defineComponent({
  name:'HardwareModelAdvisor',props:{disabled:{type:Boolean,default:false}},emits:['modelRecommended'],
  setup(props,{emit}){
    const result=ref(null),loading=ref(false),error=ref('');let disposed=false,version=0;
    async function detect(){
      if(loading.value||props.disabled)return;
      const current=++version;loading.value=true;error.value='';
      try{const reply=await rpc.invoke('video.hardwareProfile',{});if(!disposed&&current===version)result.value=reply;}
      catch(e){if(!disposed&&current===version)error.value=e instanceof Error?e.message:String(e);}
      finally{if(!disposed&&current===version)loading.value=false;}
    }
    onBeforeUnmount(()=>{disposed=true;version++;});
    return()=>h('section',{class:'hardware-advisor','aria-label':'电脑配置与模型推荐'},[
      h('style',null,'.hardware-advisor{padding:12px;border:1px solid var(--border,#dfe5f0);border-radius:9px;margin:10px 0;background:var(--bg-hover,#f7f9fe)}.hardware-advisor header{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.hardware-advisor h4{margin:0;font-size:13px}.hardware-advisor p{font-size:12px;line-height:1.7;margin:8px 0}.hardware-specs{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:10px 0;font-size:12px}.hardware-specs>div{min-width:0;overflow-wrap:anywhere}.hardware-specs strong{display:block;margin-bottom:3px}.hardware-recommendations{display:grid;gap:8px}.hardware-model{border-top:1px solid var(--border,#dfe5f0);padding-top:9px}.hardware-model small{display:block;line-height:1.65;color:var(--text-muted,#8190a9)}.hardware-model button{margin-top:6px}.hardware-status{font-weight:600;color:var(--primary,#4b5cf7);margin-right:6px}.hardware-error{color:var(--danger,#ef4444)}@media(max-width:600px){.hardware-specs{grid-template-columns:1fr}}'),
      h('header',null,[h('h4',null,'电脑配置与模型推荐'),h('button',{id:'hardware-detect',disabled:props.disabled||loading.value,onClick:detect},loading.value?'正在检测…':result.value?'重新检测电脑配置':'检测电脑配置')]),
      h('p',null,'在本机检测 CPU、内存、显卡和模型磁盘空间，帮助选择合适的模型。点击推荐只查看下载选项。'),
      error.value?h('p',{class:'hardware-error',role:'alert'},error.value):null,
      result.value?h('div',{id:'hardware-result',role:'status'},[
        h('div',{class:'hardware-specs'},[
          h('div',null,[h('strong',null,'处理器'),`${result.value.profile?.cpu?.name||'未知'} · ${result.value.profile?.cpu?.logicalCores||'?'} 线程`]),
          h('div',null,[h('strong',null,'内存'),`总计 ${capacity(result.value.profile?.ram?.totalBytes)} · 可用 ${capacity(result.value.profile?.ram?.availableBytes)}`]),
          h('div',null,[h('strong',null,'显卡 / 专用显存'),...(result.value.profile?.gpus?.length?result.value.profile.gpus:[{name:'未检测到显卡'}]).map(gpu=>h('div',null,`${gpu.name} · ${gpu.dedicatedBytes>0?capacity(gpu.dedicatedBytes):'显存未知'}`))]),
          h('div',null,[h('strong',null,'模型所在磁盘'),`剩余 ${capacity(result.value.profile?.disk?.freeBytes)}`]),
        ]),
        h('p',null,result.value.recommendations?.summary||'配置检测完成'),
        h('div',{class:'hardware-recommendations'},(result.value.recommendations?.vision||[]).map((model,index)=>h('article',{class:'hardware-model',key:model.repoId},[
          h('div',null,[h('span',{class:'hardware-status'},fitLabel[model.fit]||'待评估'),h('strong',null,model.name)]),
          h('small',null,`${model.quantization||'量化版'} · 建议内存 ${capacity(model.estimatedRamBytes)} · 预留磁盘 ${capacity(model.estimatedDiskBytes)}`),
          h('small',null,model.reason||''),...(model.warnings||[]).map(note=>h('small',null,note)),
          h('button',{id:`hardware-model-${index}`,disabled:props.disabled,onClick:()=>{if(!props.disabled)emit('modelRecommended',model);}},model.installed?'已安装 · 查看模型':'查看此模型下载选项'),
        ]))),
        result.value.recommendations?.speech?h('p',null,`${result.value.recommendations.speech.name||'语音字幕模型'}：${fitLabel[result.value.recommendations.speech.fit]||'待评估'} · ${result.value.recommendations.speech.reason||''}`):null,
        ...[...new Set([...(result.value.profile?.detection?.warnings||[]),...(result.value.recommendations?.warnings||[])])].map(note=>h('p',{class:'smart-help'},note)),
        h('p',{class:'smart-help'},result.value.recommendations?.estimateNotice||'建议为资源占用估算，实际速度与效果取决于素材、模型量化和电脑负载。'),
      ]):null,
    ]);
  },
});
export default HardwareModelAdvisor;
