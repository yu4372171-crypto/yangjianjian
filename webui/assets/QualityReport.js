import {d as defineComponent,a as h,j as ref,l as rpc} from './index-CVDv6sjN.js';

export async function openEditableProject(row,router,store){
  const project=await rpc.invoke('video.getTaskProject',row.id?{id:row.id}:{path:row.path});
  if(!await store.allowLeave())return;
  localStorage.setItem('aive-timeline-import',JSON.stringify(project));
  await router.push('/video-tools');
  store.taskCenterOpen=false;
}

export default defineComponent({
  name:'QualityReport',
  props:{report:Object,path:String},
  setup(props){
    const preview=ref(null),error=ref('');
    async function seek(row){
      if(!props.path)return;
      try{const url=await rpc.invoke('media.getUrl',{path:props.path});preview.value={url,time:row.start||0};error.value='';}
      catch(e){error.value=e.message||String(e);}
    }
    return()=>props.report?h('details',{class:'quality-report',open:props.report.status==='failed'},[
      h('summary',null,`成片检查 · ${props.report.message||'查看结果'}${props.report.coverage==='sampled'?'（抽样检查）':''}`),
      h('p',{style:{fontSize:'12px',opacity:.75}},'以下结果来自实际导出文件。待复核项可点击定位；主观效果请结合预览判断。'),
      ...(props.report.checks||[]).map(row=>h('div',{style:{display:'flex',gap:'10px',alignItems:'start',padding:'6px 0'}},[
        h('span',null,row.status==='passed'?'✓':row.status==='failed'?'未满足':'待复核'),
        h('button',{onClick:()=>seek(row),disabled:!props.path,style:{textAlign:'left',whiteSpace:'normal'}},
          `${row.label}${row.end>row.start?` · ${row.start.toFixed(1)}–${row.end.toFixed(1)}秒`:''}：${row.message}`)])),
      error.value?h('p',{role:'alert'},error.value):null,
      preview.value?h('video',{key:preview.value.url+preview.value.time,src:preview.value.url,controls:true,
        style:{maxWidth:'100%',maxHeight:'360px'},onLoadedmetadata:e=>{e.target.currentTime=preview.value.time;}}):null,
    ]):null;
  }
});
