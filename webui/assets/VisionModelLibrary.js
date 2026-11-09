import {d as defineComponent,j as ref,s as computed,a as h,K as onBeforeUnmount,u as useApp,l as rpc} from './index-CVDv6sjN.js';
import HardwareModelAdvisor from './HardwareModelAdvisor.js';

const sizeText=bytes=>!Number.isFinite(Number(bytes))||Number(bytes)<=0?'查看文件大小':Number(bytes)>=1024**3?`${(Number(bytes)/1024**3).toFixed(2)} GB`:`${(Number(bytes)/1024**2).toFixed(1)} MB`;
const categories=[['recommended','推荐 · 可在本机安装'],['all','全部公开视觉模型'],['image-text-to-text','视觉语言 / 多模态对话'],['image-to-text','图片描述 / OCR'],['visual-question-answering','视觉问答'],['image-classification','图片分类'],['zero-shot-image-classification','零样本图片分类'],['object-detection','目标检测'],['image-segmentation','图像分割'],['depth-estimation','深度估计'],['video-classification','视频分类']];
const ACTIVE=['queued','running','paused','cancelling'];
const css=`.vision-library{margin-top:12px;border:1px solid var(--border,#dfe5f0);border-radius:10px;padding:10px 12px;font-size:12px}.vision-library>summary{font-weight:600;cursor:pointer;line-height:1.8}.vision-library p{margin:8px 0;line-height:1.7;color:var(--text-muted,#8190a9)}.vision-library .vl-controls{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.vision-library .vl-controls input{flex:1;min-width:100px}.vision-library .vl-controls select{max-width:220px}.vision-library .vl-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;max-height:430px;overflow:auto}.vision-library .vl-card{border:1px solid var(--border,#dfe5f0);border-radius:8px;padding:10px;min-width:0;display:flex;flex-direction:column;gap:6px}.vision-library .vl-card strong{line-height:1.5;overflow-wrap:anywhere;font-size:12px}.vision-library .vl-card small{color:var(--text-muted,#8190a9);overflow-wrap:anywhere;line-height:1.6}.vision-library .vl-card a{font-size:12px;color:var(--primary,#5566ff)}.vision-library .vl-card .vl-action{margin-top:auto;padding-top:4px}.vision-library .vl-files{margin-top:10px;padding:10px;border:1px solid var(--primary,#5566ff);border-radius:8px;display:grid;gap:8px;overflow-wrap:anywhere}.vision-library .vl-files label{display:grid;gap:5px}.vision-library select{width:100%;min-width:0;box-sizing:border-box}.vision-library .vl-files small{line-height:1.65;color:var(--text-muted,#8190a9)}.vision-library .vl-bottom{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}.vision-library .vl-error{color:var(--danger,#c84a50);line-height:1.6;margin:8px 0;overflow-wrap:anywhere}.vision-library .vl-installed{display:grid;gap:6px;margin:8px 0 12px}.vision-library .vl-installed-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;border:1px solid var(--border,#dfe5f0);border-radius:8px;padding:7px}.vision-library .vl-installed button{text-align:left;overflow-wrap:anywhere}.vision-library .vl-installed-row small{color:var(--text-muted,#8190a9);font-size:11px}.vision-library .vl-installed-row button[aria-pressed="true"]{border-color:var(--primary,#5566ff);font-weight:650}.vision-library .vl-task{padding:8px 0;border-bottom:1px solid var(--border,#dfe5f0);overflow-wrap:anywhere}.vision-library .vl-task progress{width:100%;height:7px}.vision-library .vl-task>div{display:flex;justify-content:space-between;align-items:center;gap:8px}.vision-library .vl-task small{display:block;color:var(--text-muted,#8190a9);margin:5px 0;line-height:1.5}@media(max-width:700px){.vision-library .vl-grid{grid-template-columns:1fr}.vision-library .vl-installed-row{grid-template-columns:1fr}}`;

