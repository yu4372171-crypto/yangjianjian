import {d as defineComponent,j as ref,a as h,v as watch,K as onBeforeUnmount,l as rpc} from './index-CVDv6sjN.js';

const RequirementModelSelector=defineComponent({
  name:'RequirementModelSelector',props:{disabled:{type:Boolean,default:false},modelValue:{type:String,default:''},revision:{type:Number,default:0}},emits:['change','openLibrary'],
  setup(props,{emit}){
    const status=ref(null),selected=ref(props.modelValue),loading=ref(false),saving=ref(false),error=ref(''),message=ref(''),expanded=ref(false),query=ref('');let disposed=false,version=0;
    function choose(id){selected.value=id;message.value='';expanded.value=false;query.value='';emit('change',id);}
    function toggle(event){event.preventDefault();if(props.disabled||loading.value||saving.value)return;expanded.value=!expanded.value;query.value='';}
    async function refresh(){
      const current=++version;loading.value=true;error.value='';
      try{
        const reply=await rpc.invoke('video.requirementModels',{});if(disposed||current!==version)return;
        status.value=reply;
        const valid=id=>id==='rules'||reply.models?.some(model=>model.id===id);
        choose(valid(selected.value)?selected.value:valid(reply.selectedModel)?reply.selectedModel:reply.models?.[0]?.id||'rules');
      }catch(e){if(!disposed&&current===version)error.value=e instanceof Error?e.message:String(e);}
      finally{if(!disposed&&current===version)loading.value=false;}
    }
    async function save(){
      if(props.disabled||saving.value||!selected.value)return;
      saving.value=true;error.value='';message.value='';const id=selected.value;
      try{await rpc.invoke('video.requirementSettings',{modelId:id});if(!disposed&&selected.value===id)message.value='已设为默认';}
      catch(e){if(!disposed)error.value=e instanceof Error?e.message:String(e);}
      finally{if(!disposed)saving.value=false;}
    }
    watch(()=>props.modelValue,value=>{if(value!==selected.value)selected.value=value||'';});
    watch(()=>props.revision,()=>{void refresh();});
    watch(()=>props.disabled,value=>{if(value)expanded.value=false;});
    void refresh();onBeforeUnmount(()=>{disposed=true;version++;});
    return()=>{
      const models=[{id:'rules',name:'明确参数',description:'无需模型'},...(status.value?.models||[])],selectedModel=models.find(model=>model.id===selected.value),search=query.value.trim().toLowerCase();
      const visible=models.filter(model=>!search||`${model.name||model.id} ${model.id}`.toLowerCase().includes(search));
      return h('div',{class:'requirement-selector','aria-label':'需求理解模型'},[
        h('style',null,`.requirement-selector{min-width:0;max-width:calc(100% - 58px);font-size:12px}.requirement-model-popup{position:relative}.requirement-model-popup>summary{display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none;width:fit-content;max-width:100%;box-sizing:border-box;border:1px solid var(--border,#dfe5f0);border-radius:24px;padding:7px 12px;background:var(--bg-panel,#fff);color:var(--text,#1b2538);font-size:12px;line-height:1.5}.requirement-model-popup>summary::-webkit-details-marker{display:none}.requirement-model-popup>summary[aria-disabled=true]{opacity:.55;cursor:default}.requirement-model-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.requirement-model-backdrop{position:fixed;inset:0;z-index:79;border:0!important;background:transparent!important;cursor:default!important;border-radius:0!important}.requirement-model-menu{position:absolute;left:0;bottom:calc(100% + 10px);z-index:80;width:300px;max-width:calc(100vw - 70px);box-sizing:border-box;padding:12px;border:1px solid var(--border,#dfe5f0);border-radius:16px;background:var(--bg-panel,#fff);box-shadow:0 12px 40px #17233e24;color:var(--text,#1b2538)}.requirement-model-menu input{width:100%;box-sizing:border-box;margin-bottom:10px;font-size:13px}.requirement-model-options{max-height:min(270px,40vh);overflow-y:auto;overscroll-behavior:contain;display:grid;gap:4px}.requirement-model-options button{display:flex;align-items:center;text-align:left;justify-content:space-between;gap:10px;width:100%;padding:10px 11px;border:0;border-radius:9px;background:transparent;color:inherit;font-size:13px}.requirement-model-options button:hover,.requirement-model-options button[aria-selected=true]{background:var(--bg-hover,#f3f5fc)}.requirement-model-options button span:first-child{min-width:0;overflow-wrap:anywhere}.requirement-model-options small{display:block;margin-top:2px;color:var(--text-muted,#8190a9);font-size:11px}.requirement-model-menu .requirement-menu-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border,#dfe5f0)}.requirement-menu-actions button{font-size:11px;padding:5px 8px}.requirement-model-menu p{font-size:12px;line-height:1.6;margin:8px 0 0}.requirement-model-menu .smart-error{margin-top:8px}`),
        // Retain the select contract for saved-project and existing automation clients.
        h('select',{id:'requirement-model',hidden:true,'aria-label':'需求模型',value:selected.value,disabled:props.disabled||loading.value||saving.value,onChange:e=>choose(e.target.value)},models.map(model=>h('option',{value:model.id},model.name||model.id))),
        h('details',{id:'requirement-model-popup',class:'requirement-model-popup',open:expanded.value,onKeydown:event=>{if(event.key==='Escape'){expanded.value=false;event.stopPropagation();}}},[
          h('summary',{id:'requirement-model-trigger',onClick:toggle,'aria-haspopup':'listbox','aria-expanded':expanded.value,'aria-disabled':props.disabled||loading.value||saving.value,title:'切换需求模型'},[
            h('span',{'aria-hidden':'true'},'✦'),h('span',{class:'requirement-model-label'},loading.value?'正在读取模型…':selectedModel?.name||'选择模型'),h('span',{'aria-hidden':'true'},'⌄'),
          ]),
          h('button',{class:'requirement-model-backdrop',tabindex:-1,'aria-label':'关闭模型菜单',onClick:()=>expanded.value=false}),
          h('div',{class:'requirement-model-menu'},[
            h('input',{id:'requirement-model-search',type:'search',value:query.value,placeholder:'搜索模型…','aria-label':'搜索已安装模型',onInput:e=>query.value=e.target.value}),
            h('div',{id:'requirement-model-options',class:'requirement-model-options',role:'listbox','aria-label':'可用需求模型'},visible.map(model=>h('button',{key:model.id,role:'option','aria-selected':selected.value===model.id,'data-requirement-model':model.id,disabled:props.disabled||saving.value,onClick:()=>choose(model.id)},[
              h('span',null,[model.name||model.id,h('small',null,model.id==='rules'?'无需模型 · 执行明确参数':model.source==='api'?'顾客 API · 已检测':model.source==='auto'?'API 优先 · 失败回退本地':model.installed===false?'本机服务':'本机可用')]),h('span',{'aria-hidden':'true'},selected.value===model.id?'✓':''),
            ]))),
            !visible.length?h('p',{class:'smart-help'},'没有匹配的已安装模型'):null,
            status.value&&!status.value.models?.length?h('p',{class:'smart-help'},'尚未安装模型，可在模型管理中下载。'):null,
            h('div',{class:'requirement-menu-actions'},[
              h('button',{id:'requirement-open-library',disabled:props.disabled,onClick:()=>{expanded.value=false;emit('openLibrary');}},'模型管理'),
              h('button',{id:'requirement-refresh',disabled:props.disabled||loading.value||saving.value,onClick:refresh},loading.value?'刷新中…':'刷新'),
              h('button',{id:'requirement-save-default',disabled:props.disabled||loading.value||saving.value||!selected.value,onClick:save},saving.value?'保存中…':'设为默认'),
            ]),
            message.value?h('p',{role:'status'},message.value):null,
          ]),
        ]),
        error.value?h('p',{class:'smart-error',role:'alert'},error.value):null,
      ]);
    };
  },
});
export default RequirementModelSelector;
