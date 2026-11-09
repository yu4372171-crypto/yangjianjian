import {d as defineComponent,j as ref,s as computed,a as h,v as watch,K as onBeforeUnmount,l as rpc,u as useApp} from './index-CVDv6sjN.js';

const size=n=>Number(n)>0?`${(n/1024**3).toFixed(2)} GB`:'本机服务';
const LanguageModelLibrary=defineComponent({
  name:'LanguageModelLibrary',props:{disabled:Boolean},emits:['changed','selected'],
  setup(props,{emit}){
    const store=useApp(),catalog=ref([]),state=ref(null),error=ref(''),note=ref(''),pending=ref(''),hardware=ref(null),confirmDelete=ref('');
    const provider=ref('text-ollama'),baseUrl=ref('http://127.0.0.1:11434'),serviceModel=ref('');let disposed=false,version=0;
    const tasks=computed(()=>(store.tasks||[]).filter(t=>String(t.name).startsWith('下载语言模型：')).slice(0,5));
    async function refresh(){
      const n=++version;error.value='';
      try{const [a,b]=await Promise.all([rpc.invoke('video.languageCatalog',{}),rpc.invoke('video.languageModels',{})]);if(disposed||n!==version)return;catalog.value=a.items||[];state.value=b;
        if(b.settings?.baseUrl){provider.value=b.settings.modelId;baseUrl.value=b.settings.baseUrl;serviceModel.value=b.settings.model;}}
      catch(e){if(!disposed&&n===version)error.value=e.message||String(e);}
    }
    async function action(id,fn){if(props.disabled||pending.value)return;pending.value=id;error.value='';note.value='';try{await fn();if(!disposed){await refresh();emit('changed');}}catch(e){if(!disposed)error.value=e.message||String(e);}finally{if(!disposed)pending.value='';}}
    const installed=id=>state.value?.models?.some(m=>m.id===id&&m.installed);
    async function install(id){await action(id,async()=>{await store.runJob('video.languageInstall',{modelId:id},false);note.value='下载完成，可切换使用。';});}
    async function choose(id){await action(id,async()=>{await rpc.invoke('video.languageSettings',{modelId:id});emit('selected',id);note.value='已切换需求模型。';});}
    async function remove(id){if(confirmDelete.value!==id){confirmDelete.value=id;return;}await action(id,async()=>{await rpc.invoke('video.languageRemove',{modelId:id});confirmDelete.value='';note.value='已删除该语言模型文件，可随时重新下载。';});}
    async function detect(){await action('hardware',async()=>{hardware.value=(await rpc.invoke('video.hardwareProfile',{})).profile;});}
    function fit(item){if(!hardware.value)return '';const ram=Number(hardware.value.ram?.totalBytes)||0,free=Number(hardware.value.ram?.availableBytes)||ram,disk=Number(hardware.value.disk?.freeBytes)||0,bytes=item.variants?.[0]?.estimatedBytes||0;
      if(disk&&disk<bytes*1.2)return '磁盘空间不足';if(ram<bytes*1.8+2*1024**3)return '内存偏低，建议较小模型';if(free<bytes*1.6+1024**3)return '可尝试，建议先关闭其他大型程序';return item.recommended?'本机推荐':'本机可尝试';}
    async function configure(){await action('service',async()=>{await rpc.invoke('video.languageSettings',{modelId:provider.value,baseUrl:baseUrl.value.trim(),model:serviceModel.value.trim()});emit('selected',provider.value);note.value='本机服务配置已保存。';});}
    async function test(id){await action('test',async()=>{const reply=await rpc.invoke('video.languageTest',{modelId:id||state.value?.selectedModel});note.value=reply.message||'模型推理测试完成';});}
    watch(()=>JSON.stringify(tasks.value.map(t=>[t.taskId,t.status])),()=>{if(tasks.value.some(t=>t.status==='done'))void refresh();});
    void refresh();onBeforeUnmount(()=>{disposed=true;version++;});
    return()=>h('details',{id:'language-model-library',class:'language-library'},[
      h('style',null,'.language-library{margin:12px 0;padding:12px;border:1px solid var(--border,#dfe5f0);border-radius:10px;font-size:12px}.language-library summary{cursor:pointer;font-weight:650}.language-library p{line-height:1.7}.language-model-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.language-model-card{padding:12px;border:1px solid var(--border,#dfe5f0);border-radius:9px;display:grid;gap:8px;min-width:0}.language-model-card small{line-height:1.6;color:var(--text-muted,#8190a9)}.language-library .lm-actions{display:flex;gap:6px;flex-wrap:wrap}.language-library label{display:grid;gap:5px;margin:8px 0}.language-library input,.language-library select{width:100%;box-sizing:border-box}.language-library progress{width:100%}.language-library a{color:var(--primary,#5566ff)}@media(max-width:700px){.language-model-grid{grid-template-columns:1fr}}'),
      h('summary',null,'语言模型 · 下载与切换'),
      h('p',null,'选择并下载语言模型，用于理解剪辑需求。画面检查使用独立视觉模型。'),
      h('div',{class:'lm-actions'},[h('button',{id:'language-hardware',disabled:props.disabled||!!pending.value,onClick:detect},'检测电脑配置'),h('button',{disabled:!!pending.value,onClick:refresh},'刷新模型库')]),
      hardware.value?h('p',{id:'language-hardware-result'},`内存 ${(Number(hardware.value.ram?.totalBytes||0)/1024**3).toFixed(1)} GB；以下为资源估算，实际速度取决于电脑负载。`):null,
      h('div',{class:'language-model-grid'},catalog.value.map(item=>h('article',{class:'language-model-card',key:item.id,'data-language-model':item.id},[
        h('strong',null,`${item.name}${state.value?.selectedModel===item.id?' · 当前使用':''}`),h('small',null,item.description),h('small',null,`${item.variants?.[0]?.quantization||''} · 约 ${size(item.variants?.[0]?.estimatedBytes)} · ${item.license||'请查看许可证'}`),
        fit(item)?h('strong',null,fit(item)):null,h('a',{href:item.sourceUrl,target:'_blank',rel:'noopener noreferrer'},'模型说明与许可证'),
        h('div',{class:'lm-actions'},installed(item.id)?[
          h('button',{'data-language-use':item.id,disabled:props.disabled||!!pending.value,onClick:()=>choose(item.id)},state.value?.selectedModel===item.id?'已选用':'使用此模型'),
          h('button',{'data-language-remove':item.id,disabled:props.disabled||!!pending.value,onClick:()=>remove(item.id)},confirmDelete.value===item.id?'确认删除权重':'删除模型'),
        ]:[h('button',{'data-language-download':item.id,disabled:props.disabled||!!pending.value,onClick:()=>install(item.id)},pending.value===item.id?'下载中，可在下方取消…':'下载此模型')]),
      ]))),
      ...tasks.value.map(t=>h('div',{class:'lm-task',key:t.taskId},[h('strong',null,t.name),h('progress',{max:100,value:Number(t.progress)||0}),h('p',null,t.error||t.message||t.status),['queued','running','paused'].includes(t.status)?h('button',{onClick:async()=>{try{await rpc.invoke('task.cancel',{taskId:t.taskId});}catch(e){error.value=e.message||String(e);}}},'取消下载（保留分段）'):null])),
      h('details',null,[h('summary',null,'已有本机模型服务'),h('p',null,'连接已安装的 Ollama 或本机兼容服务。'),
        h('label',null,['服务类型',h('select',{id:'language-provider',value:provider.value,onChange:e=>{provider.value=e.target.value;baseUrl.value=provider.value==='text-ollama'?'http://127.0.0.1:11434':'http://127.0.0.1:8080/v1';}},[h('option',{value:'text-ollama'},'Ollama'),h('option',{value:'text-openai-compatible'},'本机兼容接口')])]),
        h('label',null,['本机接口地址',h('input',{id:'language-base-url',value:baseUrl.value,onInput:e=>baseUrl.value=e.target.value})]),h('label',null,['服务内模型名称',h('input',{id:'language-service-model',value:serviceModel.value,onInput:e=>serviceModel.value=e.target.value,placeholder:'例如 qwen3:4b'})]),h('button',{id:'language-configure',disabled:props.disabled||!!pending.value||!serviceModel.value.trim(),onClick:configure},'保存并选用本机服务'),
      ]),
      h('div',{class:'lm-actions'},[h('button',{id:'language-test',disabled:props.disabled||!!pending.value||!state.value?.ready,onClick:()=>test()},pending.value==='test'?'正在加载并测试模型…':'测试当前模型理解能力')]),
      note.value?h('p',{role:'status'},note.value):null,error.value?h('p',{role:'alert',class:'smart-error'},error.value):null,
    ]);
  },
});
export default LanguageModelLibrary;
