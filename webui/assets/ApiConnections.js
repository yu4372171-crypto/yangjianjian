import {d as defineComponent,a as h,j as ref,s as computed,v as watch,K as onBeforeUnmount,l as rpc,u as useApp} from './index-CVDv6sjN.js';

const presets=[
  {id:'custom',name:'自定义供应商',url:'',hint:'填写供应商提供的模型 ID'},
  {id:'openai',name:'OpenAI',url:'https://api.openai.com/v1',hint:'选择账户可用的模型；视觉用途需支持图片'},
  {id:'deepseek',name:'DeepSeek · 语言',url:'https://api.deepseek.com/v1',hint:'填写账户支持的聊天模型 ID'},
  {id:'siliconflow',name:'硅基流动',url:'https://api.siliconflow.cn/v1',hint:'从目录选择语言或视觉模型'},
  {id:'aliyun',name:'阿里云百炼 · 中国内地',url:'https://dashscope.aliyuncs.com/compatible-mode/v1',hint:'海外或其他地域请使用自定义地址'},
  {id:'zhipu',name:'智谱开放平台',url:'https://open.bigmodel.cn/api/paas/v4',hint:'选择账户支持的语言或视觉模型'},
  {id:'volcengine',name:'火山方舟 · 北京',url:'https://ark.cn-beijing.volces.com/api/v3',hint:'可直接填写推理接入点 ID'},
];
const css=`
.api-panel,.api-scheduler{--text:var(--color-text,#25304a);--text-muted:var(--color-text-secondary,#8190a9);--bg-panel:var(--color-bg-panel,#fff);--bg-input:var(--color-card,#fff);--bg-hover:var(--color-primary-soft,#f1f0f5);--border:var(--color-border,#dfe5f0);--primary:var(--color-primary,#5c48ee);--success:var(--color-success,#21a578);--danger:var(--color-error,#e24964)}
.api-panel,.api-scheduler{min-width:0;color:var(--text,#25304a)}.api-panel{display:grid;gap:16px}
.api-panel button,.api-scheduler button{cursor:pointer;border:1px solid var(--border,#dfe5f0);border-radius:9px;padding:8px 13px;background:var(--bg-panel,#fff);color:inherit}
.api-panel button:disabled,.api-scheduler button:disabled{opacity:.5;cursor:default}.api-panel .api-primary{background:var(--primary,#5c48ee);color:#fff;border-color:transparent}
.api-panel-head,.api-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:space-between}
.api-panel h3{margin:0;font-size:16px}.api-panel p,.api-scheduler p{margin:5px 0;line-height:1.7;font-size:12px;color:var(--text-muted,#8190a9)}
.api-card,.api-scheduler{padding:16px;border:1px solid var(--border,#dfe5f0);border-radius:12px;background:var(--bg-panel,#fff)}
.api-card strong{display:block;margin-bottom:7px}.api-address{overflow-wrap:anywhere;font-size:12px}.api-card .api-actions{margin-top:13px;justify-content:flex-start}
.api-editor{border:1px solid var(--border,#dfe5f0);border-radius:18px;background:var(--bg-panel,#fff);box-shadow:0 12px 36px #17233e12}
.api-editor>header{padding:20px 24px;border-bottom:1px solid var(--border,#dfe5f0);display:flex;justify-content:space-between;gap:12px}
.api-form{padding:22px 24px;display:grid;gap:18px}.api-row{display:grid;grid-template-columns:100px minmax(0,1fr);gap:16px;align-items:start}
.api-row>label{padding-top:11px;text-align:right;font-size:14px}.api-field{min-width:0;display:grid;gap:9px}
.api-panel input:not([type=checkbox]),.api-panel select,.api-panel textarea,.api-scheduler select{box-sizing:border-box;min-width:0;max-width:100%;width:100%;padding:10px 12px;border:1px solid var(--border,#dfe5f0);border-radius:10px;background:var(--bg-input,var(--bg-panel,#fff));color:inherit;font:inherit}
.api-inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.api-inline>input{flex:1;min-width:160px!important}.api-inline button{flex-shrink:0}
.api-protocols{display:flex;gap:4px;flex-wrap:wrap;padding:4px;border-radius:10px;background:var(--bg-hover,#f1f0f5)}.api-protocols button{padding:7px 10px;border-color:transparent;background:transparent}
.api-protocols button[aria-selected=true]{background:var(--bg-panel,#fff);box-shadow:0 1px 4px #17233e20}
.api-model-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;max-height:220px;overflow:auto;padding:10px;background:var(--bg-hover,#f6f7fc);border-radius:8px}
.api-model-list label{display:flex;gap:8px;align-items:flex-start;overflow-wrap:anywhere;font-size:12px}.api-model-list input{flex-shrink:0;margin-top:2px}
.api-editor details{border-top:1px solid var(--border,#dfe5f0);padding-top:13px}.api-editor summary{cursor:pointer;font-size:13px;color:var(--text-muted,#8190a9)}.api-editor details>div{display:grid;gap:12px;margin-top:14px}
.api-editor>footer{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end;padding:18px 24px;border-top:1px solid var(--border,#dfe5f0)}
.api-error{color:var(--danger,#e24964)!important;overflow-wrap:anywhere}.api-good{color:var(--success,#21a578)!important}
.api-scheduler{display:grid;gap:9px;margin-bottom:14px}.api-scheduler-controls{display:grid;grid-template-columns:minmax(100px,.6fr) minmax(160px,1fr) auto;gap:9px}
.api-icon{width:32px;height:32px;object-fit:contain;vertical-align:middle;margin-right:8px}.api-test-row{font-size:12px;overflow-wrap:anywhere}
@media(max-width:700px){.api-form{padding:16px}.api-row{grid-template-columns:1fr;gap:6px}.api-row>label{text-align:left;padding-top:0}.api-editor>header,.api-editor>footer{padding:16px}.api-scheduler-controls{grid-template-columns:1fr}.api-inline>input{min-width:100px!important}}
`;
const fresh=kind=>({kind:kind||'language',name:'',preset:'custom',baseUrl:'',apiKey:'',models:'',protocol:'openai-compatible',timeoutSeconds:120,maxOutputTokens:4096,endpoints:{models:'',chat:''},headers:{}});
const normalize=value=>[...new Set(String(value||'').split(/[,，\n]/).map(v=>v.trim()).filter(Boolean))];
const announce=()=>{if(typeof window!=='undefined')window.dispatchEvent(new Event('aive-api-changed'));};

