// Shared page/drawer, injected Vue helpers avoid a circular bootstrap import.
export function createTaskCenter({defineComponent,h,ref,computed,watch,onBeforeUnmount,useApp,useRouter,rpc},standalone=false){
  const active=['queued','running','paused','cancelling'];
  const labels={queued:'等待中',running:'处理中',paused:'已暂停',cancelling:'正在取消',cancelled:'已取消',failed:'失败',done:'已完成'};
  const css=`.tc-page{padding:24px;min-width:0}.tc-drawer{width:min(620px,calc(100vw - 28px))!important}.tc-toolbar,.tc-actions,.tc-meta{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.tc-toolbar{margin:14px 0}.tc-toolbar input{flex:1;min-width:130px}.tc-grid{display:grid;gap:12px}.tc-page .tc-grid{grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}.tc-card{border:1px solid var(--color-border,#dce2ed);border-radius:12px;padding:16px;min-width:0;background:var(--color-bg-panel,#fff)}.tc-card h3{margin:0 0 8px;font-size:15px;overflow-wrap:anywhere}.tc-meta,.tc-hint{font-size:12px;color:var(--color-text-secondary,#7b879b);line-height:1.65}.tc-meta{margin-bottom:10px}.tc-card p,.tc-card summary{overflow-wrap:anywhere}.tc-card progress{width:100%;margin:8px 0}.tc-card video{width:100%;max-height:320px;margin-top:12px;background:#101828}.tc-actions{margin-top:12px}.tc-error{color:var(--color-danger,#ce3a4e);font-size:13px;overflow-wrap:anywhere}.tc-tabs button.active{color:#4f5cff;border-color:#4f5cff;background:#4f5cff0b}.tc-modal-backdrop{position:fixed;inset:0;background:#10182888;z-index:10000;display:grid;place-items:center;padding:16px;box-sizing:border-box}.tc-modal{width:min(510px,90vw);max-height:90vh;overflow:auto;box-sizing:border-box;padding:24px;background:var(--color-bg-panel,#fff);border:1px solid var(--color-border,#dce2ed);border-radius:16px;box-shadow:0 18px 60px #0003}.tc-modal label{display:grid;gap:8px;margin:14px 0;font-size:13px}.tc-modal input{width:100%;min-width:0;box-sizing:border-box}.tc-pager{justify-content:center;margin:18px 0}.tc-empty{padding:32px;text-align:center}.tc-live{margin-bottom:16px}.tc-page h1{font-size:27px;margin:0 0 8px}.tc-card details{font-size:12px;margin-top:10px}.tc-modal .tc-actions{justify-content:flex-end}.tc-card-heading{display:flex;align-items:flex-start;gap:10px}.tc-card-heading input{flex:0 0 auto;margin-top:2px;width:17px;height:17px;accent-color:#6366f1}.tc-card-heading h3{flex:1;min-width:0}.tc-card.selected{border-color:#6366f1;box-shadow:0 0 0 1px #6366f130}.tc-batch-toolbar{padding:12px;border:1px solid var(--color-border,#dce2ed);border-radius:10px;background:var(--color-bg-panel,#fff)}.tc-batch-count{margin-right:auto;font-size:13px}.tc-batch-modal{width:min(720px,94vw)}.tc-modal .tc-checkbox{display:flex;align-items:center;gap:8px}.tc-modal .tc-checkbox input{width:16px;height:16px;accent-color:#6366f1}.tc-naming{display:grid;grid-template-columns:minmax(130px,1fr) 110px 110px;gap:12px}.tc-plan{max-height:260px;overflow:auto;border:1px solid var(--color-border,#dce2ed);border-radius:8px;margin:14px 0}.tc-plan table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}.tc-plan th,.tc-plan td{text-align:left;padding:10px;border-bottom:1px solid var(--color-border,#dce2ed);overflow-wrap:anywhere}.tc-plan th{position:sticky;top:0;background:var(--color-bg-panel,#fff)}.tc-plan-arrow{width:18px;color:var(--color-text-secondary,#7b879b)}.tc-batch-status{padding:10px 12px;border-radius:8px;background:#6366f112;overflow-wrap:anywhere}@media(max-width:520px){.tc-modal{padding:18px}.tc-naming{grid-template-columns:1fr 1fr}.tc-naming label:first-child{grid-column:1/-1}.tc-batch-toolbar .tc-batch-count{width:100%}}`;
  return defineComponent({name:standalone?'TaskCenterPage':'TaskCenter',setup(){
    const store=useApp(),router=useRouter(),items=ref([]),total=ref(0),page=ref(1),search=ref(''),tab=ref('outputs'),recoverable=ref([]),resuming=ref(false);
    const loading=ref(false),error=ref(''),download=ref(null),folder=ref(''),filename=ref(''),saving=ref(false),saveError=ref(''),saved=ref(''),preview=ref(null);
    const selected=ref(new Map()),batch=ref(null),batchRunning=ref(false);
    const selectionCount=computed(()=>selected.value.size);
    const batchBusy=computed(()=>saving.value||batchRunning.value);
    const batchPayload=computed(()=>{
      if(!batch.value)return null;
      const form=batch.value,payload={kind:form.kind,ids:Array.from(selected.value.keys())};
      if(form.kind==='download')payload.folder=form.folder.trim();
      if(form.kind==='rename'||form.useNaming)payload.naming={prefix:form.prefix,start:Number(form.start),digits:Number(form.digits)};
      return payload;
    });
    const batchSignature=computed(()=>batchPayload.value?JSON.stringify({payload:batchPayload.value,files:Array.from(selected.value.values(),row=>[row.id,row.path,row.filename])}):'');
    const batchInvalid=computed(()=>{
      const payload=batchPayload.value;if(!payload)return '';
      if(!payload.ids.length)return '请先选择需要处理的成片。';
      if(payload.ids.length>200)return '每次最多处理 200 个成片。';
      if(payload.kind==='download'&&!payload.folder)return '请选择保存文件夹。';
      if(payload.naming){
        if(String(batch.value.start).trim()===''||!Number.isInteger(payload.naming.start)||payload.naming.start<0||payload.naming.start>999999999)return '起始序号需为 0 至 999999999 的整数。';
        if(!Number.isInteger(payload.naming.digits)||payload.naming.digits<1||payload.naming.digits>6)return '序号位数需为 1 至 6 的整数。';
      }
      return '';
    });
    const visible=computed(()=>standalone||store.taskCenterOpen);
    const live=computed(()=>store.tasks.filter(task=>active.includes(task.status)));
    const recent=computed(()=>store.tasks.filter(task=>!active.includes(task.status)));
    const failedCount=computed(()=>store.tasks.filter(task=>task.status==='failed').length);
    let disposed=false,version=0,timer,debounce;
    async function reload(){
      if(!visible.value||disposed)return;
      const token=++version;loading.value=true;
      try{const value=await rpc.invoke('video.getTaskHistory',{page:page.value,pageSize:30,search:search.value});if(token!==version||disposed)return;items.value=value.items;total.value=value.total;error.value='';
        const updated=new Map(selected.value);for(const row of value.items){if(updated.has(row.id)){if(row.available)updated.set(row.id,row);else updated.delete(row.id);}}selected.value=updated;
        try{const saved=await rpc.invoke('video.getRecoverableEdits',{});if(token===version&&!disposed)recoverable.value=saved.items||[];}catch{recoverable.value=[];}}
      catch(e){if(token===version)error.value=e.message||String(e);}
      finally{if(token===version)loading.value=false;}
    }
    watch(visible,value=>{clearInterval(timer);if(value){reload();timer=setInterval(()=>{if(!loading.value&&!batchRunning.value)reload();},6000);}else{version++;loading.value=false;preview.value=null;batch.value=null;}},{immediate:true});
    watch(batchSignature,()=>{if(batch.value){batch.value.plan=null;batch.value.signature='';batch.value.error='';batch.value.saved=null;}},{flush:'sync'});
    watch(()=>store.project?.database_path,()=>{page.value=1;reload();});
    watch(page,reload);
    watch(search,()=>{clearTimeout(debounce);debounce=setTimeout(()=>{page.value=1;reload();},250);});
    watch(failedCount,(value,previous)=>{if(value>(previous??0))tab.value='tasks';},{immediate:true});
    onBeforeUnmount(()=>{disposed=true;version++;clearInterval(timer);clearTimeout(debounce);});
    function openDownload(row){download.value=row;saveError.value='';saved.value='';filename.value=`${row.project||'剪辑成片'}_${row.id.slice(0,8)}${row.filename.slice(row.filename.lastIndexOf('.'))}`.replace(/[<>:"/\\|?*]/g,'_');}
    function selectOutput(row,checked){
      if(batchBusy.value||!row.available)return;
      const next=new Map(selected.value);
      if(checked){if(!next.has(row.id)&&next.size>=200){error.value='每次最多选择 200 个成片，请减少选择后重试。';return;}next.set(row.id,row);}else next.delete(row.id);
      selected.value=next;
    }
    function selectPage(){
      if(batchBusy.value)return;const next=new Map(selected.value);let capped=false;
      for(const row of items.value){if(row.available&&!next.has(row.id)){if(next.size>=200){capped=true;break;}next.set(row.id,row);}}
      selected.value=next;if(capped)error.value='每次最多选择 200 个成片，请减少选择后重试。';
    }
    function openBatch(kind){
      if(batchBusy.value||!selectionCount.value)return;
      batch.value={kind,folder:folder.value,useNaming:kind==='rename',prefix:'成片_',start:1,digits:3,plan:null,signature:'',planning:false,executing:false,picking:false,error:'',saved:null};
    }
    function closeBatch(){batch.value=null;}
    async function pickBatchFolder(){
      const form=batch.value;if(!form||form.picking||form.executing)return;form.picking=true;
      try{const value=await rpc.invoke('folder.select');if(batch.value===form&&value){form.folder=value;folder.value=value;}}
      catch(e){if(batch.value===form)form.error=e.message||String(e);}
      finally{form.picking=false;}
    }
    async function planBatch(){
      const form=batch.value;if(!form||form.planning||form.executing)return;
      if(batchInvalid.value){form.error=batchInvalid.value;return;}
      const signature=batchSignature.value,payload=batchPayload.value;form.planning=true;form.error='';form.plan=null;form.saved=null;
      try{const plan=await rpc.invoke('video.planTaskBatch',payload);if(!disposed&&batch.value===form&&batchSignature.value===signature){form.plan=plan;form.signature=signature;}}
      catch(e){if(batch.value===form&&batchSignature.value===signature)form.error=e.message||String(e);}
      finally{form.planning=false;}
    }
    async function executeBatch(){
      const form=batch.value;if(!form||batchBusy.value||form.planning)return;
      if(!form.plan||form.signature!==batchSignature.value||batchInvalid.value){form.error='请先预览当前选择及命名规则。';return;}
      const plan=form.plan;form.executing=true;batchRunning.value=true;form.error='';form.saved=null;
      try{
        const result=await store.runJob('video.executeTaskBatch',{planId:plan.planId},false);
        if(form.kind==='rename'){
          const updated=new Map(selected.value);
          for(const item of result.items||plan.items){const row=updated.get(item.id);if(row)updated.set(item.id,{...row,filename:item.newName,path:item.path});}
          selected.value=updated;preview.value=null;
        }
        form.plan=null;form.signature='';await reload();
        const count=result.count??plan.count,destination=result.folder||plan.folder;
        if(batch.value===form)form.saved={count,folder:destination};
        store.toast(form.kind==='download'?`已下载 ${count} 个成片到 ${destination}`:`已修改 ${count} 个原成片名称`);
      }
      catch(e){if(batch.value===form){form.error=e.message||String(e);form.plan=null;form.signature='';}else error.value=e.message||String(e);}
      finally{form.executing=false;batchRunning.value=false;}
    }
    async function pickFolder(){try{const selected=await rpc.invoke('folder.select');if(selected)folder.value=selected;}catch(e){saveError.value=e.message;}}
    async function save(){
      if(saving.value)return;saving.value=true;saveError.value='';saved.value='';
      try{const row=download.value;const result=await store.runJob('video.downloadTask',{id:row.id,folder:folder.value.trim(),filename:filename.value.trim()},false);saved.value=result.path;store.toast('成片已保存到所选位置');}
      catch(e){saveError.value=e.message||String(e);}
      finally{saving.value=false;}
    }
    async function showPreview(row,time=0){
      const id=row.id;preview.value={id,url:'',loading:true};
      try{const url=await rpc.invoke('media.getUrl',{path:row.path});if(preview.value?.id===id)preview.value={id,url,time};}
      catch(e){error.value=e.message;preview.value=null;}
    }
    async function control(task,action){try{await rpc.invoke('task.'+action,{taskId:task.taskId});}catch(e){error.value=e.message;}}
    async function resumeEdit(row){
      if(resuming.value)return;resuming.value=true;error.value='';
      try{await store.runJob('video.resumeAutoEdit',{id:row.id},false);await reload();}
      catch(e){error.value=e.message||String(e);}
      finally{resuming.value=false;}
    }
    async function refine(row){
      try{const {openEditableProject}=await import('./QualityReport.js');await openEditableProject(row,router,store);}
      catch(e){error.value=e.message||String(e);}
    }
    async function navigate(task){if(await store.allowLeave()){await router.push(task.location?.route||'/editor/smart');store.taskCenterOpen=false;}}
    const executionDetails=value=>{
      const entries=Object.entries(value||{}).filter(([,row])=>row&&['api','local'].includes(row.executedProvider));
      if(!entries.length)return null;
      return h('details',{class:'tc-ai-execution'},[h('summary',null,'实际使用的 AI 模型'),
        ...entries.map(([kind,row])=>h('p',{class:'tc-hint'},
          `${kind==='language'?'需求理解':kind==='vision'?'画面分析':'模型调用'}：${row.executedProvider==='api'?'API · '+row.connectionName:'本地模型'} / ${row.model}`+
          (row.localFallbackUsed?` · 已回退本地（${row.failureCode||'API_UNAVAILABLE'}）`:'')))]);
    };
    const requirementDetails=value=>{
      const rows=Array.isArray(value)?value.filter(row=>row&&typeof row==='object'):[];
      if(!rows.length)return null;
      const fulfilled=rows.filter(row=>row.status==='verified').length;
      const display=value=>value===undefined||value===null?'未记录':
        typeof value==='boolean'?(value?'是':'否'):typeof value==='object'?JSON.stringify(value):String(value);
      return h('details',{class:'tc-requirements'},[
        h('summary',null,`执行核对 · ${fulfilled}/${rows.length} 项已满足`),
        h('p',{class:'tc-hint'},'保留生成时的参数核对记录；字幕内容、画面瑕疵与观感仍需预览确认。'),
        ...rows.map((row,index)=>h('p',{class:'tc-hint',key:row.key||index,'data-requirement-key':row.key},[
          h('strong',null,`${row.status==='verified'?'✓ 已满足':'待处理'} · ${row.label||row.key||'剪辑要求'}`),
          h('br'),`预期：${display(row.expected)} · 实际：${display(row.actual)}`,
        ])),
      ]);
    };
    const taskCard=task=>h('article',{class:'tc-card',key:task.taskId},[
      h('h3',null,task.name),h('div',{class:'tc-meta'},[labels[task.status]||task.status,` · ${Math.round(task.progress||0)}%`]),
      h('p',{class:'tc-hint'},task.message||''),active.includes(task.status)?h('progress',{value:task.progress||0,max:100,'aria-label':task.name+'进度'}):null,
      task.error?h('p',{class:'tc-error'},task.error):null,
      executionDetails({language:task.result?.languageExecution,vision:task.result?.analysis?.execution,model:task.result?.execution}),
      h('div',{class:'tc-actions'},[active.includes(task.status)?[
        h('button',{disabled:task.status==='cancelling',onClick:()=>control(task,task.status==='paused'?'resume':'pause')},task.status==='paused'?'继续':'暂停'),
        h('button',{disabled:task.status==='cancelling',onClick:()=>control(task,'cancel')},'取消')]:null,
        h('button',{onClick:()=>navigate(task)},'快速定位')]),
      task.result?.taskCenterWarning?h('p',{class:'tc-error'},task.result.taskCenterWarning):null]);
    const outputCard=row=>h('article',{class:['tc-card',{selected:selected.value.has(row.id)}],'data-output-id':row.id,key:row.id},[
      h('div',{class:'tc-card-heading'},[h('input',{id:'task-select-'+row.id,type:'checkbox',checked:selected.value.has(row.id),disabled:!row.available||batchBusy.value,'aria-label':'选择成片 '+row.filename,onChange:e=>selectOutput(row,e.target.checked)}),h('h3',null,row.filename)]),
      h('div',{class:'tc-hint'},row.project?`${row.project} · ${row.name}`:row.name),
      h('div',{class:'tc-meta'},[h('span',null,Number(row.duration)?`${Number(row.duration).toFixed(2)} 秒`:row.filename),h('span',null,row.created_at.replace('T',' ')),h('span',null,row.available?'可下载':'文件已移动、删除或变化')]),
      row.requirements?h('details',null,[h('summary',null,'查看剪辑需求'),h('p',null,row.requirements)]):null,
      executionDetails(row.aiExecution),
      requirementDetails(row.requirementReport),
      row.qualityReport?h('details',null,[
        h('summary',null,`成片检查 · ${row.qualityReport.message}${row.qualityReport.coverage==='sampled'?'（抽样）':''}`),
        ...(row.qualityReport.checks||[]).map(check=>h('p',{class:'tc-hint'},[
          h('button',{disabled:!row.available,onClick:()=>showPreview(row,check.start||0)},
            `${check.status==='passed'?'✓':'待复核'} ${check.label} · ${(check.start||0).toFixed(1)}秒`),
          ' '+check.message]))]):null,
      h('div',{class:'tc-actions'},[
        h('button',{class:'primary',disabled:!row.available||batchBusy.value,onClick:()=>openDownload(row)},'下载成片'),
        h('button',{disabled:!row.available,onClick:()=>showPreview(row)},'预览'),
        row.editProjectPath?h('button',{disabled:!row.available,onClick:()=>refine(row)},'继续精修'):null,
        h('button',{disabled:!row.available,onClick:()=>rpc.invoke('file.reveal',{path:row.path}).catch(e=>error.value=e.message)},'打开位置')]),
      preview.value?.id===row.id?(preview.value.loading?h('p',{class:'tc-hint'},'正在加载预览…'):h('video',{key:row.id+preview.value.time,controls:true,src:preview.value.url,preload:'metadata','aria-label':'任务成片预览',onLoadedmetadata:e=>{e.target.currentTime=preview.value.time||0;},onError:()=>error.value='无法播放该文件，请检查原成片是否完整'})):null]);
    return()=>visible.value?h(standalone?'section':'aside',{class:standalone?'page tc-page':'task-center tc-drawer','aria-label':'任务中心'},[
      h('style',null,css),h('header',null,[h('div',null,[h(standalone?'h1':'h2',null,'任务中心'),h('p',{class:'tc-hint'},'生成的视频自动保留记录，重启后可继续预览和下载。')]),
        !standalone?h('button',{'aria-label':'关闭任务中心',onClick:()=>store.taskCenterOpen=false},'关闭'):null]),
      h('div',{class:standalone?'':'task-body'},[
        h('div',{class:'tc-toolbar tc-tabs'},[
          h('button',{class:{active:tab.value==='outputs'},onClick:()=>tab.value='outputs'},`成片下载 (${total.value})`),
          h('button',{class:{active:tab.value==='tasks'},onClick:()=>tab.value='tasks'},`运行任务 (${live.value.length})`),
          h('button',{disabled:loading.value,onClick:reload},loading.value?'刷新中…':'刷新'),
          !standalone?h('button',{onClick:async()=>{if(await store.allowLeave()){await router.push('/tasks');store.taskCenterOpen=false;}}},'展开任务中心'):null]),
        error.value?h('p',{class:'tc-error',role:'alert'},error.value):null,
        recoverable.value.length?h('details',{class:'tc-card'},[
          h('summary',null,`当前项目可继续的任务 (${recoverable.value.length})`),
          h('p',{class:'tc-hint'},'中断任务可从已完成阶段继续；本轮已完成的剪辑可复用原素材与需求重新生成。'),
          ...recoverable.value.map(row=>h('div',{class:'tc-hint'},[
            h('p',null,row.text),h('span',null,row.status==='done'?'已完成 · 可安全重新生成':`已保存 ${row.completedStages.join('、')||'输入素材'} · ${row.code||'任务中断'}`),
            h('button',{disabled:resuming.value,onClick:()=>resumeEdit(row)},row.status==='done'?'按原需求重新生成':'从已完成阶段继续')]))]):null,
        live.value.length?h('div',{class:'tc-live tc-grid'},live.value.map(taskCard)):null,
        tab.value==='tasks'?h('div',{class:'tc-grid'},recent.value.map(taskCard)):[
          h('div',{class:'tc-toolbar'},[h('input',{type:'search','aria-label':'搜索成片任务',placeholder:'搜索项目、任务或剪辑需求',value:search.value,onInput:e=>search.value=e.target.value})]),
          h('div',{class:'tc-toolbar tc-batch-toolbar'},[
            h('span',{class:'tc-batch-count',role:'status','aria-live':'polite'},`已选择 ${selectionCount.value} 个（最多 200 个）`),
            h('button',{disabled:batchBusy.value||!items.value.some(row=>row.available),onClick:selectPage},'全选本页'),
            h('button',{disabled:batchBusy.value||!selectionCount.value,onClick:()=>selected.value=new Map()},'清空选择'),
            h('button',{id:'task-batch-download',class:'primary',disabled:batchBusy.value||!selectionCount.value,onClick:()=>openBatch('download')},'批量下载'),
            h('button',{id:'task-batch-rename',disabled:batchBusy.value||!selectionCount.value,onClick:()=>openBatch('rename')},'批量改名')]),
          !items.value.length&&!loading.value?h('p',{class:'tc-empty tc-hint'},search.value?'没有匹配的成片':'还没有已完成的成片，生成后会自动出现在这里。'):null,
          h('div',{class:'tc-grid'},items.value.map(outputCard)),
          total.value>30?h('div',{class:'tc-actions tc-pager'},[h('button',{disabled:page.value<=1||loading.value,onClick:()=>page.value--},'上一页'),`${page.value} / ${Math.max(1,Math.ceil(total.value/30))}`,h('button',{disabled:page.value*30>=total.value||loading.value,onClick:()=>page.value++},'下一页')]):null,
          h('p',{class:'tc-hint'},'下载会把原成片复制到你选择的文件夹。请保留项目中的原文件，以便后续下载。')]]),
      download.value?h('div',{class:'tc-modal-backdrop',onClick:e=>{if(e.target===e.currentTarget&&!saving.value)download.value=null;}},[h('section',{class:'tc-modal',role:'dialog','aria-modal':true,'aria-label':'下载成片',onKeydown:e=>{if(e.key==='Escape'&&!saving.value)download.value=null;}},[
        h('h2',null,'下载成片'),h('p',{class:'tc-hint'},'选择保存位置，并为视频命名。'),
        h('label',null,['保存文件夹',h('input',{id:'task-download-folder',value:folder.value,disabled:saving.value,onInput:e=>folder.value=e.target.value,placeholder:'点击选择文件夹或填写完整路径'})]),
        h('button',{disabled:saving.value,onClick:pickFolder},'选择文件夹'),
        h('label',null,['文件名',h('input',{id:'task-download-filename',value:filename.value,disabled:saving.value,onInput:e=>filename.value=e.target.value})]),
        saveError.value?h('p',{class:'tc-error',role:'alert'},saveError.value):null,
        saved.value?h('p',{class:'tc-hint',role:'status'},`已保存：${saved.value}`):null,
        h('div',{class:'tc-actions'},[h('button',{disabled:saving.value,onClick:()=>download.value=null},saved.value?'关闭':'取消'),saved.value?h('button',{onClick:()=>rpc.invoke('file.reveal',{path:saved.value}).catch(e=>saveError.value=e.message)},'打开下载位置'):null,
          h('button',{class:'primary',disabled:saving.value||!folder.value.trim()||!filename.value.trim(),onClick:save},saving.value?'正在保存…':'保存到此处')])])]):null,
      batch.value?h('div',{class:'tc-modal-backdrop',onClick:e=>{if(e.target===e.currentTarget)closeBatch();}},[h('section',{class:'tc-modal tc-batch-modal',role:'dialog','aria-modal':true,'aria-label':batch.value.kind==='download'?'批量下载成片':'批量修改成片名称',onKeydown:e=>{if(e.key==='Escape')closeBatch();}},[
        h('h2',null,batch.value.kind==='download'?'批量下载成片':'修改项目内原成片名称'),
        h('p',{class:'tc-hint'},batch.value.kind==='download'?`将选中的 ${selectionCount.value} 个成片复制到指定文件夹，可保留原名或统一命名。`:`将直接修改选中的 ${selectionCount.value} 个项目原成片文件名，并同步更新任务记录。请先预览原名与新名。`),
        batch.value.kind==='download'?[
          h('label',null,['保存文件夹',h('input',{id:'task-batch-folder',value:batch.value.folder,disabled:batch.value.executing,onInput:e=>batch.value.folder=e.target.value,placeholder:'选择文件夹或填写完整路径'})]),
          h('button',{disabled:batch.value.executing||batch.value.picking,onClick:pickBatchFolder},batch.value.picking?'正在选择…':'选择文件夹'),
          h('label',{class:'tc-checkbox'},[h('input',{id:'task-batch-use-naming',type:'checkbox',checked:batch.value.useNaming,disabled:batch.value.executing,onChange:e=>batch.value.useNaming=e.target.checked}),'统一命名下载副本'])]:null,
        batch.value.kind==='rename'||batch.value.useNaming?h('div',{class:'tc-naming'},[
          h('label',null,['文件名前缀',h('input',{id:'task-batch-prefix',value:batch.value.prefix,disabled:batch.value.executing,placeholder:'例如：客户成片_',onInput:e=>batch.value.prefix=e.target.value})]),
          h('label',null,['起始序号',h('input',{id:'task-batch-start',type:'number',min:0,max:999999999,step:1,value:batch.value.start,disabled:batch.value.executing,onInput:e=>batch.value.start=e.target.value})]),
          h('label',null,['序号位数',h('input',{id:'task-batch-digits',type:'number',min:1,max:6,step:1,value:batch.value.digits,disabled:batch.value.executing,onInput:e=>batch.value.digits=e.target.value})])]):null,
        batch.value.kind==='rename'||batch.value.useNaming?h('p',{class:'tc-hint'},'按选择顺序连续编号，保留视频扩展名。例如：成片_001.mp4、成片_002.mp4。'):null,
        batchInvalid.value?h('p',{class:'tc-hint',role:'status'},batchInvalid.value):null,
        batch.value.error?h('p',{class:'tc-error',role:'alert'},batch.value.error):null,
        batch.value.plan?[
          h('p',{class:'tc-hint'},`已预览 ${batch.value.plan.count} 个文件。请核对后${batch.value.kind==='download'?'下载':'修改原成片名称'}。`),
          h('div',{class:'tc-plan'},[h('table',{'aria-label':'批量文件名预览'},[h('thead',null,[h('tr',null,[h('th',null,'原文件名'),h('th',{class:'tc-plan-arrow'},''),h('th',null,'新文件名')])]),h('tbody',null,batch.value.plan.items.map(item=>h('tr',{key:item.id},[h('td',null,item.oldName),h('td',{class:'tc-plan-arrow'},'→'),h('td',null,item.newName)])))])])]:null,
        batch.value.executing?h('p',{class:'tc-hint',role:'status'},'正在处理，可关闭此窗口并在运行任务中查看进度。'):null,
        batch.value.saved?h('p',{class:'tc-batch-status',role:'status'},batch.value.kind==='download'?`已下载 ${batch.value.saved.count} 个成片至：${batch.value.saved.folder}`:`已修改 ${batch.value.saved.count} 个原成片名称，任务记录已更新。`):null,
        h('div',{class:'tc-actions'},[
          h('button',{onClick:closeBatch},batch.value.saved||batch.value.executing?'关闭':'取消'),
          batch.value.saved?.folder?h('button',{onClick:()=>rpc.invoke('file.reveal',{path:batch.value.saved.folder}).catch(e=>{if(batch.value)batch.value.error=e.message||String(e);})},'打开下载位置'):null,
          h('button',{id:'task-batch-preview',disabled:batch.value.executing||batch.value.planning||batch.value.picking||!!batchInvalid.value,onClick:planBatch},batch.value.planning?'正在预览…':'预览文件名'),
          h('button',{id:'task-batch-execute',class:'primary',disabled:batchBusy.value||batch.value.planning||!!batchInvalid.value||!batch.value.plan||batch.value.signature!==batchSignature.value,onClick:executeBatch},batch.value.executing?'正在处理…':batch.value.kind==='download'?'开始批量下载':'确认修改原成片名称')])])]):null
    ]):null;
  }});
}