const VisionModelLibrary=defineComponent({
  name:'VisionModelLibrary',props:{disabled:{type:Boolean,default:false}},emits:['installed','modelSelected'],
  setup(props,{emit}){
    const store=useApp(),search=ref(''),task=ref('recommended'),items=ref([]),installed=ref([]),cursor=ref(null);
    const loading=ref(false),fileLoading=ref(false),downloading=ref(false),error=ref(''),detail=ref(null),modelFile=ref(''),projectorFile=ref(''),status=ref('');
    const activeModel=ref(''),savingModel=ref('');
    const cancelling=ref({});
    const tasks=computed(()=>(store.tasks||[]).filter(row=>row.category==='model'&&String(row.name||'').startsWith('下载视觉模型：')).slice(0,4));
    const selectedFile=computed(()=>detail.value?.files?.find(row=>row.name===modelFile.value));
    const selectedProjector=computed(()=>detail.value?.projectors?.find(row=>row.name===projectorFile.value));
    const pairSize=computed(()=>Number(selectedFile.value?.size||0)+Number(selectedProjector.value?.size||0));
    const installDisabled=computed(()=>props.disabled||downloading.value||!detail.value?.compatible||!selectedFile.value||!selectedProjector.value||!selectedFile.value.projectorFiles.includes(projectorFile.value));
    let disposed=false,loadVersion=0,detailVersion=0,lastSearch='',lastTask='recommended';
    function fail(e){error.value=e instanceof Error?e.message:String(e);}
    async function refreshInstalled(){
      const [reply,visionStatus]=await Promise.all([
        rpc.invoke('video.getInstalledVisionModels',{}),
        rpc.invoke('video.visionStatus',{}),
      ]);
      if(disposed)return;
      installed.value=(reply.items||[]).map(model=>({
        ...model,
        ready:!!visionStatus.local?.ready,
        selected:visionStatus.local?.selectedModel===model.id,
        runtimeMessage:visionStatus.local?.message||'',
      }));
      activeModel.value=visionStatus.local?.selectedModel||'';
    }
    async function load(more=false){
      if(loading.value)return;
      const version=++loadVersion;
      loading.value=true;error.value='';
      const currentSearch=more?lastSearch:search.value.trim(),currentTask=more?lastTask:task.value;
      if(!more){detailVersion++;detail.value=null;status.value='';}
      try{
        const [reply,visionStatus]=await Promise.all([
          rpc.invoke('video.listVisionModels',{search:currentSearch,task:currentTask,...(more&&cursor.value?{cursor:cursor.value}:{})}),
          rpc.invoke('video.visionStatus',{}),
        ]);
        if(disposed||version!==loadVersion)return;
        const combined=more?[...items.value,...(reply.items||[])]:reply.items||[];
        items.value=[...new Map(combined.map(item=>[item.repoId,item])).values()];
        installed.value=(reply.installedModels||[]).map(model=>({...model,ready:!!visionStatus.local?.selectedReady,
          selected:visionStatus.local?.selectedModel===model.id,runtimeMessage:visionStatus.local?.message||''}));
        activeModel.value=visionStatus.local?.selectedModel||'';cursor.value=reply.nextCursor||null;
        lastSearch=currentSearch;lastTask=currentTask;
      }catch(e){if(!disposed&&version===loadVersion)fail(e);}
      finally{if(version===loadVersion)loading.value=false;}
    }
    async function inspect(item){
      if(fileLoading.value||downloading.value)return;
      const version=++detailVersion;fileLoading.value=true;error.value='';status.value='';detail.value=null;
      try{
        const reply=await rpc.invoke('video.getVisionModelFiles',{repoId:item.repoId});
        if(disposed||version!==detailVersion)return;
        detail.value={...reply,name:item.name||reply.name};
        modelFile.value=reply.files?.[0]?.name||'';
        projectorFile.value=reply.files?.[0]?.projectorFiles?.[0]||'';
      }catch(e){if(!disposed&&version===detailVersion)fail(e);}
      finally{fileLoading.value=false;}
    }
    function changeModel(value){
      modelFile.value=value;
      const pairs=detail.value?.files?.find(row=>row.name===value)?.projectorFiles||[];
      if(!pairs.includes(projectorFile.value))projectorFile.value=pairs[0]||'';
    }
    async function install(){
      if(installDisabled.value)return;
      const requested={repoId:detail.value.repoId,modelFile:modelFile.value,projectorFile:projectorFile.value,name:detail.value.name};
      downloading.value=true;error.value='';status.value='正在下载模型；进度与取消按钮显示在下方。关闭此窗口后任务会继续。';
      try{
        const result=await store.runJob('video.downloadVisionModel',requested,false);
        if(disposed)return;
        await refreshInstalled();
        await load(true);
        status.value='下载与校验完成。现在点击“使用此模型”即可切换，软件会自动保存选择。';
        emit('installed',result);store.toast('视觉模型已安装，可立即选择使用');
      }catch(e){if(!disposed){fail(e);status.value='已有分段已保留，重新点击下载可继续。';store.error(e);}}
      finally{if(!disposed)downloading.value=false;}
    }
    async function selectInstalled(model){
      if(props.disabled||downloading.value||savingModel.value)return;
      savingModel.value=model.id;error.value='';status.value='';
      try{
        const reply=await rpc.invoke('video.visionSettings',{modelId:model.id});
        if(disposed)return;
        activeModel.value=reply.modelId||model.id;
        installed.value=installed.value.map(item=>({...item,selected:item.id===activeModel.value,
          ready:!!reply.local?.ready,runtimeMessage:reply.local?.message||item.runtimeMessage}));
        status.value=`当前使用：${model.name}。${reply.local?.ready?'已可用于画面检查。':reply.local?.message||'模型已保存，但运行引擎未就绪。'}`;
        emit('modelSelected',activeModel.value);emit('installed',reply);store.toast('当前视觉模型已切换并保存');
      }catch(e){if(!disposed){fail(e);store.error(e);}}
      finally{if(!disposed)savingModel.value='';}
    }
    async function cancel(row){
      if(cancelling.value[row.taskId]||row.status==='cancelling')return;
      cancelling.value[row.taskId]=true;
      try{await rpc.invoke('task.cancel',{taskId:row.taskId});}
      catch(e){fail(e);}
      finally{delete cancelling.value[row.taskId];}
    }
    function installedFor(item){return installed.value.filter(model=>model.repoId===item.repoId||(item.repoId==='ggml-org/Qwen3-VL-2B-Instruct-GGUF'&&model.id==='qwen3-vl-2b-q8'));}
    void load();
    onBeforeUnmount(()=>{disposed=true;loadVersion++;detailVersion++;});
    return()=>h('details',{class:'vision-library',id:'vision-model-library'},[
      h('style',null,css),h('summary',null,'视觉模型库 · 选择、下载与切换'),
      h(HardwareModelAdvisor,{disabled:props.disabled||downloading.value,onModelRecommended:model=>{void inspect(items.value.find(item=>item.repoId===model.repoId)||model);}}),
      h('p',null,'在线检索 Hugging Face 公开视觉模型，并显示原始许可证。推荐模型可下载到本机；分类、检测等模型及未适配架构可查看模型卡，暂不能直接用于本应用的画面分析。'),
      installed.value.length?h('div',{class:'vl-installed'},[
        h('strong',null,'已校验安装 · 点击即可切换'),
        ...installed.value.map(model=>h('div',{class:'vl-installed-row',key:model.id},[
          h('button',{disabled:props.disabled||downloading.value||!!savingModel.value,onClick:()=>selectInstalled(model),
            'aria-pressed':activeModel.value===model.id?'true':'false'},
          activeModel.value===model.id?`✓ 当前使用：${model.name}`:savingModel.value===model.id?`正在保存：${model.name}`:`使用此模型：${model.name}`),
          h('small',null,model.ready?'运行引擎可用 · 首次分析时加载':'暂不可运行 · '+(model.runtimeMessage||'本地推理引擎未就绪')),
        ])),
      ]):null,
      h('div',{class:'vl-controls'},[
        h('select',{id:'vision-model-task','aria-label':'模型任务分类',value:task.value,disabled:loading.value,onChange:e=>{task.value=e.target.value;void load();}},categories.map(([value,label])=>h('option',{value},label))),
        h('input',{id:'vision-model-search',value:search.value,placeholder:'搜索模型名或作者，例如 Qwen、InternVL','aria-label':'搜索公开视觉模型',onInput:e=>{search.value=e.target.value;},onKeydown:e=>{if(e.key==='Enter')void load();}}),
        h('button',{disabled:loading.value,onClick:()=>load()},loading.value?'正在检索…':'搜索模型'),
        h('button',{disabled:loading.value,onClick:async()=>{try{await refreshInstalled();await load();}catch(e){fail(e);}}},'刷新模型库'),
      ]),
      error.value?h('div',{class:'vl-error',role:'alert'},error.value):null,
      h('div',{class:'vl-grid'},items.value.map(item=>h('article',{class:'vl-card',key:item.repoId},[
        h('strong',null,item.name),h('small',null,item.repoId),
        h('small',null,`许可证：${item.license||'未标注，请查看模型卡'}`),
        item.size?h('small',null,`约 ${sizeText(item.size)} · ${item.memory||'实际内存需求随模型、画面与上下文变化'}`):null,
        item.description?h('small',null,item.description):null,
        item.pipelineTag?h('small',null,`任务：${item.pipelineTag}`):null,
        item.downloads?h('small',null,`Hub 下载量：${Number(item.downloads).toLocaleString()}`):null,
        h('a',{href:item.sourceUrl,target:'_blank',rel:'noopener noreferrer'},'查看原始模型卡与许可证'),
        h('div',{class:'vl-action'},[
          installedFor(item).length?h('small',null,`已校验安装 ${installedFor(item).length} 个版本，可在上方切换使用`):null,
          h('button',{disabled:fileLoading.value||downloading.value||props.disabled,onClick:()=>inspect(item)},item.gated?'查看访问要求':'查看可下载文件'),
        ]),
      ]))),
      !loading.value&&!items.value.length?h('p',null,'没有匹配模型，请调整搜索词或任务分类。'):null,
      fileLoading.value?h('p',null,'正在读取模型文件与兼容信息…'):null,
      detail.value?h('div',{class:'vl-files','aria-label':'模型下载选项'},[
        h('strong',null,detail.value.name),h('small',null,`许可证：${detail.value.license} · 架构：${detail.value.architecture||'未标注'}`),
        !detail.value.compatible?h('div',{class:'vl-error'},detail.value.unsupportedReason):[
          h('label',null,['模型量化文件',h('select',{id:'vision-model-file',value:modelFile.value,disabled:downloading.value,onChange:e=>changeModel(e.target.value)},detail.value.files.map(file=>h('option',{value:file.name},`${file.name} · ${sizeText(file.size)}`)))]),
          h('label',null,['视觉投影器（与模型配对）',h('select',{id:'vision-projector-file',value:projectorFile.value,disabled:downloading.value,onChange:e=>{projectorFile.value=e.target.value;}},(selectedFile.value?.projectorFiles||[]).map(name=>h('option',{value:name},`${name} · ${sizeText(detail.value.projectors.find(file=>file.name===name)?.size)}`)))]),
          h('small',null,`合计 ${sizeText(pairSize.value)}。运行还需额外内存；模型越大，画面分析越慢。下载保存在应用目录，取消后可续传，下载完成会校验 SHA256。`),
          h('button',{class:'primary',disabled:installDisabled.value,onClick:install},downloading.value?'下载进行中…':'下载并安装模型'),
        ],
      ]):null,
      status.value?h('p',{role:'status'},status.value):null,
      ...tasks.value.map(row=>h('div',{class:'vl-task',key:row.taskId},[
        h('div',null,[h('strong',null,row.name),h('span',null,`${Number(row.progress)||0}%`)]),
        h('progress',{max:100,value:Number(row.progress)||0}),h('small',null,row.error||row.message||row.status),
        ACTIVE.includes(row.status)?h('button',{disabled:row.status==='cancelling'||!!cancelling.value[row.taskId],onClick:()=>cancel(row)},row.status==='cancelling'||cancelling.value[row.taskId]?'取消中…':'取消模型下载'):null,
      ])),
      h('div',{class:'vl-bottom'},[cursor.value?h('button',{disabled:loading.value,onClick:()=>load(true)},'加载更多模型'):null,h('small',null,`当前列出 ${items.value.length} 个模型${task.value==='recommended'?' · 推荐列表，其余模型可在线搜索':' · 目录持续更新'}`)]),
    ]);
  },
});
export default VisionModelLibrary;