const SchedulerControl=defineComponent({
  name:'SchedulerControl',props:{kind:{type:String,required:true},revision:{type:Number,default:0},disabled:Boolean},emits:['changed'],
  setup(props,{emit}){
    const status=ref(null),items=ref([]),mode=ref('local'),selection=ref(''),busy=ref(false),error=ref('');
    let disposed=false,version=0;
    async function refresh(){
      const current=++version;
      try{
        const [s,c]=await Promise.all([rpc.invoke('video.schedulerStatus',{kind:props.kind}),rpc.invoke('video.apiConnections',{kind:props.kind})]);
        if(disposed||current!==version)return;
        status.value=s;items.value=c.items||[];mode.value=s.mode;
        selection.value=s.connectionId&&s.model?JSON.stringify([s.connectionId,s.model]):'';
      }catch(e){if(!disposed)error.value=e.message||String(e);}
    }
    async function save(){
      busy.value=true;error.value='';
      try{
        const [connectionId,model]=selection.value?JSON.parse(selection.value):['',''];
        const payload={kind:props.kind,mode:mode.value};
        if(mode.value!=='local'){payload.connectionId=connectionId;payload.model=model;}
        status.value=await rpc.invoke('video.schedulerSettings',payload);emit('changed',status.value);announce();
      }catch(e){error.value=e.message||String(e);}finally{busy.value=false;}
    }
    const listener=()=>void refresh();
    if(typeof window!=='undefined')window.addEventListener('aive-api-changed',listener);
    watch(()=>props.revision,refresh);void refresh();
    onBeforeUnmount(()=>{disposed=true;version++;if(typeof window!=='undefined')window.removeEventListener('aive-api-changed',listener);});
    return()=>h('section',{class:'api-scheduler','aria-label':props.kind==='vision'?'视觉调度':'语言调度'},[
      h('style',null,css),
      h('strong',null,props.kind==='vision'?'画面分析 · 执行方式':'需求理解 · 执行方式'),
      h('div',{class:'api-scheduler-controls'},[
        h('select',{'aria-label':'执行方式',disabled:props.disabled||busy.value,value:mode.value,onChange:e=>mode.value=e.target.value},[
          h('option',{value:'local'},'本地模型'),h('option',{value:'api'},'顾客 API'),h('option',{value:'auto'},'自动 · API 优先，失败转本地')]),
        h('select',{'aria-label':'API 模型',disabled:props.disabled||busy.value||mode.value==='local',value:selection.value,onChange:e=>selection.value=e.target.value},[
          h('option',{value:''},'请选择已检测的 API 模型'),...items.value.flatMap(c=>(c.testedModels||[]).map(m=>h('option',{value:JSON.stringify([c.id,m])},`${c.name} / ${m}`)))]),
        h('button',{disabled:props.disabled||busy.value||(mode.value!=='local'&&!selection.value),onClick:save},busy.value?'保存中…':'应用选择')]),
      h('p',{role:'status'},status.value?.message||'正在读取调度…'),
      mode.value==='auto'?h('p',null,'API 失败后只回退到本机已准备好的模型，任务会记录实际执行来源。'):null,
      error.value?h('p',{class:'api-error',role:'alert'},error.value):null,
    ]);
  },
});

