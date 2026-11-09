import { d as defineComponent, j as ref, s as computed, a as h, v as watch, K as onBeforeUnmount, u as useApp, l as rpc } from './index-CVDv6sjN.js';

const GROUPS=[['all','全部'],['transition','转场'],['sticker','贴纸'],['effect','透明特效'],['template','调色模板']];
const ACTIVE=['queued','running','paused','cancelling'];
const message=e=>e instanceof Error?e.message:String(e);
const bytes=n=>n<1024*1024?`${Math.max(1,Math.round(n/1024))} KB`:`${(n/1024/1024).toFixed(1)} MB`;
const css=`
.free-assets{font-size:12px;color:var(--text,var(--tl-text,#dbe4f4));min-width:0}
.free-assets-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0 14px;flex-wrap:wrap}
.free-assets-head p{margin:4px 0;color:var(--text-muted,var(--tl-muted,#8997af));font-size:11px;line-height:1.65}
.free-assets-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:12px 0}
.free-assets-toolbar input[type=search]{flex:1;min-width:120px;box-sizing:border-box}
.free-assets-toolbar label{display:flex;align-items:center;gap:5px;font-size:11px;white-space:nowrap}
.free-assets-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px}
.free-assets-tabs button{padding:6px 10px;font-size:11px;border-radius:18px}
.free-assets-tabs button.active{background:var(--primary,#6177e8);border-color:transparent;color:#fff}
.free-asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,160px),1fr));gap:12px}
.free-asset-card{min-width:0;border:1px solid var(--border,var(--tl-line,#34425e));border-radius:12px;overflow:hidden;background:var(--bg-panel,var(--tl-panel,#131a29));display:flex;flex-direction:column}
.free-asset-preview{display:grid;place-items:center;height:112px;background-color:#273043;background-image:linear-gradient(45deg,#ffffff08 25%,transparent 25%),linear-gradient(-45deg,#ffffff08 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ffffff08 75%),linear-gradient(-45deg,transparent 75%,#ffffff08 75%);background-size:18px 18px;background-position:0 0,0 9px,9px -9px,-9px 0}
.free-asset-preview img{max-height:98px;max-width:92%;object-fit:contain}
.free-asset-preview video,.free-asset-preview.lut img{width:100%;height:100%;max-width:100%;max-height:100%;object-fit:cover}
.free-asset-body{padding:11px;display:flex;flex-direction:column;gap:7px;flex:1}
.free-asset-name{display:flex;justify-content:space-between;gap:5px;align-items:baseline;font-size:12px}
.free-asset-name small{font-weight:400;font-size:9px;color:var(--primary,#8092ff);white-space:nowrap}
.free-asset-description{font-size:10px;color:var(--text-muted,var(--tl-muted,#8997af));line-height:1.6;margin:0;flex:1}
.free-asset-meta{font-size:10px;color:var(--text-muted,var(--tl-muted,#8997af))}
.free-asset-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}
.free-asset-actions button{font-size:11px;padding:5px 9px}
.free-asset-actions .primary{flex:1}
.free-asset-license{font-size:10px;padding:0!important;background:transparent!important;border:0!important;color:var(--text-muted,var(--tl-muted,#8997af));text-align:left;cursor:pointer}
.free-assets progress{width:100%;height:6px}
.free-assets-status,.free-assets-error{font-size:12px;line-height:1.7;margin:9px 0;overflow-wrap:anywhere}
.free-assets-error{color:var(--danger,#e78b8b)}
.free-assets-empty{padding:26px 14px;text-align:center;color:var(--text-muted,var(--tl-muted,#8997af))}
.free-assets-license{margin:12px 0;padding:12px;background:var(--bg-hover,#7184e50a);border:1px solid var(--border,var(--tl-line,#34425e));border-radius:9px}
.free-assets-license a{color:var(--primary,#8092ff);overflow-wrap:anywhere}
.free-assets-license pre{white-space:pre-wrap;word-break:break-word;max-height:210px;overflow:auto;font-size:10px;line-height:1.6}
.free-assets-more{margin:15px auto;display:block;font-size:12px}
.tl-library-content .free-assets{padding:10px}
.tl-library-content .free-asset-grid{grid-template-columns:1fr}
.tl-library-content .free-assets-head{margin-top:0}
.tl-library-content .free-assets-toolbar input[type=search]{width:100%}
`;

