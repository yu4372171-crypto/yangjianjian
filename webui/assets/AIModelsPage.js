import {d as defineComponent,a as h,j as ref,u as useApp} from './index-CVDv6sjN.js';
import VisionModelLibrary from './VisionModelLibrary.js';
import LanguageModelLibrary from './LanguageModelLibrary.js';
import ApiConnectionsPanel,{SchedulerControl} from './ApiConnections.js';

const css=`
.ai-models-page{display:grid;gap:14px;min-width:0}
.ai-models-hero{padding:18px 20px;border:1px solid var(--border,#dfe5f0);border-radius:12px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary,#5566ff) 10%,transparent),transparent 62%)}
.ai-models-hero h2{margin:0 0 8px;font-size:18px}
.ai-models-hero p{margin:6px 0;line-height:1.75;color:var(--text-muted,#8190a9)}
.ai-models-note{padding:11px 13px;border-left:4px solid var(--primary,#5566ff);background:var(--panel-muted,#f6f8fc);border-radius:7px;line-height:1.7;color:var(--text,#25304a)}
.ai-models-tabs{display:flex;gap:8px;flex-wrap:wrap}
.ai-models-tabs button{padding:9px 14px;border:1px solid var(--border,#dfe5f0);border-radius:9px}
.ai-models-tabs button[aria-selected="true"]{border-color:var(--primary,#5566ff);background:color-mix(in srgb,var(--primary,#5566ff) 12%,transparent);font-weight:650}
.ai-models-section{min-width:0}
`;

const AIModelsPage=defineComponent({
  name:'AIModelsPage',
  setup(){
    const selected=ref('vision'),revision=ref(0),testing=ref(false),measurement=ref(null),error=ref('');
    const store=useApp();
    async function benchmark(){
      if(testing.value)return;testing.value=true;error.value='';measurement.value=null;
      try{measurement.value=await store.runJob('video.benchmarkModel',{kind:selected.value},false);}
      catch(e){error.value=e.message||String(e);}
      finally{testing.value=false;}
    }
    return()=>h('div',{class:'ai-models-page'},[
      h('style',null,css),
      h('section',{class:'ai-models-hero'},[
        h('h2',null,'AI 模型中心'),
        h('p',null,'视觉模型检查画面，语言模型理解剪辑需求。可分别使用本地模型、顾客自己的 API，或自动调度。'),
        h('div',{class:'ai-models-note'},'视觉模型只有主模型与视觉投影器都完整下载，并通过大小、GGUF 文件头和 SHA-256 校验后，才会显示为“已校验安装”并可切换使用。'),
      ]),
      h('div',{class:'ai-models-tabs',role:'tablist','aria-label':'模型类型'},[
        h('button',{role:'tab',id:'ai-models-vision-tab','aria-controls':'ai-models-vision',
          'aria-selected':selected.value==='vision'?'true':'false',
          onClick:()=>{selected.value='vision';}}, '视觉模型 · 检查画面'),
        h('button',{role:'tab',id:'ai-models-language-tab','aria-controls':'ai-models-language',
          'aria-selected':selected.value==='language'?'true':'false',
          onClick:()=>{selected.value='language';}}, '语言模型 · 理解需求'),
        h('button',{role:'tab',id:'ai-models-api-tab','aria-controls':'ai-models-api',
          'aria-selected':selected.value==='api'?'true':'false',
          onClick:()=>{selected.value='api';}}, 'API 连接 · 自定义供应商'),
      ]),
      selected.value!=='api'?h('details',{class:'ai-models-note'},[
        h('summary',null,'当前模型实际试跑'),
        h('p',null,'运行一个小样例，检查当前模型能否完成推理并记录耗时。选择 API 时将使用你自己的账户调用一次服务。'),
        h('button',{disabled:testing.value,onClick:benchmark},testing.value?'正在实际推理…':'试跑当前模型'),
        measurement.value?h('p',{role:'status'},`${measurement.value.message} · ${measurement.value.elapsedSeconds} 秒 · ${measurement.value.execution.model}。${measurement.value.note}`):null,
        error.value?h('p',{role:'alert'},error.value):null,
      ]):null,
      h('section',{id:'ai-models-vision',role:'tabpanel','aria-labelledby':'ai-models-vision-tab',
        class:'ai-models-section',hidden:selected.value!=='vision'},[
        h(SchedulerControl,{kind:'vision',revision:revision.value,onChanged:()=>revision.value++}),
        h(VisionModelLibrary),
      ]),
      h('section',{id:'ai-models-language',role:'tabpanel','aria-labelledby':'ai-models-language-tab',
        class:'ai-models-section',hidden:selected.value!=='language'},[
        h(SchedulerControl,{kind:'language',revision:revision.value,onChanged:()=>revision.value++}),
        h(LanguageModelLibrary),
      ]),
      h('section',{id:'ai-models-api',role:'tabpanel','aria-labelledby':'ai-models-api-tab',
        class:'ai-models-section',hidden:selected.value!=='api'},[
        h(ApiConnectionsPanel,{onChanged:()=>revision.value++}),
      ]),
    ]);
  },
});

export default AIModelsPage;