const ApiConnectionsPanel=defineComponent({
  name:'ApiConnectionsPanel',props:{kind:{type:String,default:''},disabled:Boolean},emits:['changed'],
  setup(props,{emit}){
    const store=useApp(),items=ref([]),draft=ref(null),directory=ref([]),tests=ref([]),tested=ref(false);
    const busy=ref(''),error=ref(''),message=ref(''),showKey=ref(false),probe=ref(''),icon=ref(''),hasKey=ref(false),search=ref('');
    let disposed=false;
    const models=computed(()=>normalize(draft.value?.models));
    const form=()=>{const value=draft.value;return {...value,models:models.value,model:models.value.includes(value.model)?value.model:models.value[0]||'',endpoints:{...value.endpoints},headers:{...value.headers}};};
    const fail=e=>{error.value=e.message||String(e);};
    function changed(){tested.value=false;tests.value=[];message.value='';}
    function field(name,value){draft.value[name]=value;changed();}
    async function refresh(){
      try{const result=await rpc.invoke('video.apiConnections',props.kind?{kind:props.kind}:{});if(!disposed)items.value=result.items||[];}catch(e){if(!disposed)fail(e);}
    }
    function edit(row=null){
      draft.value=row?{...fresh(row.kind),...Object.fromEntries(Object.entries(row).filter(([k])=>['id','kind','name','preset','baseUrl','model','protocol','timeoutSeconds','maxOutputTokens','endpoints','headers'].includes(k))),apiKey:'',models:row.models.join('\n')} : fresh(props.kind);
      hasKey.value=!!row?.hasKey;icon.value=row?.icon||'';tested.value=false;tests.value=[];directory.value=[];error.value='';message.value='';showKey.value=false;probe.value='';search.value='';
    }
    function close(){draft.value=null;icon.value='';probe.value='';tests.value=[];tested.value=false;showKey.value=false;hasKey.value=false;error.value='';}
    async function action(name,work){
      if(busy.value)return;
      busy.value=name;error.value='';message.value='';
      try{await work();}catch(e){fail(e);}finally{busy.value='';}
    }
    async function detect(){await action('detect',async()=>{
      const result=await rpc.invoke('video.apiDetectProtocol',{...form(),probeModel:probe.value.trim()||models.value[0]||''});
      message.value=result.message;
    });}
    async function fetchModels(){await action('models',async()=>{
      const result=await rpc.invoke('video.apiModels',form());directory.value=result.models||[];
      message.value=`已读取 ${directory.value.length} 个模型，请勾选后检测`;
    });}
    async function check(){await action('test',async()=>{
      const result=await store.runJob('video.apiTestStart',form(),false);if(disposed)return;
      tests.value=result.models||[];tested.value=!!result.success;
      message.value=tested.value?'检测完成，可保存并启用通过的模型':'没有模型通过检测，请检查地址、密钥和模型能力';
    });}
    async function save(){await action('save',async()=>{
      const result=await store.runJob('video.apiConnectionSaveStart',form(),false);if(disposed)return;
      const row=result.connection;
      if(icon.value&&icon.value!==row.icon)await rpc.invoke('video.apiConnectionIcon',{id:row.id,source:icon.value});
      // Save a verified model route as one explicit user action.
      await rpc.invoke('video.schedulerSettings',{kind:row.kind,mode:'api',connectionId:row.id,model:row.model});
      close();await refresh();emit('changed',row);announce();message.value='已保存并启用；密钥由 Windows 加密保存在当前电脑';
    });}
    async function remove(row){await action('delete',async()=>{await rpc.invoke('video.apiConnectionDelete',{id:row.id});await refresh();emit('changed');announce();});}
    function toggleModel(model,checked){const list=models.value.filter(m=>m!==model);if(checked)list.push(model);field('models',list.join('\n'));}
    function choosePreset(value){
      const preset=presets.find(p=>p.id===value);draft.value={...draft.value,preset:value,baseUrl:preset.url,name:preset.id==='custom'?draft.value.name:preset.name,model:'',models:''};
      directory.value=[];changed();
    }
    async function chooseIcon(event){
      const file=event.target.files?.[0];if(!file)return;
      if(file.size>256*1024||!['image/png','image/jpeg','image/webp'].includes(file.type)){error.value='请选择 256KB 以内的 PNG、JPEG 或 WEBP';return;}
      try{icon.value=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(Error('图片读取失败'));r.readAsDataURL(file);});}catch(e){fail(e);}
    }
    async function websiteIcon(){await action('icon',async()=>{const result=await rpc.invoke('video.apiWebsiteIcon',{baseUrl:draft.value.baseUrl});icon.value=result.icon;message.value='已读取网站图标';});}
    const listener=()=>void refresh();
    if(typeof window!=='undefined')window.addEventListener('aive-api-changed',listener);
    watch(()=>props.kind,()=>{close();void refresh();});void refresh();
    onBeforeUnmount(()=>{disposed=true;close();if(typeof window!=='undefined')window.removeEventListener('aive-api-changed',listener);});
    const input=(id,name,placeholder,type='text')=>h('input',{id,type,value:draft.value[name],placeholder,disabled:!!busy.value,autocomplete:'off',
      onInput:e=>field(name,type==='number'?Number(e.target.value):e.target.value)});
    const row=(label,id,children)=>h('div',{class:'api-row'},[h('label',{for:id},label),h('div',{class:'api-field'},children)]);
    return()=>h('div',{class:'api-panel'},[
      h('style',null,css),
      h('div',{class:'api-panel-head'},[h('div',null,[h('h3',null,'顾客 API 连接'),h('p',null,'填写您自己的服务地址和密钥，检测后可直接用于剪辑。')]),
        h('button',{id:'api-add-connection',disabled:props.disabled||!!busy.value,onClick:()=>edit()},'＋ 添加供应商')]),
      !items.value.length&&!draft.value?h('p',null,'尚未添加服务。本地模型仍可正常下载和使用。'):null,
      ...items.value.map(c=>h('article',{key:c.id,class:'api-card'},[
        h('strong',null,[c.icon?.startsWith('data:image/')?h('img',{class:'api-icon',src:c.icon,alt:''}):null,c.name,` · ${c.kind==='vision'?'视觉':'语言'}`]),
        h('div',{class:'api-address'},c.baseUrl),h('p',null,`已通过：${(c.testedModels||[]).join('、')||'尚未检测'} · ${c.hasKey?'密钥已配置':'本机免密服务'}`),
        h('div',{class:'api-actions'},[h('button',{'data-api-edit':c.id,disabled:!!busy.value,onClick:()=>edit(c)},'编辑与检测'),
          h('button',{'data-api-delete':c.id,disabled:!!busy.value,onClick:()=>remove(c)},'删除')])])),
      draft.value?h('section',{id:'api-provider-editor',class:'api-editor','aria-label':'自定义供应商'},[
        h('header',null,[h('h3',null,'◇ 自定义供应商'),h('button',{disabled:!!busy.value,'aria-label':'关闭供应商编辑',onClick:close},'×')]),
        h('div',{class:'api-form'},[
          row('服务用途','api-kind',[h('select',{id:'api-kind',value:draft.value.kind,disabled:!!busy.value||!!draft.value.id,onChange:e=>field('kind',e.target.value)},[
            h('option',{value:'language'},'语言模型 · 理解剪辑需求'),h('option',{value:'vision'},'视觉模型 · 分析画面')])]),
          row('服务商预设','api-preset',[h('select',{id:'api-preset',value:draft.value.preset,disabled:!!busy.value,onChange:e=>choosePreset(e.target.value)},presets.map(p=>h('option',{value:p.id},p.name)))]),
          row('名称','api-name',[input('api-name','name','例如 我的 AI 服务')]),
          row('Base URL','api-base-url',[
            h('div',{class:'api-protocols',role:'tablist','aria-label':'API 协议'},[
              h('button',{role:'tab','aria-selected':true,type:'button'},'OpenAI 兼容'),
              ...['OpenAI Responses','Anthropic','Gemini','System One'].map(p=>h('button',{role:'tab','aria-selected':false,disabled:true,title:'此版本尚未适配，请使用供应商的 OpenAI 兼容地址'},p))]),
            input('api-base-url','baseUrl','https://…/v1'),
            h('div',{class:'api-inline'},[h('button',{id:'api-protocol-detect',disabled:!!busy.value||!draft.value.baseUrl,onClick:detect},busy.value==='detect'?'检测中…':'检测协议'),
              h('input',{id:'api-probe-model',value:probe.value,placeholder:'试用的模型 · 可留空',disabled:!!busy.value,onInput:e=>probe.value=e.target.value})]),
            h('p',null,'使用供应商提供的完整兼容地址，保留 /v1、/v4 或其他必要路径。')]),
          row('API 密钥','api-key',[h('div',{class:'api-inline'},[input('api-key','apiKey',hasKey.value?'已配置 · 留空保留原密钥':'粘贴您自己的 API 密钥',showKey.value?'text':'password'),
            h('button',{id:'api-show-key',disabled:!!busy.value,onClick:()=>showKey.value=!showKey.value},showKey.value?'隐藏':'显示')]),
            h('p',null,'密钥只用于所填服务，使用 Windows 当前账户加密保存；保存后不会回显。')]),
          row('图标','api-icon-file',[h('div',{class:'api-inline'},[icon.value.startsWith('data:image/')?h('img',{class:'api-icon',src:icon.value,alt:'供应商图标'}):h('span',null,'◇'),
            h('label',null,['选择图片…',h('input',{id:'api-icon-file',type:'file',accept:'image/png,image/jpeg,image/webp',disabled:!!busy.value,onChange:chooseIcon})]),
            h('button',{disabled:!!busy.value||!draft.value.baseUrl,onClick:websiteIcon},'从网站获取'),
            h('button',{disabled:!!busy.value,onClick:()=>icon.value='builtin:'+draft.value.kind},'内置图标')])]),
          row('模型','api-models',[
            h('div',{class:'api-inline'},[h('textarea',{id:'api-models',rows:2,value:draft.value.models,placeholder:'模型 ID，可用逗号或换行分隔',disabled:!!busy.value,onInput:e=>field('models',e.target.value)}),
              h('button',{id:'api-fetch-models',disabled:!!busy.value||!draft.value.baseUrl,onClick:fetchModels},busy.value==='models'?'获取中…':'获取模型')]),
            h('p',null,presets.find(p=>p.id===draft.value.preset)?.hint||'可直接填写模型 ID；不支持目录的服务同样可以检测。'),
            directory.value.length?h('input',{type:'search',value:search.value,placeholder:'筛选模型',onInput:e=>search.value=e.target.value}):null,
            directory.value.length?h('div',{class:'api-model-list'},directory.value.filter(m=>m.toLowerCase().includes(search.value.toLowerCase())).map(m=>h('label',null,[
              h('input',{type:'checkbox','data-api-model':m,checked:models.value.includes(m),disabled:!!busy.value,onChange:e=>toggleModel(m,e.target.checked)}),m]))):null,
            h('div',{class:'api-inline'},[h('button',{id:'api-test-models',disabled:!!busy.value||!models.value.length,onClick:check},busy.value==='test'?'正在逐项检测…':'逐项检测已选模型'),
              h('p',null,'视觉检测会实际识别测试图片。检测及保存复验会使用供应商额度；长任务可在任务中心取消。')]),
            ...tests.value.map(t=>h('div',{class:['api-test-row',t.success?'api-good':'api-error']},`${t.success?'✓':'×'} ${t.model}：${t.message}`))]),
          h('details',{id:'api-advanced'},[h('summary',null,'高级'),h('div',null,[
            row('超时（秒）','api-timeout',[input('api-timeout','timeoutSeconds','5–300','number')]),
            row('输出上限','api-tokens',[input('api-tokens','maxOutputTokens','128–16384','number')]),
            h('p',null,'公网连接跟随系统代理，本机连接直连。额外请求头仅支持 OpenAI-Organization 与 OpenAI-Project。'),
            ...['OpenAI-Organization','OpenAI-Project'].map(key=>row(key,'api-'+key,[h('input',{id:'api-'+key,value:draft.value.headers[key]||'',disabled:!!busy.value,onInput:e=>{draft.value.headers={...draft.value.headers,[key]:e.target.value};changed();}})]))])]),
          h('details',{id:'api-endpoints'},[h('summary',null,'更多端点'),h('div',null,['models','chat'].map(key=>row(key==='models'?'模型目录':'聊天推理','api-endpoint-'+key,[
            h('input',{id:'api-endpoint-'+key,value:draft.value.endpoints[key]||'',placeholder:'留空使用默认端点；填写同源绝对地址',disabled:!!busy.value,onInput:e=>{draft.value.endpoints={...draft.value.endpoints,[key]:e.target.value};changed();}})])))]),
        ]),
        h('footer',null,[h('button',{disabled:!!busy.value,onClick:close},'取消'),h('button',{id:'api-save-connection',class:'api-primary',disabled:!!busy.value||!tested.value,onClick:save},busy.value==='save'?'复验并保存中…':'保存并启用')]),
      ]):null,
      busy.value?h('p',{role:'status'},'正在处理，请稍候…'):null,
      error.value?h('p',{class:'api-error',role:'alert'},error.value):null,
      message.value?h('p',{role:'status'},message.value):null,
    ]);
  },
});
export {SchedulerControl};
export default ApiConnectionsPanel;