const FreeAssetLibrary=defineComponent({
  name:'FreeAssetLibrary',
  props:{disabled:Boolean,categories:{type:Array,default:()=>['transition','sticker','effect','template']}},
  emits:['apply','changed'],
  setup(props,{emit}){
    const store=useApp(),items=ref([]),loading=ref(false),error=ref(''),note=ref('');
    const search=ref(''),category=ref('all'),onlyDownloaded=ref(false),limit=ref(12);
    const downloading=ref(''),applying=ref(''),license=ref(null);
    let disposed=false,revision=0;
    const allowed=computed(()=>items.value.filter(row=>props.categories.includes(row.category)));
    const filtered=computed(()=>{
      const query=search.value.trim().toLowerCase();
      return allowed.value.filter(row=>(category.value==='all'||row.category===category.value)&&
        (!onlyDownloaded.value||row.installed)&&(!query||[row.name,row.author,row.description,...(row.tags||[])].join(' ').toLowerCase().includes(query)));
    });
    const taskFor=item=>(store.tasks||[]).find(task=>task.name===`下载免费素材：${item.name}`&&ACTIVE.includes(task.status));
    const working=computed(()=>!!(downloading.value||applying.value));
    async function refresh(){
      const token=++revision;loading.value=true;
      try{const result=await rpc.invoke('video.getFreeAssetCatalog',{});if(!disposed&&token===revision){items.value=result.items||[];error.value='';}}
      catch(e){if(!disposed&&token===revision)error.value=message(e);}
      finally{if(!disposed&&token===revision)loading.value=false;}
    }
    async function download(item){
      if(props.disabled||working.value||taskFor(item))return;
      downloading.value=item.id;error.value='';note.value='';
      try{
        await store.runJob('video.downloadFreeAsset',{id:item.id},false);
        if(!disposed){await refresh();note.value=`“${item.name}”已下载，点击“应用”加入当前剪辑。`;emit('changed');}
      }catch(e){if(!disposed){error.value=message(e);await refresh();error.value=message(e);}}
      finally{if(!disposed)downloading.value='';}
    }
    async function apply(item){
      if(props.disabled||working.value)return;
      applying.value=item.id;error.value='';note.value='';
      try{const result=await rpc.invoke('video.getFreeAsset',{id:item.id});if(!disposed)emit('apply',result);}
      catch(e){if(!disposed){await refresh();error.value=message(e);}}
      finally{if(!disposed)applying.value='';}
    }
    async function showLicense(item){
      if(license.value?.id===item.id){license.value=null;return;}
      try{const reply=await rpc.invoke('video.freeAssetLicense',{id:item.id});if(!disposed)license.value={...item,text:reply.text};}
      catch(e){if(!disposed)error.value=message(e);}
    }
    async function cancel(task){
      try{await rpc.invoke('task.cancel',{taskId:task.taskId});}
      catch(e){if(!disposed)error.value=message(e);}
    }
    watch(()=>JSON.stringify([search.value,category.value,onlyDownloaded.value]),()=>limit.value=12);
    watch(()=>JSON.stringify((store.tasks||[]).filter(t=>t.name?.startsWith('下载免费素材：')).map(t=>[t.taskId,t.status])),()=>{void refresh();});
    onBeforeUnmount(()=>{disposed=true;revision++;});
    void refresh();
    function card(item){
      const task=taskFor(item),pending=!!task||downloading.value===item.id;
      const disabled=props.disabled||working.value||!!task;
      return h('article',{class:'free-asset-card',key:item.id,'data-asset-id':item.id},[
        h('div',{class:['free-asset-preview',item.kind]},[item.preview?.endsWith('.mp4')?
          h('video',{src:'/assets/'+item.preview,muted:true,loop:true,autoplay:true,playsinline:true,preload:'metadata','aria-label':`${item.name}转场演示`}):
          h('img',{src:'/assets/'+item.preview,alt:item.name,loading:'lazy'})]),
        h('div',{class:'free-asset-body'},[
          h('strong',{class:'free-asset-name'},[item.name,h('small',null,item.installed?'已下载':'免费')]),
          h('p',{class:'free-asset-description'},item.description),
          h('span',{class:'free-asset-meta'},`${item.author} · ${bytes(item.size)}`),
          h('button',{id:`free-asset-license-${item.id}`,type:'button',class:'free-asset-license',onClick:()=>showLicense(item)},`来源与授权 · ${item.license}`),
          pending?h('div',null,[h('progress',{max:100,value:Number(task?.progress)||0}),h('small',null,task?.message||'正在准备下载…'),
            task&&task.status!=='cancelling'?h('button',{type:'button',onClick:()=>cancel(task)},'取消下载'):null]):null,
          h('div',{class:'free-asset-actions'},item.installed?
            [h('button',{id:`free-asset-apply-${item.id}`,type:'button',class:'primary',disabled,onClick:()=>apply(item)},applying.value===item.id?'正在添加…':'应用')]:
            [h('button',{id:`free-asset-download-${item.id}`,type:'button',class:'primary',disabled,onClick:()=>download(item)},pending?'下载中…':'下载到我的素材')]),
        ]),
      ]);
    }
    return()=>h('section',{class:'free-assets','aria-label':'免费素材库'},[
      h('style',null,css),
      h('div',{class:'free-assets-head'},[
        h('div',null,[h('strong',null,'免费素材库'),h('p',null,`精选 ${allowed.value.length} 项 · 按需下载 · 下载后可离线使用`)]),
        h('button',{type:'button',disabled:loading.value||working.value,onClick:refresh},loading.value?'加载中…':'刷新'),
      ]),
      h('div',{class:'free-assets-toolbar'},[
        h('input',{id:'free-assets-search',type:'search',placeholder:'搜索贴纸、转场、调色…',value:search.value,'aria-label':'搜索免费素材',onInput:e=>search.value=e.target.value}),
        h('label',null,[h('input',{type:'checkbox',checked:onlyDownloaded.value,onChange:e=>onlyDownloaded.value=e.target.checked}),'只看已下载']),
      ]),
      h('nav',{class:'free-assets-tabs','aria-label':'素材分类'},GROUPS.filter(([id])=>id==='all'||props.categories.includes(id)).map(([id,label])=>
        h('button',{id:`free-assets-category-${id}`,type:'button',class:{active:category.value===id},'aria-pressed':category.value===id,onClick:()=>category.value=id},
          `${label} ${id==='all'?allowed.value.length:allowed.value.filter(row=>row.category===id).length}`))),
      error.value?h('p',{class:'free-assets-error',role:'alert'},error.value):null,
      note.value?h('p',{class:'free-assets-status',role:'status'},note.value):null,
      license.value?h('div',{class:'free-assets-license'},[
        h('strong',null,`${license.value.name} · ${license.value.license}`),
        h('p',null,[h('a',{href:license.value.source,target:'_blank',rel:'noopener noreferrer'},'查看原始素材与固定版本')]),
        h('p',null,'下载时同时保存作者与许可证；转场模板已适配本应用，调色预览为示意画面的实际套用效果。'),
        h('pre',null,license.value.text),
        h('button',{type:'button',onClick:()=>license.value=null},'收起授权说明'),
      ]):null,
      h('div',{class:'free-asset-grid'},filtered.value.slice(0,limit.value).map(card)),
      !loading.value&&!filtered.value.length?h('p',{class:'free-assets-empty'},onlyDownloaded.value?'还没有符合条件的已下载素材。':'未找到匹配素材，试试其它关键词。'):null,
      filtered.value.length>limit.value?h('button',{class:'free-assets-more',type:'button',onClick:()=>limit.value+=12},`加载更多（${Math.min(limit.value,filtered.value.length)}/${filtered.value.length}）`):null,
    ]);
  },
});
export default FreeAssetLibrary;
