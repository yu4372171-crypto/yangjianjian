import { d as defineComponent, j as ref, s as computed, a as h, v as watch, K as onBeforeUnmount, u as useApp, l as rpc, i as useRouter } from './index-CVDv6sjN.js';
import VisionModelLibrary from './VisionModelLibrary.js';
import RequirementModelSelector from './RequirementModelSelector.js';
import ApiConnectionsPanel,{SchedulerControl} from './ApiConnections.js';
import LanguageModelLibrary from './LanguageModelLibrary.js';
import RequirementChat from './RequirementChat.js';
import FreeAssetLibrary from './FreeAssetLibrary.js';
import QualityReport,{openEditableProject} from './QualityReport.js';

const VIDEO_FILTER = '视频素材|*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v;*.mts;*.m2ts|所有文件|*.*';
const VIDEO_EXTENSION = /\.(mp4|mov|mkv|avi|webm|m4v|mts|m2ts)$/i;
const MAX_SIZE = 4 * 1024 ** 3;
const QUICK_PROJECT_KEY = 'aive-smart-quick-project';
const EFFECT_FILTER = '特效素材|*.png;*.webp;*.jpg;*.jpeg;*.mp4;*.mov;*.webm;*.mkv;*.cube;*.json|图片叠加|*.png;*.webp;*.jpg;*.jpeg|视频特效|*.mp4;*.mov;*.webm;*.mkv|调色LUT|*.cube|特效预设|*.json';
const EFFECT_EXTENSION = /\.(png|webp|jpe?g|mp4|mov|webm|mkv|cube|json)$/i;
const EFFECT_MAX_SIZE = 50 * 1024 ** 2;
const subtitleDefaults = () => ({preset:'classic',font:'Microsoft YaHei',size:0,color:'#FFFFFF',outlineColor:'#141414',position:'bottom',outline:2,shadow:1,bold:false});
const effectDefaults = id => ({id,enabled:true,start:0,end:0,opacity:.6,chromaKey:false,keyColor:'#00FF00',position:'center',scale:1,lutStrength:1});
const defaults = () => ({maxApiCalls:100,requirementModelId:'',duration:0,minDuration:0,minSpeed:.25,minDurationPolicy:'slowdown',start:0,speed:1,ratio:'自动',resolution:'原画',keepAudio:true,bgm:false,bgmPath:'',bgmVolume:.18,bgmTrack:'soft',speechLanguage:'auto',subtitleStyle:subtitleDefaults(),transition:{type:'none',duration:.4},defectDetection:{enabled:'auto',mode:'balanced',threshold:.8,padding:.1},effects:[],removeRanges:[],analysisId:'',montageMode:'sequential',shotDuration:3,fitMode:'contain',bgmDucking:false});
const presetStyles={classic:{color:'#FFFFFF',outline:2,shadow:1,bold:false},yellow:{color:'#FFE47A',outline:2,shadow:1,bold:true},boxed:{color:'#FFFFFF',outline:0,shadow:0,bold:false},neon:{color:'#5EF2FF',outline:1,shadow:3,bold:true},fade:{color:'#FFFFFF',outline:2,shadow:1,bold:false},karaoke:{color:'#FFFFFF',outline:2,shadow:1,bold:true}};
const nameOf = path => String(path).split(/[\\/]/).pop();
const css = `.smart-inputs{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:16px;margin:16px 0}.smart-inputs .panel{min-width:0;padding:18px}.smart-inputs h2{margin:0 0 6px;font-size:17px}.smart-inputs .smart-help{color:var(--text-muted,#8190a9);font-size:12px;line-height:1.65;margin:6px 0 12px}.smart-drop{border:2px dashed var(--border,#34425e);border-radius:12px;background:var(--bg-hover,#ffffff05);text-align:center;padding:24px 14px;transition:.15s}.smart-drop.dragging{border-color:var(--primary,#647cff);background:#647cff18}.smart-drop strong{display:block;font-size:15px;margin-bottom:8px}.smart-inputs .smart-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px}.smart-inputs textarea{width:100%;box-sizing:border-box;min-height:110px;resize:vertical;line-height:1.65}.smart-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.smart-options label{font-size:12px;display:flex;flex-direction:column;gap:5px}.smart-options input,.smart-options select{width:100%;min-width:0;box-sizing:border-box}.smart-options .smart-audio{flex-direction:row;align-items:center}.smart-options input[type=checkbox]{width:auto}.smart-clips{max-height:220px;overflow:auto;margin:12px 0;display:grid;gap:7px}.smart-clip{display:flex;gap:8px;align-items:center;background:var(--bg-hover,#ffffff06);padding:8px 10px;border-radius:8px}.smart-clip .smart-clip-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;font-size:12px}.smart-clip button{padding:3px 7px;font-size:12px}.smart-plan{padding:12px;border:1px solid var(--border,#34425e);border-radius:9px;margin-top:12px;line-height:1.75;font-size:13px}.smart-plan strong{display:block}.smart-plan ul{padding-left:20px;margin:8px 0 0}.smart-import-state{font-size:12px;overflow-wrap:anywhere}.smart-import-state progress{width:100%;height:8px}.smart-inputs .smart-error{font-size:12px;color:var(--danger,#ff9d9d);line-height:1.6;overflow-wrap:anywhere}.smart-project-list summary{cursor:pointer;font-size:12px;color:var(--text-muted,#8190a9)}.smart-project-list label{display:flex;gap:7px;padding:5px 0;font-size:12px;overflow-wrap:anywhere}.smart-project-list .smart-clips{max-height:160px}@media(max-width:1150px){.smart-inputs{grid-template-columns:1fr}.smart-options{grid-template-columns:repeat(3,minmax(0,1fr))}}`;

const SmartInputs = defineComponent({
  name:'SmartInputs',emits:['imported','completed','preview'],
  setup(props,{emit,expose}) {
    const store=useApp(),router=useRouter(),text=ref(''),options=ref(defaults()),rows=ref([]),selected=ref([]);
    const importing=ref(false),working=ref(false),dragging=ref(false),message=ref(''),percent=ref(0),error=ref('');
    const plan=ref(null),planId=ref(''),result=ref(''),summary=ref(null);
    const requirementPreview=ref(null),modelRevision=ref(0);
    const chat=ref(null),dialoguePlan=ref(null),dialoguePlanText=ref(''),chatWorking=ref(false);
    const removeClip=ref(''),removeStart=ref(0),removeEnd=ref(0),markUrl=ref(''),markTime=ref(0);
    const vision=ref(null),visionMode=ref('local'),visionModel=ref(''),visionInterval=ref(.5),analyzing=ref(false),suggestions=ref(null),visionError=ref('');
    const catalogs=ref({languages:[],subtitlePresets:[],fontTemplates:[],bgmTracks:[],detectionModes:[],effects:[]}),editorError=ref(''),languageSearch=ref('');
    const musicUrl=ref(''),musicLoading=ref(false),musicError=ref('');
    const speechModel=ref(null),speechDownloading=ref(false),speechError=ref('');
    const speechTask=computed(()=>(store.tasks||[]).find(task=>task.name==='下载语音字幕模型'&&['queued','running','paused','cancelling'].includes(task.status)));
    const effectsOpen=ref(false),effectSelection=ref(''),effectImporting=ref(false),effectDragging=ref(false),effectStatus=ref(''),effectError=ref(''),effectTemplate=ref('');
    const effectTab=ref('mine');
    const busy=computed(()=>!!(importing.value||working.value||chatWorking.value||analyzing.value||effectImporting.value||store.switching));
    const database=computed(()=>store.project?.database_path||'');
    let transfer=null,disposed=false,loadVersion=0,hydrating=false,switchVersion=0,editorVersion=0,musicVersion=0;
    const storageKey=()=>`aive-smart-inputs:${database.value}`;
    function invalidate(){plan.value=null;planId.value='';requirementPreview.value=null;}
    function save(){if(hydrating||!database.value)return;try{localStorage.setItem(storageKey(),JSON.stringify({version:2,text:text.value,options:options.value,selected:selected.value}));}catch{}}
    async function reload(expected=database.value){
      if(!expected)return;
      const version=++loadVersion;
      const response=await rpc.invoke('material.getList',{page:1,pageSize:500,sort:'newest'});
      if(disposed||expected!==database.value||version!==loadVersion)return;
      rows.value=(response.items||[]).filter(row=>row.file_path&&VIDEO_EXTENSION.test(row.file_path)&&row.status!=='missing'&&row.status!=='deleted');
      selected.value=selected.value.filter(path=>rows.value.some(row=>row.file_path===path));
    }
    function fail(e,notify=true){error.value=e instanceof Error?e.message:String(e);if(notify)store.error(e);}
    function cancelled(job){if(job.cancelled||disposed||(!job.preparingProject&&database.value!==job.database))throw Error('视频导入已取消');}
    async function prepareProject(job){
      cancelled(job);
      if(database.value){job.database=database.value;job.preparingProject=false;return;}
      const draft={text:text.value,options:JSON.parse(JSON.stringify(options.value)),dialoguePlan:JSON.parse(JSON.stringify(dialoguePlan.value)),dialoguePlanText:dialoguePlanText.value};
      const changedDraft=!!draft.text.trim()||JSON.stringify(draft.options)!==JSON.stringify(defaults());
      message.value='正在准备剪辑项目…';
      let automatic=false;
      let remembered='';try{remembered=localStorage.getItem(QUICK_PROJECT_KEY)||'';}catch{}
      if(remembered){
        const recent=await rpc.invoke('project.getRecent');cancelled(job);
        const normalized=value=>String(value).replaceAll('\\','/').toLowerCase();
        const existing=recent.find(project=>project.exists&&normalized(project.path)===normalized(remembered));
        if(existing&&!database.value){await store.openProject(existing.path);automatic=!!database.value;}
      }
      cancelled(job);
      if(!database.value){
        const settings=await rpc.invoke('project.getDefaults');cancelled(job);
        if(!settings.path)throw Error('默认保存目录未设置，请在顶部选择项目或设置项目保存目录');
        if(!database.value){
          const now=new Date(),stamp=new Intl.DateTimeFormat('sv-SE',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now).replace(/[^0-9]/g,'');
          await store.createProject(`视频剪辑_${stamp}_${String(now.getMilliseconds()).padStart(3,'0')}`,settings.path,'9:16','blank');
          automatic=!!database.value;
        }
      }
      cancelled(job);
      if(!database.value)throw Error('无法准备剪辑项目，请查看项目创建提示');
      // Let the project watcher hydrate its saved state before restoring an unassigned draft.
      await new Promise(resolve=>setTimeout(resolve,0));cancelled(job);
      job.database=database.value;job.preparingProject=false;
      if(changedDraft){
        text.value=draft.text;options.value=draft.options;
        dialoguePlan.value=draft.dialoguePlan;dialoguePlanText.value=draft.dialoguePlanText;
        save();
      }
      if(automatic)try{localStorage.setItem(QUICK_PROJECT_KEY,database.value);}catch{}
    }
    async function abort(job){if(job?.uploadId){const id=job.uploadId;job.uploadId='';try{await rpc.invoke('video.uploadAbort',{uploadId:id});}catch{}}}
    async function cancelImport(){
      if(transfer){transfer.cancelled=true;await abort(transfer);if(transfer.taskId)try{await rpc.invoke('task.cancel',{taskId:transfer.taskId});}catch{}}
      message.value='正在取消导入…';
    }
    async function importProject(paths,job){
      const submitted=await rpc.invoke('material.import',{paths});job.taskId=submitted.taskId;
      if(!job.taskId)throw Error('素材导入任务未启动，请重试');
      try{
        for(;;){
          cancelled(job);
          const tasks=await rpc.invoke('task.getList');
          const task=tasks.find(task=>task.taskId===job.taskId);
          if(task?.status==='done')return task.result;
          if(task&&['failed','cancelled'].includes(task.status))throw Error(task.error||task.message||'素材导入已取消');
          await new Promise(resolve=>setTimeout(resolve,200));
        }
      }finally{
        if(job.cancelled||disposed||database.value!==job.database)try{await rpc.invoke('task.cancel',{taskId:job.taskId});}catch{}
        job.taskId='';
      }
    }
    async function registerPaths(paths,job){
      if(!paths.length)return;
      cancelled(job);
      message.value='正在导入项目素材…';
      const reply=await importProject(paths,job);
      cancelled(job);
      // Preserve drop/selection order; duplicate imports can refer to existing rows.
      const wanted=[...new Set([...selected.value,...paths])];
      await reload(job.database);
      cancelled(job);
      selected.value=wanted.filter(path=>rows.value.some(row=>row.file_path===path));
      save();invalidate();emit('imported');
      store.toast(`导入 ${reply.added||0} 条视频${reply.skipped?.length?`，${reply.skipped.length} 条跳过`:''}`);
      return paths.filter(path=>rows.value.some(row=>row.file_path===path)).length;
    }
    async function importFiles(files){
      if(busy.value)return;
      if(!files.length)return;
      const job={database:database.value,cancelled:false,uploadId:'',preparingProject:!database.value};transfer=job;
      importing.value=true;error.value='';percent.value=0;
      let importedCount=0;
      try{
        if(files.length>50)throw Error('一次最多拖入50个视频，请分批导入');
        for(const file of files){
          if(!VIDEO_EXTENSION.test(file.name))throw Error(`不支持的文件：${file.name}。请拖入视频文件`);
          if(!Number.isSafeInteger(file.size)||file.size<=0||file.size>MAX_SIZE)throw Error('单个视频大小需大于0，且不超过4GB');
        }
        await prepareProject(job);
        for(let index=0;index<files.length;index++){
          const file=files[index];cancelled(job);
          if(!VIDEO_EXTENSION.test(file.name))throw Error(`不支持的文件：${file.name}。请拖入视频文件`);
          if(!Number.isSafeInteger(file.size)||file.size<=0||file.size>MAX_SIZE)throw Error('单个视频大小需大于0，且不超过4GB');
          message.value=`正在接收 ${index+1}/${files.length}：${file.name}`;
          const start=await rpc.invoke('video.uploadBegin',{name:file.name,size:file.size});
          job.uploadId=start.uploadId;cancelled(job);
          const chunkSize=Math.min(1024*1024,Number(start.chunkSize)||262144);
          if(!Number.isSafeInteger(chunkSize)||chunkSize<=0)throw Error('视频导入通道返回了无效分段大小');
          for(let offset=0;offset<file.size;offset+=chunkSize){
            cancelled(job);
            const bytes=new Uint8Array(await file.slice(offset,Math.min(file.size,offset+chunkSize)).arrayBuffer());
            let binary='';for(let k=0;k<bytes.length;k+=8192)binary+=String.fromCharCode(...bytes.subarray(k,k+8192));
            cancelled(job);
            const response=await rpc.invoke('video.uploadChunk',{uploadId:job.uploadId,offset,base64:btoa(binary)});
            if(response.received!==offset+bytes.length)throw Error('接收的视频长度不一致，请重试');
            percent.value=Math.round(100*(index+response.received/file.size)/files.length);
          }
          cancelled(job);
          message.value=`正在检查视频：${file.name}`;
          const finished=await rpc.invoke('video.uploadFinish',{uploadId:job.uploadId});
          job.uploadId='';cancelled(job);
          // Register each completed file immediately; a later cancelled file keeps earlier imports usable.
          importedCount+=await registerPaths([finished.path],job);
        }
        percent.value=100;message.value=importedCount?`已导入 ${importedCount} 个视频`:'未导入有效视频，请检查文件是否完整';
      }catch(e){
        await abort(job);
        if(job.cancelled||disposed||database.value!==job.database)message.value=`已取消导入${importedCount?`，已完成 ${importedCount} 个视频`:''}`;
        else fail(e);
      }finally{if(transfer===job)transfer=null;importing.value=false;dragging.value=false;}
    }
    async function choose(){
      if(busy.value)return;
      error.value='';importing.value=true;
      const job={database:database.value,cancelled:false,uploadId:'',preparingProject:!database.value};transfer=job;
      try{
        const paths=await rpc.invoke('file.select',{multiple:true,filter:VIDEO_FILTER});
        if(!paths.length)return;
        if(paths.length>50)throw Error('一次最多选择50个视频，请分批导入');
        if(paths.some(path=>!VIDEO_EXTENSION.test(path)))throw Error('请选择视频文件（MP4、MOV、MKV、AVI、WEBM 等）');
        await prepareProject(job);
        const count=await registerPaths(paths,job);percent.value=100;message.value=count?`已选用 ${count} 个项目视频`:'未导入有效视频，请检查文件是否完整';
      }catch(e){if(job.cancelled||disposed)message.value='已取消导入';else fail(e);}
      finally{if(transfer===job)transfer=null;importing.value=false;}
    }
    async function drop(event){event.preventDefault();dragging.value=false;await importFiles(Array.from(event.dataTransfer?.files||[]));}
    function select(path,checked){selected.value=checked?[...selected.value,path]:selected.value.filter(item=>item!==path);}
    function move(index,direction){const clips=[...selected.value],target=index+direction;if(target<0||target>=clips.length)return;[clips[index],clips[target]]=[clips[target],clips[index]];selected.value=clips;}
    async function loadEditorOptions(){
      const version=++editorVersion,expected=database.value;
      try{
        const reply=await rpc.invoke('video.getEditorOptions');
        if(disposed||version!==editorVersion||expected!==database.value)return;
        catalogs.value={...catalogs.value,languages:reply.languages||[],subtitlePresets:reply.subtitlePresets||[],fontTemplates:reply.fontTemplates||[],bgmTracks:reply.bgmTracks||[],detectionModes:reply.detectionModes||[],effects:reply.effects||[]};
        speechModel.value=reply.speechModel||null;
        if(!catalogs.value.effects.some(effect=>effect.id===effectSelection.value))effectSelection.value=catalogs.value.effects[0]?.id||'';
        editorError.value='';
      }catch(e){if(!disposed&&version===editorVersion)editorError.value=`选项加载失败：${e instanceof Error?e.message:String(e)}`;}
    }
    function applySubtitlePreset(id){
      const preset=catalogs.value.subtitlePresets.find(item=>item.id===id);
      options.value.subtitleStyle={...options.value.subtitleStyle,...(presetStyles[id]||{}),...(preset?.style||{}),preset:id};
    }
    async function downloadSpeechModel(){
      if(speechDownloading.value||speechTask.value)return;
      speechDownloading.value=true;speechError.value='';
      try{const status=await store.runJob('video.downloadSpeechModel',{},false);if(!disposed){speechModel.value=status;store.toast('语音字幕模型已安装，可以生成同步字幕');}}
      catch(e){if(!disposed)speechError.value=e instanceof Error?e.message:String(e);}
      finally{speechDownloading.value=false;}
    }
    async function auditionMusic(){
      if(busy.value||musicLoading.value)return;
      const version=++musicVersion,expected=database.value,path=options.value.bgmPath||catalogs.value.bgmTracks.find(track=>track.id===options.value.bgmTrack)?.path;
      musicError.value='';musicUrl.value='';
      if(!path){musicError.value='该配乐暂时无法试听，请选择本地音频或刷新选项。';return;}
      musicLoading.value=true;
      try{const reply=await rpc.invoke('media.getUrl',{path});if(!disposed&&version===musicVersion&&expected===database.value)musicUrl.value=reply;}
      catch(e){if(!disposed&&version===musicVersion)musicError.value=e instanceof Error?e.message:String(e);}
      finally{if(version===musicVersion)musicLoading.value=false;}
    }
    function registerEffect(effect){
      if(!effect?.id)throw Error('特效导入没有返回有效素材，请重试');
      catalogs.value.effects=[...catalogs.value.effects.filter(item=>item.id!==effect.id),effect];effectSelection.value=effect.id;
    }
    function applyFreeAsset(payload){
      if(busy.value)return;
      effectError.value='';effectStatus.value='';
      if(payload.transition){
        options.value.transition={...payload.transition};
        effectStatus.value=`已应用“${payload.item.name}”，将用于多个片段的接缝。`;
        return;
      }
      const effect=payload.effect;
      if(!effect?.id){effectError.value='素材未准备完成，请重新下载';return;}
      const existing=options.value.effects.find(row=>row.id===effect.id);
      if(!existing&&options.value.effects.length>=8){effectError.value='每次最多使用8个特效，请先移除一个已添加特效。';return;}
      registerEffect(effect);
      if(existing)existing.enabled=true;
      else options.value.effects=[...options.value.effects,{...effectDefaults(effect.id),...(payload.item.defaults||{})}];
      effectStatus.value=`已将“${payload.item.name}”加入本次剪辑，可在“我的素材”调整时间、位置和强度。`;
    }
    async function importEffectFiles(files){
      if(busy.value||!files.length)return;
      const expected=database.value,version=switchVersion;effectImporting.value=true;effectError.value='';effectStatus.value='';
      try{
        if(files.length>20)throw Error('一次最多导入20个特效，请分批导入');
        for(const file of files){
          if(!EFFECT_EXTENSION.test(file.name||file.path||''))throw Error('仅支持 PNG、WEBP、JPG、MP4、MOV、WEBM、MKV、CUBE 和 JSON 特效素材');
          if(!file.path&&(!Number.isSafeInteger(file.size)||file.size<=0||file.size>EFFECT_MAX_SIZE))throw Error('拖入的特效需大于0且不超过50MB；较大素材请使用“导入特效文件”按钮');
        }
        for(const file of files){
          if(disposed||expected!==database.value||version!==switchVersion)return;
          effectStatus.value=`正在导入：${file.name||nameOf(file.path)}`;
          let reply;
          if(file.path)reply=await rpc.invoke('video.importEffect',{path:file.path});
          else{
            const bytes=new Uint8Array(await file.arrayBuffer());
            if(bytes.length!==file.size)throw Error('读取的特效长度不一致，请重试');
            let binary='';for(let offset=0;offset<bytes.length;offset+=8192)binary+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
            if(disposed||expected!==database.value||version!==switchVersion)return;
            reply=await rpc.invoke('video.uploadEffect',{name:file.name,base64:btoa(binary)});
          }
          if(disposed||expected!==database.value||version!==switchVersion)return;
          registerEffect(reply.effect);
        }
        effectStatus.value=`已导入 ${files.length} 个特效，选择素材后点击“添加到本次剪辑”。`;
      }catch(e){if(!disposed&&expected===database.value&&version===switchVersion)effectError.value=e instanceof Error?e.message:String(e);}
      finally{effectImporting.value=false;effectDragging.value=false;}
    }
    async function chooseEffects(){
      if(busy.value)return;
      const expected=database.value,version=switchVersion;
      try{const paths=await rpc.invoke('file.select',{multiple:true,filter:EFFECT_FILTER});if(!disposed&&expected===database.value&&version===switchVersion)await importEffectFiles(paths.map(path=>({path,name:nameOf(path)})));}
      catch(e){if(!disposed&&expected===database.value)effectError.value=e instanceof Error?e.message:String(e);}
    }
    async function dropEffects(event){event.preventDefault();effectDragging.value=false;await importEffectFiles(Array.from(event.dataTransfer?.files||[]));}
    function addEffect(){
      if(busy.value||!effectSelection.value)return;
      if(!options.value.effects.some(effect=>effect.id===effectSelection.value))options.value.effects=[...options.value.effects,effectDefaults(effectSelection.value)];
      else options.value.effects.find(effect=>effect.id===effectSelection.value).enabled=true;
      effectStatus.value='已加入本次剪辑，可调整时间和强度。';
    }
    async function removeLibraryEffect(){
      const id=effectSelection.value;if(busy.value||!id)return;
      const expected=database.value,version=switchVersion;effectImporting.value=true;effectError.value='';
      try{
        await rpc.invoke('video.removeEffect',{id});
        if(disposed||expected!==database.value||version!==switchVersion)return;
        catalogs.value.effects=catalogs.value.effects.filter(effect=>effect.id!==id);options.value.effects=options.value.effects.filter(effect=>effect.id!==id);
        effectSelection.value=catalogs.value.effects[0]?.id||'';effectStatus.value='已从特效库移除；原始素材文件仍保留，可再次导入。';
      }catch(e){if(!disposed&&expected===database.value)effectError.value=e instanceof Error?e.message:String(e);}
      finally{effectImporting.value=false;}
    }
    async function showEffectTemplate(){
      try{const reply=await rpc.invoke('video.getEffectTemplate',{});if(!disposed)effectTemplate.value=JSON.stringify(reply.template||reply,null,2);}
      catch(e){effectError.value=e instanceof Error?e.message:String(e);}
    }
    async function chooseMusic(){
      if(busy.value)return;
      const expected=database.value,version=switchVersion;
      try{
        const paths=await rpc.invoke('file.select',{multiple:false,filter:'音频文件|*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg|所有文件|*.*'});
        if(!disposed&&expected===database.value&&version===switchVersion&&paths[0]){options.value.bgmPath=paths[0];options.value.bgm=true;}
      }catch(e){if(!disposed&&expected===database.value&&version===switchVersion)fail(e);}
    }
    function addRemoval(){
      const path=removeClip.value||selected.value[0],start=Number(removeStart.value),end=Number(removeEnd.value);
      const row=rows.value.find(row=>row.file_path===path);
      if(!path||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start){fail(Error('请先选择视频，并填写有效的删除起止时间'));return;}
      if(row?.duration&&end>Number(row.duration)+.02){fail(Error(`结束时间超过视频时长（${Number(row.duration).toFixed(2)}秒）`));return;}
      options.value.removeRanges=[...(options.value.removeRanges||[]),{path,start,end}];error.value='';
    }
    async function previewRemoval(){
      const path=removeClip.value||selected.value[0];if(!path)return;
      try{const url=await rpc.invoke('media.getUrl',{path});if((removeClip.value||selected.value[0])===path&&!disposed){markUrl.value=url;markTime.value=0;}}
      catch(e){fail(e);}
    }
    async function loadVision(){
      try{
        const status=await rpc.invoke('video.visionStatus');if(disposed)return;vision.value=status;
        visionMode.value=status.scheduler?.mode||status.mode||'local';
        const models=status.local?.models||[];
        let remembered='';try{remembered=localStorage.getItem('aive-smart-vision-model')||'';}catch{}
        if(!models.some(model=>model.id===visionModel.value))visionModel.value=models.find(model=>model.id===remembered)?.id||status.local?.selectedModel||models[0]?.id||'';
        visionError.value='';
      }catch(e){if(!disposed)visionError.value=e instanceof Error?e.message:String(e);}
    }
    async function selectVisionModel(value,persist=true){
      const modelId=typeof value==='string'?value:value.id;
      visionModel.value=modelId;
      visionMode.value='local';
      try{
        if(persist&&modelId)await rpc.invoke('video.visionSettings',{modelId});
        localStorage.setItem('aive-smart-vision-model',visionModel.value);
      }catch(e){visionError.value=e instanceof Error?e.message:String(e);throw e;}
    }
    function openModelLibrary(){
      if(typeof document==='undefined')return;
      const library=document.getElementById('vision-model-library');
      if(library){library.open=true;library.scrollIntoView({behavior:'smooth',block:'center'});}
    }
    function openLanguageLibrary(){
      if(typeof document==='undefined')return;
      const library=document.getElementById('smart-language-model-library');
      if(library)library.open=true;
      const models=document.getElementById('language-model-library');
      if(models){models.open=true;models.scrollIntoView({behavior:'smooth',block:'center'});}
    }
    const chatDefaults=()=>({...Object.fromEntries(['start','duration','minDuration','minSpeed','speed','ratio','resolution','keepAudio','bgm','bgmVolume'].map(key=>[key,options.value[key]])),options:Object.fromEntries(['montageMode','shotDuration','fitMode','bgmDucking'].map(key=>[key,options.value[key]]))});
    const chatContext=()=>({sourceCount:selected.value.length,sourceDurations:selected.value.map(path=>Number(rows.value.find(row=>row.file_path===path)?.duration)||0)});
    // Selecting an inference engine does not change an already accepted plan.
    // Keep it out of the context key so the selector's initial refresh cannot
    // reset a plan immediately after the user submits it.
    const chatKey=()=>{
      const {requirementModelId,...planningOptions}=options.value;
      return JSON.stringify([database.value,planningOptions]);
    };
    async function analyze(){
      if(busy.value||!selected.value.length)return;
      if(visionMode.value==='local'&&(!vision.value?.local?.ready||!visionModel.value)){visionError.value='请选择并下载完整的本地视觉模型及视觉组件，然后刷新状态。';return;}
      if(visionMode.value!=='local'&&!vision.value?.scheduler?.ready){visionError.value='请在 API 连接中添加、检测并启用视觉模型。';return;}
      analyzing.value=true;visionError.value='';suggestions.value=null;options.value.analysisId='';
      const expected=database.value,version=switchVersion,paths=[...selected.value],request=text.value,model=visionModel.value,mode=visionMode.value;
      try{
        const reply=await store.runJob('video.analyzeDefects',{paths,text:request||'找出明显穿模或不自然的画面',mode:visionMode.value,modelId:visionModel.value,sampleInterval:visionInterval.value,
          detectionMode:options.value.defectDetection.mode,confidenceThreshold:options.value.defectDetection.threshold,padding:options.value.defectDetection.padding});
        if(!disposed&&expected===database.value&&version===switchVersion&&JSON.stringify(paths)===JSON.stringify(selected.value)&&request===text.value&&model===visionModel.value&&mode===visionMode.value)suggestions.value=reply;
      }catch(e){visionError.value=e instanceof Error?e.message:String(e);store.error(e);}
      finally{analyzing.value=false;}
    }
    function adoptSuggestions(){
      if(!suggestions.value?.analysisId)return;
      const ranges=(suggestions.value.ranges||[]).filter(range=>selected.value[range.index]).map(range=>({path:selected.value[range.index],start:range.start,end:range.end,reason:range.reason,confidence:range.confidence,source:'ai'}));
      options.value.removeRanges=[...(options.value.removeRanges||[]),...ranges];options.value.analysisId=suggestions.value.analysisId;
      store.toast(ranges.length?`已采用 ${ranges.length} 个删除建议，请预览后开始剪辑`:'已采用分析结果：未发现达到阈值的穿模，将保留画面');
    }
    async function buildPlan(){
      if(busy.value||!database.value||!selected.value.length||!text.value.trim())return;
      working.value=true;error.value='';invalidate();
      const expected=database.value,version=switchVersion,snapshot=JSON.stringify([text.value,options.value,selected.value]);
      try{
        if(String(options.value.requirementModelId).startsWith('text-')){
          const reply=await chat.value?.prepare();
          if(reply?.status==='ready')requirementPreview.value={summary:['已生成完整对话剪辑计划，请按需求自动剪辑。'],modelName:options.value.requirementModelId};
          return;
        }
        const removeRanges=(options.value.removeRanges||[]).filter(range=>selected.value.includes(range.path)).map(range=>({index:selected.value.indexOf(range.path),start:Number(range.start),end:Number(range.end)}));
        const intent=await rpc.invoke('video.requirementPlan',{text:text.value.trim(),...options.value});
        if(disposed||expected!==database.value||version!==switchVersion||snapshot!==JSON.stringify([text.value,options.value,selected.value]))return;
        requirementPreview.value=intent;
        if((intent.status&&intent.status!=='ready')||intent.unsupported?.length||intent.subtitles||intent.visualCleanup||intent.operations?.length)return;
        const inferredStyle=intent.options?.subtitleStyle||{},subtitleStyle={...options.value.subtitleStyle};
        if(inferredStyle.preset)for(const key of ['color','outline','shadow','bold'])delete subtitleStyle[key];
        const reply=await rpc.invoke('video.smartPlan',{paths:[...selected.value],...options.value,...intent.settings,...intent.options,text:intent.canonicalText||text.value.trim(),
          removeRanges:intent.preserveFrames?[]:removeRanges,analysisId:intent.preserveFrames?'':options.value.analysisId,
          bgmPath:intent.options?.bgmTrack?'':options.value.bgmPath,subtitleStyle:{...subtitleStyle,...inferredStyle},...(intent.preserveFrames?{montageMode:'sequential'}:{})});
        if(!disposed&&expected===database.value&&version===switchVersion&&snapshot===JSON.stringify([text.value,options.value,selected.value])){plan.value=reply.plan;planId.value=reply.planId;}
      }catch(e){fail(e);}finally{working.value=false;}
    }
    async function execute(){
      if(busy.value||!planId.value||!database.value)return;
      working.value=true;error.value='';result.value='';summary.value=null;const expected=database.value,version=switchVersion;
      try{
        const reply=await store.runJob('video.smartExecute',{planId:planId.value});
        if(!disposed&&expected===database.value&&version===switchVersion){result.value=reply.path||reply.outputs?.[0]?.path||'';await reload(expected);emit('completed',{...reply,path:result.value});store.toast('按需求剪辑完成');}
      }catch(e){fail(e);}finally{working.value=false;}
    }
    function previewResult(){
      emit('preview',{path:result.value});
      if(typeof document!=='undefined')setTimeout(()=>document.querySelector('.preview-column')?.scrollIntoView({behavior:'smooth',block:'center'}),0);
    }
    async function startEditing(){
      if(busy.value)return;
      if(!selected.value.length){fail(Error('请先拖入或选择要剪辑的视频'));return;}
      if(!text.value.trim()){fail(Error('请填写你的剪辑需求'));return;}
      if(!database.value){fail(Error('请先导入视频，准备剪辑项目'));return;}
      working.value=true;error.value='';result.value='';summary.value=null;
      const expected=database.value,version=switchVersion;
      const requestSnapshot=()=>JSON.stringify([text.value,options.value,selected.value,visionMode.value,visionModel.value,visionInterval.value]);
      const snapshot=requestSnapshot(),current=()=>!disposed&&expected===database.value&&version===switchVersion&&snapshot===requestSnapshot();
      try{
        const removeRanges=(options.value.removeRanges||[]).filter(range=>selected.value.includes(range.path)).map(range=>({index:selected.value.indexOf(range.path),start:Number(range.start),end:Number(range.end)}));
        let accepted=dialoguePlanText.value===text.value.trim()?dialoguePlan.value:null;
        if(!accepted)accepted=chat.value?.getPlanForText?.(text.value.trim())||null;
        if(!accepted&&String(options.value.requirementModelId).startsWith('text-')){
          const response=accepted?{status:'ready',plan:accepted}:await chat.value?.prepare();
          if(response?.status!=='ready'||!response.plan)return;
          accepted=response.plan;
        }
        const reply=await store.runJob('video.autoEdit',{paths:[...selected.value],text:text.value.trim(),...options.value,removeRanges,mode:visionMode.value,modelId:visionModel.value,sampleInterval:visionInterval.value,...(accepted?{dialoguePlan:accepted}:{})});
        if(reply.needsClarification){error.value=reply.dialogue?.assistant||'请先在需求对话中补充必要信息';return;}
        if(current()){
          await reload(expected);
          if(current()){result.value=reply.path||reply.outputs?.[0]?.path||'';summary.value=reply;emit('completed',{...reply,path:result.value});store.toast('自动剪辑完成');}
        }
      }catch(e){if(current())fail(e,false);}finally{working.value=false;}
    }
    expose({startEditing,busy,hasInput:computed(()=>!!(selected.value.length||text.value.trim()))});
    watch(()=>JSON.stringify([text.value,options.value,selected.value]),()=>{invalidate();if(dialoguePlanText.value!==text.value.trim())dialoguePlan.value=null;save();},{flush:'sync'});
    watch(()=>JSON.stringify([text.value,selected.value,visionMode.value,visionModel.value,options.value.defectDetection.mode,options.value.defectDetection.threshold,options.value.defectDetection.padding]),()=>{
      if(options.value.analysisId)options.value.analysisId='';
      if((options.value.removeRanges||[]).some(range=>range.source==='ai'||range.confidence!==undefined))options.value.removeRanges=options.value.removeRanges.filter(range=>range.source!=='ai'&&range.confidence===undefined);
      suggestions.value=null;
    });
    watch(()=>JSON.stringify(selected.value),()=>{if(!selected.value.includes(removeClip.value)){removeClip.value=selected.value[0]||'';markUrl.value='';}});
    watch(removeClip,()=>{markUrl.value='';markTime.value=0;removeStart.value=0;removeEnd.value=0;});
    watch(()=>JSON.stringify([options.value.bgmPath,options.value.bgmTrack]),()=>{musicVersion++;musicUrl.value='';musicLoading.value=false;musicError.value='';});
    watch(speechTask,(current,previous)=>{if(previous&&!current&&!disposed)void loadEditorOptions();});
    watch(()=>options.value.defectDetection.mode,mode=>{visionInterval.value=mode==='precise'?.25:.5;});
    watch(database,async(current)=>{
      const version=++switchVersion;hydrating=true;
      let saved={};try{saved=JSON.parse(localStorage.getItem(`aive-smart-inputs:${current}`)||'{}');}catch{}
      if(transfer&&!transfer.preparingProject&&transfer.database!==current){transfer.cancelled=true;await abort(transfer);}
      if(disposed||version!==switchVersion)return;
      loadVersion++;invalidate();rows.value=[];selected.value=[];result.value='';summary.value=null;message.value='';error.value='';
      text.value=typeof saved.text==='string'?saved.text:'';
      const base=defaults(),savedOptions=saved.options&&typeof saved.options==='object'?saved.options:{};
      options.value={...base,...savedOptions,subtitleStyle:{...base.subtitleStyle,...savedOptions.subtitleStyle},transition:{...base.transition,...savedOptions.transition},defectDetection:{...base.defectDetection,...savedOptions.defectDetection},effects:Array.isArray(savedOptions.effects)?savedOptions.effects.filter(effect=>effect&&typeof effect.id==='string').map(effect=>({...effectDefaults(effect.id),...effect})):[]};
      if(saved.version!==2&&saved.options?.duration===30)options.value.duration=0;
      selected.value=Array.isArray(saved.selected)?saved.selected:[];markUrl.value='';removeClip.value='';musicVersion++;musicUrl.value='';musicLoading.value=false;effectStatus.value='';effectError.value='';
      hydrating=false;
      if(current)try{await reload(current);}catch(e){fail(e);}
      await Promise.all([loadVision(),loadEditorOptions()]);
    },{immediate:true});
    onBeforeUnmount(()=>{disposed=true;if(transfer){void cancelImport();}});
    const field=(key,label,type='number',attrs={})=>h('label',null,[label,h('input',{id:`smart-${key}`,type,...attrs,value:options.value[key],disabled:busy.value,onInput:event=>options.value[key]=Number(event.target.value)})]);
    const selectField=(key,label,values)=>h('label',null,[label,h('select',{id:`smart-${key}`,value:options.value[key],disabled:busy.value,onChange:event=>options.value[key]=event.target.value},values.map(value=>h('option',{value},value)))]);
    const editorSelect=(id,label,value,choices,change,attrs={})=>h('label',null,[label,h('select',{id,value,disabled:busy.value,...attrs,onChange:event=>change(event.target.value)},choices.map(choice=>h('option',{value:choice.id??choice.code},choice.name)))]);
    const editorNumber=(id,label,value,change,attrs={})=>h('label',null,[label,h('input',{id,type:'number',value,disabled:busy.value,...attrs,onInput:event=>{const parsed=Number(event.target.value);if(Number.isFinite(parsed))change(Math.min(attrs.max??Infinity,Math.max(attrs.min??-Infinity,parsed)));}})]);
    const editorColor=(id,label,value,change)=>h('label',null,[label,h('input',{id,type:'color',value,disabled:busy.value,onInput:event=>change(event.target.value)})]);
    const languageChoices=()=>{
      const list=[{code:'auto',name:'自动识别语言'},...catalogs.value.languages.filter(language=>language.code!=='auto')],query=languageSearch.value.trim().toLowerCase();
      return list.filter(language=>!query||language.code==='auto'||language.code===options.value.speechLanguage||`${language.name} ${language.code}`.toLowerCase().includes(query));
    };
    const renderAssembly=()=>h('details',{class:'smart-editor-card',id:'smart-assembly'},[
      h('summary',null,'成片方式'),
      h('div',{class:'smart-actions'},[
        h('button',{id:'smart-preset-narration',disabled:busy.value,onClick:()=>Object.assign(options.value,{montageMode:'sequential',fitMode:'blur',keepAudio:true,bgmDucking:true})},'口播保留'),
        h('button',{id:'smart-preset-montage',disabled:busy.value,onClick:()=>Object.assign(options.value,{montageMode:'balanced',shotDuration:3,fitMode:'cover',keepAudio:false,bgm:true,bgmDucking:false})},'素材混剪'),
        h('button',{id:'smart-preset-sequence',disabled:busy.value,onClick:()=>Object.assign(options.value,{montageMode:'sequential',fitMode:'contain',keepAudio:true,bgmDucking:false})},'完整拼接'),
      ]),
      h('div',{class:'smart-options'},[
        editorSelect('smart-montage-mode','素材取法',options.value.montageMode,[{id:'sequential',name:'顺序完整 · 保持口播连贯'},{id:'balanced',name:'均衡取材 · 轮换不同素材'}],value=>options.value.montageMode=value),
        editorNumber('smart-shot-duration','单镜头最长（秒）',options.value.shotDuration,value=>options.value.shotDuration=value,{min:.5,max:30,step:.5,disabled:busy.value||options.value.montageMode!=='balanced'}),
        editorSelect('smart-fit-mode','画幅适配',options.value.fitMode,[{id:'contain',name:'完整画面 · 黑边补齐'},{id:'cover',name:'居中裁切 · 铺满画幅'},{id:'blur',name:'完整画面 · 模糊背景'}],value=>options.value.fitMode=value),
      ]),
      h('label',{class:'smart-audio'},[h('input',{id:'smart-bgm-ducking',type:'checkbox',checked:options.value.bgmDucking,disabled:busy.value,onChange:event=>options.value.bgmDucking=event.target.checked}),'口播配乐避让 · 有原声时压低音乐']),
      h('p',{class:'smart-help'},options.value.montageMode==='balanced'?'轮流从不同素材取片，已删除的区间会排除。镜头按时间选取；原声会随镜头重排，连续口播建议用“顺序完整”。':'按导入顺序保留连续画面。可在需求中写“均衡取材，每个镜头3秒，模糊背景，说话时音乐小一点”；文字中明确的设置优先。'),
    ]);
    const renderStoryboard=value=>value?.storyboard?.length?h('details',{class:'smart-storyboard'},[
      h('summary',null,`镜头清单 · ${value.storyboard.length} 个镜头 / ${value.usedSourceCount} 段素材`),
      h('div',{style:{maxHeight:'200px',overflow:'auto',fontSize:'12px',lineHeight:1.8}},value.storyboard.map((shot,index)=>h('div',{key:index},
        `${index+1}. 素材 ${shot.index+1} · 原片 ${Number(shot.sourceStart).toFixed(2)}–${Number(shot.sourceEnd).toFixed(2)} 秒 → 成片 ${Number(shot.start).toFixed(2)} 秒起 / ${Number(shot.duration).toFixed(2)} 秒`))),
    ]):null;
    const renderSubtitles=()=>{
      const style=options.value.subtitleStyle;
      return h('details',{class:'smart-editor-card'},[
        h('summary',null,'旁白语言与字幕样式'),
        speechModel.value?h('div',{class:'smart-help',id:'smart-speech-model-state'},[
          h('p',null,speechModel.value.ready?'本地语音字幕模型已就绪，可识别口播并生成原文字幕。':speechModel.value.resumable?`已保留 ${(Number(speechModel.value.partialBytes||0)/1024**2).toFixed(1)} MB 下载进度；会先尝试官方源，失败后自动切换国内镜像。`:`首次加字幕需要下载语音模型（约 ${Math.ceil((speechModel.value.modelSize||486209372)/1024**2)} MB），会先尝试官方源，失败后自动切换国内镜像，无需 API 密钥。`),
          !speechModel.value.ready?h('button',{id:'smart-download-speech',disabled:busy.value||speechDownloading.value||!!speechTask.value,onClick:downloadSpeechModel},speechDownloading.value||speechTask.value?'正在下载语音字幕模型…':speechModel.value.resumable?'继续下载语音字幕模型':'下载语音字幕模型'):null,
          speechTask.value?h('div',null,[h('progress',{value:speechTask.value.progress||0,max:100,'aria-label':'语音模型下载进度'}),` ${Math.round(speechTask.value.progress||0)}% · 可在任务中心暂停或取消`]):null,
          speechError.value?h('p',{class:'smart-error',role:'alert'},speechError.value):null,
        ]):null,
        h('style',null,'.smart-subtitle-sample.preset-pop{animation:smart-caption-pop 3s infinite}.smart-subtitle-sample.preset-slide{animation:smart-caption-slide 3s infinite}@keyframes smart-caption-pop{0%{transform:scale(.75)}8%,90%{transform:scale(1)}100%{transform:scale(.75)}}@keyframes smart-caption-slide{0%{transform:translateY(10px)}10%,90%{transform:translateY(0)}100%{transform:translateY(10px)}}'),
        h('p',{class:'smart-help'},'自动识别旁白或指定语言；要求中写“加字幕”即可使用所选样式。下方预览随设置即时变化。'),
        h('div',{class:'smart-options'},[
          h('label',null,['搜索语言',h('input',{id:'smart-language-search',type:'search',value:languageSearch.value,disabled:busy.value,placeholder:'中文、英语、Japanese…',onInput:event=>languageSearch.value=event.target.value})]),
          editorSelect('smart-speech-language','旁白语言',options.value.speechLanguage,languageChoices(),value=>options.value.speechLanguage=value),
          editorSelect('smart-subtitle-preset','字幕预设',style.preset,catalogs.value.subtitlePresets,value=>applySubtitlePreset(value)),
        ]),
        h('div',{id:'smart-subtitle-preview',class:'smart-subtitle-preview',role:'img','aria-label':'字幕样式即时预览',style:{color:style.color,alignItems:style.position==='top'?'flex-start':style.position==='center'?'center':'flex-end'}},[
          h('span',{class:`smart-subtitle-sample preset-${style.preset}`,style:{fontFamily:`"${style.font}",sans-serif`,fontSize:`${style.size||28}px`,fontWeight:style.bold?700:400,WebkitTextStroke:`${Math.min(3,style.outline||0)}px ${style.outlineColor}`,paintOrder:'stroke fill',textShadow:style.preset==='neon'?`0 0 8px ${style.color},0 0 16px ${style.color}`:style.shadow?`0 ${style.shadow}px ${style.shadow*2}px #000`:undefined,background:style.preset==='boxed'?'#111D':undefined}},'这是字幕样式预览'),
        ]),
        h('div',{class:'smart-options'},[
          h('label',null,['字体模板',h('select',{id:'smart-font-template',disabled:busy.value,value:catalogs.value.fontTemplates.find(row=>row.style.font===style.font&&row.style.bold===style.bold)?.id||'',onChange:event=>{const chosen=catalogs.value.fontTemplates.find(row=>row.id===event.target.value);if(chosen)Object.assign(style,chosen.style);}},[
            h('option',{value:''},'自定义字体'),...catalogs.value.fontTemplates.map(row=>h('option',{value:row.id,disabled:!row.available},row.name+(row.available?'':'（未安装）')))])]),
          h('label',null,['字体',h('input',{id:'smart-subtitle-font',type:'text',value:style.font,disabled:busy.value,onInput:event=>style.font=event.target.value,placeholder:'Microsoft YaHei'})]),
          editorNumber('smart-subtitle-size','字号（0为自动）',style.size,value=>style.size=value,{min:0,max:120,step:1}),
          editorSelect('smart-subtitle-position','字幕位置',style.position,[{id:'bottom',name:'底部'},{id:'center',name:'居中'},{id:'top',name:'顶部'}],value=>style.position=value),
          editorColor('smart-subtitle-color','文字颜色',style.color,value=>style.color=value),
          editorColor('smart-subtitle-outline-color','描边颜色',style.outlineColor,value=>style.outlineColor=value),
          editorNumber('smart-subtitle-outline','描边宽度',style.outline,value=>style.outline=value,{min:0,max:8,step:1}),
          editorNumber('smart-subtitle-shadow','阴影强度',style.shadow,value=>style.shadow=value,{min:0,max:8,step:1}),
          h('label',{class:'smart-audio'},[h('input',{id:'smart-subtitle-bold',type:'checkbox',checked:style.bold,disabled:busy.value,onChange:event=>style.bold=event.target.checked}),'粗体字幕']),
        ]),
        h('p',{class:'smart-help'},`${Math.max(0,catalogs.value.languages.filter(language=>language.code!=='auto').length)} 种语言可选 · 字号会根据成片尺寸自动调整；预览字体取决于本机已安装字体。`),
      ]);
    };
    const renderMusic=()=>h('details',{class:'smart-editor-card'},[
      h('summary',null,`背景音乐${options.value.bgm?' · 已开启':''}`),
      h('label',{class:'smart-audio'},[h('input',{id:'smart-bgm',type:'checkbox',checked:options.value.bgm,disabled:busy.value,onChange:event=>options.value.bgm=event.target.checked}),'加入背景音乐（BGM）']),
      h('div',{class:'smart-options'},[
        editorSelect('smart-bgm-track','内置配乐',options.value.bgmTrack,catalogs.value.bgmTracks,value=>{options.value.bgmTrack=value;options.value.bgmPath='';options.value.bgm=true;}),
        h('label',null,['音乐音量',h('input',{id:'smart-bgm-volume',type:'range',min:0,max:100,step:1,value:Math.round(options.value.bgmVolume*100),disabled:busy.value,onInput:event=>options.value.bgmVolume=Number(event.target.value)/100}),`${Math.round(options.value.bgmVolume*100)}%`]),
      ]),
      h('p',{class:'smart-help'},options.value.bgmPath?`当前使用本地音频：${nameOf(options.value.bgmPath)}。本地音频优先于内置配乐。`:catalogs.value.bgmTracks.find(track=>track.id===options.value.bgmTrack)?.description||'选择内置配乐或自己的音频，导出时会淡入淡出并混合原声。'),
      h('div',{class:'smart-actions'},[
        h('button',{disabled:busy.value,onClick:chooseMusic},'选择背景音乐'),
        options.value.bgmPath?h('button',{disabled:busy.value,onClick:()=>{options.value.bgmPath='';options.value.bgm=true;}},'使用内置音乐'):null,
        h('button',{id:'smart-music-audition-button',disabled:busy.value||musicLoading.value,onClick:auditionMusic},musicLoading.value?'正在准备试听…':'试听当前配乐'),
      ]),
      musicUrl.value?h('audio',{id:'smart-music-audition',controls:true,src:musicUrl.value,preload:'metadata','aria-label':'当前背景音乐试听',volume:options.value.bgmVolume,onError:()=>musicError.value='无法播放该音频，请检查素材是否完整。'}):null,
      musicError.value?h('p',{class:'smart-error',role:'alert'},musicError.value):null,
    ]);
    const renderTransitions=()=>h('details',{class:'smart-editor-card'},[
      h('summary',null,`片段转场${options.value.transition.type!=='none'?' · 已开启':''}`),
      h('p',{class:'smart-help'},'需求中写“自动加入转场特效”或“裁掉的衔接部分要加转场”即可使用淡入淡出，也可选择擦除、滑动和叠化。转场应用在保留片段的连接处，声音同步交叉衔接。'),
      h('div',{class:'smart-options'},[
        editorSelect('smart-transition-type','转场效果',options.value.transition.type,[{id:'none',name:'不加转场 / 硬切'},{id:'fade',name:'淡入淡出'},{id:'dissolve',name:'叠化'},{id:'wipeleft',name:'向左擦除'},{id:'wiperight',name:'向右擦除'},{id:'slideleft',name:'向左滑动'},{id:'slideright',name:'向右滑动'}],value=>options.value.transition.type=value),
        editorNumber('smart-transition-duration','期望时长（秒）',options.value.transition.duration,value=>options.value.transition.duration=value,{min:.1,max:2,step:.1}),
      ]),
      h('p',{class:'smart-help'},'过短片段会自动缩短转场。只有一段连续画面时没有连接点；最短成片时长会按转场后的实际时长计算。'),
    ]);
    const renderDefectOptions=()=>{
      const detection=options.value.defectDetection;
      return h('details',{class:'smart-editor-card'},[
        h('summary',null,`智能画面检查 · ${detection.enabled==='auto'?'按需求开启':detection.enabled?'已开启':'已关闭'}`),
        h('label',{class:'smart-audio'},[h('input',{id:'smart-defect-enabled',type:'checkbox',checked:detection.enabled===true,disabled:busy.value,onChange:event=>detection.enabled=event.target.checked}),'自动检测并删除明显画面瑕疵']),
        h('p',{class:'smart-help'},'开启后检查穿模、不自然动作等画面问题。模型判断可能有误，建议预览成片；识别结果会显示在处理摘要中。'),
        h('div',{class:'smart-options'},[
          editorSelect('smart-defect-behavior','检查开关',String(detection.enabled),[{id:'auto',name:'按文字需求开启'},{id:'true',name:'始终开启'},{id:'false',name:'关闭检查'}],value=>detection.enabled=value==='auto'?'auto':value==='true'),
          editorSelect('smart-defect-mode','检测模式',detection.mode,catalogs.value.detectionModes,value=>detection.mode=value),
          h('label',null,['删除置信度',h('input',{id:'smart-defect-threshold',type:'range',min:65,max:95,step:1,value:Math.round(detection.threshold*100),disabled:busy.value,onInput:event=>detection.threshold=Math.max(65,Math.min(95,Number(event.target.value)))/100}),`${Math.round(detection.threshold*100)}%`]),
          editorNumber('smart-defect-padding','删除边缘余量（秒）',detection.padding,value=>detection.padding=value,{min:0,max:1,step:.05}),
        ]),
        h('p',{class:'smart-help'},`${catalogs.value.detectionModes.find(mode=>mode.id===detection.mode)?.description||''} 置信度越高，自动删除越谨慎。视觉模型可在左侧选择和安装。`),
      ]);
    };
    const renderAppliedEffect=effect=>{
      const asset=catalogs.value.effects.find(item=>item.id===effect.id),prefix=`smart-effect-${effect.id}`,lut=asset?.kind==='lut'||/\.cube$/i.test(asset?.path||'');
      return h('div',{class:'smart-applied-effect',key:effect.id},[
        h('div',{class:'smart-actions'},[
          h('label',{class:'smart-audio'},[h('input',{id:`${prefix}-enabled`,type:'checkbox',checked:effect.enabled,disabled:busy.value,onChange:event=>effect.enabled=event.target.checked}),asset?.name||'已保存的特效']),
          h('button',{id:`smart-effect-remove-${effect.id}`,disabled:busy.value,onClick:()=>options.value.effects=options.value.effects.filter(item=>item.id!==effect.id)},'移出本次剪辑'),
        ]),
        h('div',{class:'smart-options'},[
          editorNumber(`${prefix}-start`,'成片起点（秒）',effect.start,value=>effect.start=value,{min:0,step:.1}),
          editorNumber(`${prefix}-end`,'成片终点（0为全程）',effect.end,value=>effect.end=value,{min:0,step:.1}),
          h('label',null,[lut?'LUT强度':'不透明度',h('input',{id:`${prefix}-${lut?'lut-strength':'opacity'}`,type:'range',min:0,max:100,step:1,value:Math.round((lut?effect.lutStrength:effect.opacity)*100),disabled:busy.value,onInput:event=>{if(lut)effect.lutStrength=Number(event.target.value)/100;else effect.opacity=Number(event.target.value)/100;}}),`${Math.round((lut?effect.lutStrength:effect.opacity)*100)}%`]),
          ...(!lut?[
            editorSelect(`${prefix}-position`,'叠加位置',effect.position,[{id:'center',name:'居中'},{id:'top-left',name:'左上'},{id:'top-right',name:'右上'},{id:'bottom-left',name:'左下'},{id:'bottom-right',name:'右下'}],value=>effect.position=value),
            editorNumber(`${prefix}-scale`,'素材缩放',effect.scale,value=>effect.scale=value,{min:.05,max:2,step:.05}),
            h('label',{class:'smart-audio'},[h('input',{id:`${prefix}-chroma`,type:'checkbox',checked:effect.chromaKey,disabled:busy.value,onChange:event=>effect.chromaKey=event.target.checked}),'绿幕 / 指定色抠像']),
            editorColor(`${prefix}-key-color`,'抠像颜色',effect.keyColor,value=>effect.keyColor=value),
          ]:[]),
        ]),
      ]);
    };
    const renderEffects=()=>h('details',{class:'smart-editor-card'},[
      h('summary',null,`特效与免费素材 · 已启用 ${options.value.effects.filter(effect=>effect.enabled).length} 个`),
      h('p',{class:'smart-help'},'从特效库选用图片叠加、绿幕或透明视频、CUBE调色以及JSON参数预设。素材可复用，每次剪辑可分别调整时间与强度。'),
      h('button',{id:'smart-effect-open',disabled:busy.value,onClick:()=>effectsOpen.value=true},'打开特效库'),
      h('button',{id:'smart-free-assets-open',disabled:busy.value,onClick:()=>{effectTab.value='online';effectsOpen.value=true;}},'免费素材下载'),
      ...(!effectsOpen.value?options.value.effects.map(renderAppliedEffect):[]),
    ]);
    const renderEffectWindow=()=>effectsOpen.value?h('div',{class:'smart-effect-backdrop',onClick:event=>{if(event.target===event.currentTarget&&!effectImporting.value)effectsOpen.value=false;}},[
      h('section',{class:'smart-effect-window',role:'dialog','aria-modal':true,'aria-labelledby':'smart-effect-title',onKeydown:event=>{if(event.key==='Escape'&&!effectImporting.value)effectsOpen.value=false;}},[
        h('div',{class:'smart-effect-heading'},[h('h2',{id:'smart-effect-title'},'我的特效库'),h('button',{disabled:effectImporting.value,onClick:()=>effectsOpen.value=false,'aria-label':'关闭特效库'},'关闭')]),
        h('div',{class:'smart-actions',role:'tablist','aria-label':'特效库内容'},[
          h('button',{type:'button',role:'tab','aria-selected':effectTab.value==='mine',class:effectTab.value==='mine'?'primary':'',onClick:()=>effectTab.value='mine'},'我的素材 / 自行导入'),
          h('button',{id:'smart-effect-online-tab',type:'button',role:'tab','aria-selected':effectTab.value==='online',class:effectTab.value==='online'?'primary':'',onClick:()=>effectTab.value='online'},'免费素材下载'),
        ]),
        effectTab.value==='online'&&effectStatus.value?h('p',{class:'smart-help',role:'status'},effectStatus.value):null,
        effectTab.value==='online'&&effectError.value?h('p',{class:'smart-error',role:'alert'},effectError.value):null,
        effectTab.value==='online'?h(FreeAssetLibrary,{disabled:busy.value,onApply:applyFreeAsset,onChanged:loadEditorOptions}):null,
        h('div',{hidden:effectTab.value!=='mine'},[
        h('p',{class:'smart-help'},'导入顾客自己的素材并保存到特效库。支持 PNG / WEBP / JPG 图片叠加，MP4 / MOV / WEBM / MKV 绿幕或透明视频，CUBE调色LUT，JSON简单参数预设。'),
        h('div',{id:'smart-effect-drop',class:['smart-drop',{dragging:effectDragging.value}],'aria-label':'特效导入窗口',onDragover:event=>{event.preventDefault();if(!busy.value){effectDragging.value=true;if(event.dataTransfer)event.dataTransfer.dropEffect='copy';}},onDragleave:()=>effectDragging.value=false,onDrop:dropEffects},[
          h('strong',null,effectDragging.value?'松开鼠标导入特效':'把特效素材拖入这里'),
          h('p',{class:'smart-help'},'拖入素材最大50MB；大视频请通过本地文件选择导入。JSON只读取参数，不运行脚本。'),
          h('button',{id:'smart-effect-import',disabled:busy.value,onClick:chooseEffects},effectImporting.value?'正在导入…':'导入特效文件'),
        ]),
        h('div',{class:'smart-options smart-effect-library-fields'},[
          editorSelect('smart-effect-library','库中素材',effectSelection.value,[{id:'',name:catalogs.value.effects.length?'请选择素材':'特效库为空，请先导入'},...catalogs.value.effects],value=>effectSelection.value=value),
        ]),
        effectSelection.value?h('p',{class:'smart-help'},`类型：${({overlay:'图片叠加',image:'图片叠加',video:'视频特效',lut:'调色LUT',preset:'参数预设'})[catalogs.value.effects.find(effect=>effect.id===effectSelection.value)?.kind]||'特效素材'} · ${catalogs.value.effects.find(effect=>effect.id===effectSelection.value)?.name||''}`):null,
        h('div',{class:'smart-actions'},[
          h('button',{id:'smart-effect-add',class:'primary',disabled:busy.value||!effectSelection.value,onClick:addEffect},'添加到本次剪辑'),
          h('button',{id:'smart-effect-library-remove',disabled:busy.value||!effectSelection.value,onClick:removeLibraryEffect},'从特效库移除'),
          h('button',{disabled:busy.value,onClick:showEffectTemplate},'查看JSON预设格式'),
          h('button',{disabled:busy.value,onClick:loadEditorOptions},'刷新特效库'),
        ]),
        effectStatus.value?h('p',{class:'smart-help',role:'status'},effectStatus.value):null,
        effectError.value?h('p',{class:'smart-error',role:'alert'},effectError.value):null,
        effectTemplate.value?h('label',{class:'smart-template'},['JSON预设示例（可以复制后保存为 .json 文件导入）',h('textarea',{readonly:true,value:effectTemplate.value,'aria-label':'JSON特效参数预设示例'})]):null,
        options.value.effects.length?h('h3',null,'本次剪辑使用的特效'):null,
        ...options.value.effects.map(renderAppliedEffect),
        ]),
      ]),
    ]):null;
    const renderVision=()=>h('details',{class:'smart-removals'},[
          h('summary',null,'画面检查与视觉模型'),
          h('div',{class:'smart-options'},[
            h('label',null,['分析方式',h('select',{id:'smart-vision-mode',disabled:busy.value,value:visionMode.value,onChange:async event=>{const mode=event.target.value;try{await rpc.invoke('video.schedulerSettings',{kind:'vision',mode});await loadVision();}catch(e){visionError.value=e.message||String(e);}}},[h('option',{value:'local'},'本地视觉模型'),h('option',{value:'api'},'顾客 API'),h('option',{value:'auto'},'自动 · API 优先')])]),
            h('label',null,['本地模型',h('select',{id:'smart-vision-model',disabled:busy.value||visionMode.value!=='local',value:visionModel.value,onChange:event=>void selectVisionModel(event.target.value)},[h('option',{value:''},'请选择已下载模型'),...(vision.value?.local?.models||[]).map(model=>h('option',{value:model.id},`${model.name||model.id}${model.id===vision.value?.local?.selectedModel?' · 当前使用':''}`))])]),
            h('label',null,['采样间隔',h('select',{id:'smart-vision-interval',disabled:busy.value,value:visionInterval.value,onChange:event=>visionInterval.value=Number(event.target.value)},[.25,.5,1,2,3].map(value=>h('option',{value},`${value}秒`))) ]),
          ]),
          h('p',{class:'smart-help'},visionMode.value==='local'?(vision.value?.local?.ready?'本地模型已就绪。自动剪辑会按需求检查画面，并显示处理摘要。':'请下载完整本地模型，或添加自己的 API。'):vision.value?.scheduler?.message||'请检测并启用视觉 API'),
          h(SchedulerControl,{kind:'vision',disabled:busy.value,revision:modelRevision.value,onChanged:()=>{void loadVision();modelRevision.value++;}}),
          h('details',null,[h('summary',null,'手动画面检查'),
          h('div',{class:'smart-actions'},[
            h('button',{disabled:busy.value||!selected.value.length||!(visionMode.value==='local'?vision.value?.local?.ready:vision.value?.scheduler?.ready),onClick:analyze},analyzing.value?'正在分析画面…':'AI检查穿模片段'),
            h('button',{disabled:busy.value,onClick:loadVision},'刷新模型状态'),
            h('button',{disabled:busy.value,onClick:()=>router.push({path:'/settings',query:{group:'AI模型与识别'}})},'云端AI设置'),
          ]),
          visionError.value?h('p',{class:'smart-error',role:'alert'},visionError.value):null,
          suggestions.value?h('div',{class:'smart-plan'},[
            h('strong',null,`AI建议（${suggestions.value.modelName||'本地模型'}）`),
            h('p',null,suggestions.value.ranges?.length?`发现 ${suggestions.value.ranges.length} 个疑似片段。采用前请用下方预览复核。`:'未发现达到阈值的穿模片段，可保留全部画面继续剪辑。'),
            ...(suggestions.value.ranges||[]).map(range=>h('div',null,`第${range.index+1}段 ${Number(range.start).toFixed(2)}–${Number(range.end).toFixed(2)}秒：${range.reason||'疑似画面异常'}（${Math.round(Number(range.confidence)*100)}%）`)),
            ...(suggestions.value.notes||[]).map(note=>h('p',{class:'smart-help'},note)),
            h('button',{disabled:busy.value,onClick:adoptSuggestions},suggestions.value.ranges?.length?'采用这些删除建议':'按此分析结果继续'),
          ]):null,
          ]),
          h(VisionModelLibrary,{disabled:busy.value,onInstalled:()=>{modelRevision.value++;void loadVision();},onModelSelected:value=>{visionModel.value=value;visionMode.value='local';try{localStorage.setItem('aive-smart-vision-model',value);}catch{}modelRevision.value++;void loadVision();}}),
        ]);
    return()=>h('div',{class:'smart-inputs'},[
      h('style',null,`.smart-inputs,.smart-effect-window{--border:var(--color-border,#e0e6ef);--bg-hover:var(--color-primary-soft,#f3f5fc);--bg-panel:var(--color-card,#fff);--text:var(--color-text,#1b2538);--text-muted:var(--color-text-secondary,#8190a9);--primary:var(--color-primary,#4b5cf7);--danger:var(--color-error,#ef4444)}`),
      h('style',null,`.smart-editor-card{border:1px solid var(--border,#34425e);background:var(--bg-hover,#ffffff05);padding:12px 14px;border-radius:11px;margin:12px 0}.smart-editor-card>summary{font-size:14px;font-weight:600;cursor:pointer;list-style-position:inside}.smart-editor-card .smart-audio,.smart-effect-window .smart-audio{display:flex;gap:8px;align-items:center;font-size:12px;margin-top:9px}.smart-subtitle-preview{position:relative;box-sizing:border-box;min-height:150px;display:flex;justify-content:center;padding:18px 8px;border-radius:9px;background:radial-gradient(circle at 25% 25%,#35415c,#101622 68%);overflow:hidden}.smart-subtitle-sample{max-width:100%;text-align:center;padding:5px 10px;border-radius:5px;line-height:1.3}.smart-subtitle-sample.preset-fade{animation:smart-subtitle-fade 3s ease-in-out infinite}.smart-subtitle-sample.preset-karaoke{background:linear-gradient(90deg,#FFE47A 0 42%,#FFFFFF 42% 100%);background-size:200% 100%;background-clip:text;-webkit-background-clip:text;color:transparent;animation:smart-subtitle-karaoke 4s linear infinite}.smart-editor-card audio{display:block;max-width:100%;width:100%;height:36px;margin-top:12px}.smart-editor-card input[type=color],.smart-effect-window input[type=color]{height:34px;padding:3px}.smart-effect-backdrop{position:fixed;inset:0;z-index:1200;background:#0009;display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box}.smart-effect-window{box-sizing:border-box;width:min(800px,100%);max-height:88vh;overflow:auto;background:var(--bg-panel,#182133);border:1px solid var(--border,#34425e);color:var(--text,#eff3ff);padding:20px;border-radius:14px;box-shadow:0 20px 70px #0008}.smart-effect-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.smart-effect-heading h2{margin:0}.smart-effect-heading button{flex-shrink:0}.smart-applied-effect{border-top:1px solid var(--border,#34425e);margin-top:12px;padding-top:4px}.smart-effect-library-fields{grid-template-columns:1fr}.smart-template{display:grid;gap:8px;margin-top:14px;font-size:12px}.smart-template textarea{min-height:180px;font-family:monospace}.smart-effect-window h3{font-size:14px;margin-top:20px}@keyframes smart-subtitle-fade{0%,100%{opacity:.25}25%,75%{opacity:1}}@keyframes smart-subtitle-karaoke{from{background-position:100% 0}to{background-position:0 0}}@media(prefers-reduced-motion:reduce){.smart-subtitle-sample{animation:none!important}}@media(max-width:650px){.smart-editor-card .smart-options,.smart-effect-window .smart-options{grid-template-columns:repeat(2,minmax(0,1fr))}.smart-effect-backdrop{padding:10px}.smart-effect-window{padding:14px;max-height:94vh}}`),
      h('style',null,css+`.smart-clip{min-width:0}.smart-clip button{flex-shrink:0}.smart-clips{overflow-x:hidden}.smart-advanced{border-top:1px solid var(--border,#34425e);margin-top:16px;padding-top:12px}.smart-advanced>summary{cursor:pointer;color:var(--text-muted,#8190a9);font-size:13px}.smart-bgm,.smart-removals{border:1px solid var(--border,#34425e);border-radius:9px;padding:12px;margin:12px 0;font-size:12px}.smart-bgm .smart-audio{display:flex;align-items:center;gap:8px}.smart-removals summary{cursor:pointer;font-size:13px;font-weight:600}.smart-removal-fields{display:grid;grid-template-columns:minmax(0,1fr) 110px 110px;gap:8px;margin-top:10px}.smart-removal-fields label{min-width:0;display:grid;gap:5px}.smart-removal-fields input,.smart-removal-fields select{min-width:0;max-width:100%}.smart-removals video{display:block;width:100%;max-height:260px;background:#101827;border-radius:8px;margin-top:10px}.smart-removal-item{display:flex;gap:8px;align-items:center;margin:7px 0}.smart-removal-item span{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media(max-width:650px){.smart-removal-fields{grid-template-columns:1fr}}`),
      h('style',null,`.smart-requirement-composer{border:1px solid var(--border,#dfe5f0);border-radius:20px;background:var(--bg-panel,#fff);padding:16px;transition:border-color .15s,box-shadow .15s}.smart-requirement-composer:focus-within{border-color:var(--primary,#4b5cf7);box-shadow:0 0 0 3px #647cff0c}.smart-inputs .smart-requirement-composer textarea{min-height:128px;padding:0;border:0!important;box-shadow:none!important;outline:none;background:transparent;color:inherit;resize:vertical;font-size:14px;line-height:1.8}.smart-composer-footer{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-top:14px}.smart-inputs .smart-composer-send{display:grid;place-items:center;flex-shrink:0;width:38px;height:38px;padding:0;border:0;border-radius:50%;background:var(--primary,#4b5cf7);color:#fff}.smart-inputs .smart-composer-send:disabled{opacity:.35}.smart-model-management{margin-top:18px;font-size:12px;color:var(--text-muted,#8190a9)}.smart-model-management>summary{cursor:pointer;width:fit-content}.smart-model-management>.language-library{color:var(--text,#1b2538)}@media(max-width:650px){.smart-requirement-composer{padding:13px}.smart-inputs .smart-requirement-composer textarea{min-height:110px}}`),
      h('article',{class:'panel'},[
        h('h2',null,'拖入视频'),h('p',{class:'smart-help'},database.value?'拖入视频后自动导入当前项目，可选择多段并调整剪辑顺序。':'直接拖入或选择视频即可，软件会自动准备剪辑项目。'),
        h('div',{id:'smart-video-drop',class:['smart-drop',{dragging:dragging.value}],onDragover:event=>{event.preventDefault();if(!busy.value){dragging.value=true;if(event.dataTransfer)event.dataTransfer.dropEffect='copy';}},onDragleave:()=>dragging.value=false,onDrop:drop,'aria-label':'视频拖入窗口','aria-disabled':busy.value},[
          h('strong',null,dragging.value?'松开鼠标导入视频':'把视频拖入此窗口'),h('p',{class:'smart-help'},'MP4、MOV、MKV、AVI、WEBM 等 · 单个文件最大4GB · 最多50段'),
          h('button',{disabled:busy.value,onClick:choose},'选择视频'),
        ]),
        message.value?h('div',{class:'smart-import-state',role:'status'},[h('p',null,message.value),importing.value?h('progress',{max:100,value:percent.value}):null]):null,
        importing.value?h('button',{onClick:cancelImport},'取消导入'):null,
        h('div',{class:'smart-clips'},selected.value.map((path,index)=>h('div',{class:'smart-clip',key:path},[
          h('span',null,`${index+1}.`),h('span',{class:'smart-clip-name',title:path},nameOf(path)),
          h('button',{disabled:busy.value,onClick:()=>emit('preview',{path}),'aria-label':`预览第${index+1}段`},'预览'),
          h('button',{disabled:busy.value||index===0,onClick:()=>move(index,-1),'aria-label':`上移第${index+1}段`},'↑'),
          h('button',{disabled:busy.value||index===selected.value.length-1,onClick:()=>move(index,1),'aria-label':`下移第${index+1}段`},'↓'),
          h('button',{disabled:busy.value,onClick:()=>select(path,false),'aria-label':`移出第${index+1}段`},'移出'),
        ]))),
        h('details',{class:'smart-project-list'},[h('summary',null,`选用项目视频（${rows.value.length}）`),h('div',{class:'smart-clips'},rows.value.map(row=>h('label',{key:row.id},[
          h('input',{type:'checkbox',checked:selected.value.includes(row.file_path),disabled:busy.value,onChange:event=>select(row.file_path,event.target.checked)}),row.filename||nameOf(row.file_path),
        ])))]),
        renderVision(),
      ]),
      h('article',{class:'panel'},[
        h('h2',null,'我的需求'),h('p',{class:'smart-help'},'说说你想怎么剪，可继续对话调整。'),
        h('div',{id:'smart-requirement-composer',class:'smart-requirement-composer'},[
          h('textarea',{id:'smart-requirements','aria-label':'我的剪辑需求',maxlength:4000,placeholder:'例如：竖屏，加口播字幕，删去穿模画面，配上柔和音乐。',value:text.value,disabled:busy.value,onInput:event=>text.value=event.target.value,onKeydown:event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)&&!event.isComposing&&!busy.value&&text.value.trim()){event.preventDefault();void chat.value?.prepare();}}}),
          h('div',{id:'smart-composer-footer',class:'smart-composer-footer'},[
            h(RequirementModelSelector,{key:database.value,disabled:busy.value,modelValue:options.value.requirementModelId,revision:modelRevision.value,onChange:id=>{if(options.value.requirementModelId!==id)options.value.requirementModelId=id;},onOpenLibrary:openLanguageLibrary}),
            h('button',{id:'requirement-chat-send',class:'smart-composer-send',disabled:busy.value||!text.value.trim(),onClick:()=>chat.value?.prepare(),'aria-label':chatWorking.value?'正在理解需求':'发送需求',title:'发送需求 · Ctrl+Enter'},[
              chatWorking.value?h('span',{'aria-hidden':'true'},'…'):h('svg',{width:20,height:20,viewBox:'0 0 24 24',fill:'none','aria-hidden':'true'},[h('path',{d:'M12 19V5m-6 6 6-6 6 6',stroke:'currentColor','stroke-width':2,'stroke-linecap':'round','stroke-linejoin':'round'})]),
            ]),
          ]),
        ]),
        h(RequirementChat,{ref:chat,compact:true,text:text.value,modelId:options.value.requirementModelId,contextKey:chatKey(),context:chatContext(),defaults:chatDefaults(),disabled:busy.value,storageKey:`aive-requirement-chat:${database.value}`,onAdopt:value=>{dialoguePlan.value=value;dialoguePlanText.value=value?text.value.trim():'';},onBusy:value=>chatWorking.value=value}),
        h('div',{class:'smart-actions'},[
          h('button',{id:'smart-start-editing',class:'primary',disabled:busy.value||!database.value||!selected.value.length||!text.value.trim(),onClick:startEditing},working.value?'正在自动剪辑…':'按需求自动剪辑'),
          h('button',{id:'smart-preview-requirement',disabled:busy.value||!database.value||!selected.value.length||!text.value.trim(),onClick:buildPlan},'预览需求理解'),
          h('button',{id:'smart-free-assets-quick',disabled:busy.value,onClick:()=>{effectTab.value='online';effectsOpen.value=true;}},'免费素材库'),
          working.value?h('span',{class:'smart-help',role:'status'},'正在处理，可在任务中心查看进度或取消'):null,
        ]),
        requirementPreview.value?h('div',{id:'smart-requirement-preview',class:'smart-plan',role:'status'},[
          h('strong',null,'需求理解预览'),
          ...(requirementPreview.value.summary||[]).map(item=>h('div',null,item)),
          requirementPreview.value.modelName?h('p',{class:'smart-help'},`理解模型：${requirementPreview.value.modelName}`):null,
          requirementPreview.value.unsupported?.length?h('p',{class:'smart-error'},`尚无法执行：${requirementPreview.value.unsupported.join('；')}`):null,
          requirementPreview.value.subtitles||requirementPreview.value.visualCleanup?h('p',{class:'smart-help'},'点击“按需求自动剪辑”会继续进行语音识别 / 画面分析，并剪辑导出。'):null,
        ]):null,
        h('details',{id:'smart-language-model-library',class:'smart-model-management'},[
          h('summary',null,'语言模型库与下载'),
          h(LanguageModelLibrary,{disabled:busy.value,onChanged:()=>{modelRevision.value++;},onSelected:id=>{options.value.requirementModelId=id;modelRevision.value++;}}),
          h(SchedulerControl,{kind:'language',disabled:busy.value,revision:modelRevision.value,onChanged:()=>{options.value.requirementModelId='';modelRevision.value++;}}),
          h('details',{id:'smart-api-connections'},[h('summary',null,'API 连接 · 添加自己的供应商'),
            h(ApiConnectionsPanel,{disabled:busy.value,onChanged:()=>{options.value.requirementModelId='';modelRevision.value++;void loadVision();}})]),
        ]),
        h('details',{class:'smart-advanced'},[
        h('summary',null,'高级选项与手动剪辑'),
        h('div',{class:'smart-options'},[
          field('maxApiCalls','本次 API 最多调用次数（1–500）','number',{min:1,max:500,step:1}),
          h('p',{class:'smart-help'},'达到上限会停止并保留已完成阶段；实际金额由顾客自己的服务商计费。'),
        ]),
        renderAssembly(),
        h('div',{class:'smart-options'},[
          h('label',null,['最短时长选项',h('select',{id:'smart-min-preset',disabled:busy.value,value:[0,5,10,15,30,60,120].includes(options.value.minDuration)?String(options.value.minDuration):'custom',onChange:event=>{if(event.target.value!=='custom')options.value.minDuration=Number(event.target.value);}},[
            ...[0,5,10,15,30,60,120].map(value=>h('option',{value:String(value)},value?`至少 ${value} 秒`:'不限')),h('option',{value:'custom'},'自定义')])]),
          h('label',null,['成片最短时长（秒，0为不限）',h('input',{id:'smart-min-duration',type:'number',min:0,max:86400,step:.1,value:options.value.minDuration,disabled:busy.value,onInput:event=>options.value.minDuration=Number(event.target.value)})]),
          h('label',null,['自动降速最低倍速',h('input',{id:'smart-min-speed',type:'number',min:.25,max:4,step:.05,value:options.value.minSpeed,disabled:busy.value,onInput:event=>options.value.minSpeed=Math.min(options.value.speed,Math.max(.25,Number(event.target.value)))})]),
          h('label',null,['素材不足时',h('select',{id:'smart-min-policy',value:options.value.minDurationPolicy,disabled:busy.value,onChange:event=>options.value.minDurationPolicy=event.target.value},[
            h('option',{value:'slowdown'},'自动降低倍速，尽量达到最短时长'),h('option',{value:'available'},'按实际可用时长导出'),h('option',{value:'strict'},'严格限制，不足时停止导出')])]),
        ]),
        h('p',{class:'smart-help'},'也可以写“成片至少15秒”。默认自动降速至最低0.25倍，尽量达到时长；仍不足时导出最长可用成片，并显示实际时长。'),
        renderSubtitles(),renderMusic(),renderTransitions(),renderDefectOptions(),renderEffects(),
        editorError.value?h('p',{class:'smart-error',role:'alert'},[editorError.value,' ',h('button',{disabled:busy.value,onClick:loadEditorOptions},'重新加载选项')]):null,
        h('div',{class:'smart-options'},[
          field('start','开始时间（秒）','number',{min:0,step:.1}),field('duration','目标时长（秒，0为全部）','number',{min:0,step:.1}),field('speed','播放倍速','number',{min:.25,max:4,step:.25}),
          selectField('ratio','画面比例',['自动','9:16','16:9','1:1','3:4','4:3','21:9']),selectField('resolution','分辨率',['原画','720p','1080p','2K','4K']),
          h('label',{class:'smart-audio'},[h('input',{id:'smart-keepAudio',type:'checkbox',checked:options.value.keepAudio,disabled:busy.value,onChange:event=>options.value.keepAudio=event.target.checked}),'保留原声']),
        ]),
        h('details',{class:'smart-removals',open:/穿模|说错|删.*片段|剪.*部分/.test(text.value)||(options.value.removeRanges||[]).length>0},[
          h('summary',null,'标记要删除的片段'),
          h('p',{class:'smart-help'},'预览视频，标记穿模或其他不需要的片段。起止时间是所选原视频内的秒数；标记区间会从成片中删掉。自动识别画面问题需要可用的视觉模型。'),
          h('div',{class:'smart-removal-fields'},[
            h('label',null,['视频段',h('select',{id:'smart-remove-clip',value:removeClip.value,disabled:busy.value,onChange:event=>removeClip.value=event.target.value},selected.value.map((path,index)=>h('option',{value:path},`${index+1}. ${nameOf(path)}`)))]),
            h('label',null,['删除起点（秒）',h('input',{id:'smart-remove-start',type:'number',min:0,step:.05,value:removeStart.value,disabled:busy.value,onInput:event=>removeStart.value=Number(event.target.value)})]),
            h('label',null,['删除终点（秒）',h('input',{id:'smart-remove-end',type:'number',min:0,step:.05,value:removeEnd.value,disabled:busy.value,onInput:event=>removeEnd.value=Number(event.target.value)})]),
          ]),
          h('div',{class:'smart-actions'},[
            h('button',{disabled:busy.value||!selected.value.length,onClick:previewRemoval},'预览并标记'),
            h('button',{disabled:busy.value||!selected.value.length,onClick:addRemoval},'添加删除片段'),
          ]),
          markUrl.value?h('div',null,[h('video',{controls:true,src:markUrl.value,preload:'metadata','aria-label':'片段标记预览',onTimeupdate:event=>markTime.value=Number(event.target.currentTime)}),h('div',{class:'smart-actions'},[
            h('span',null,`当前预览：${markTime.value.toFixed(2)}秒`),h('button',{disabled:busy.value,onClick:()=>removeStart.value=Math.round(markTime.value*100)/100},'设为删除起点'),h('button',{disabled:busy.value,onClick:()=>removeEnd.value=Math.round(markTime.value*100)/100},'设为删除终点'),
          ])]):null,
          ...(options.value.removeRanges||[]).filter(range=>selected.value.includes(range.path)).map(range=>h('div',{class:'smart-removal-item'},[
            h('span',{title:range.path},`第${selected.value.indexOf(range.path)+1}段：删掉 ${range.start}–${range.end} 秒`),h('button',{disabled:busy.value,onClick:()=>options.value.removeRanges=options.value.removeRanges.filter(item=>item!==range)},'取消删除片段'),
          ])),
        ]),
        h('p',{class:'smart-help'},'需求中明确写出的参数优先于界面设置。取材顺序与画幅适配由“成片方式”控制。'),

        h('div',{class:'smart-actions'},[
          h('button',{disabled:busy.value||!database.value||!selected.value.length||!text.value.trim(),onClick:buildPlan},working.value&&!planId.value?'正在生成计划…':'生成剪辑计划'),
          h('button',{disabled:busy.value||!planId.value||plan.value?.canExecute===false,onClick:execute},'执行手动计划'),
        ]),
        plan.value?h('div',{class:'smart-plan',role:'status'},[
          h('strong',null,'本次剪辑计划'),
          h('div',null,`视频 ${selected.value.length} 段 · 起点 ${plan.value.start??options.value.start} 秒 · 时长 ${Number(plan.value.duration??plan.value.duration_seconds??options.value.duration).toFixed(2)} 秒`),
          plan.value.minDuration?h('div',null,`最短时长 ${plan.value.minDuration} 秒 · ${plan.value.minimumSatisfied?'计划已达到':'将按所选方式处理不足时长'}`):null,
          h('div',null,`${plan.value.ratio||options.value.ratio} · ${plan.value.resolution||options.value.resolution} · ${plan.value.speed??options.value.speed} 倍速 · ${(plan.value.keepAudio??options.value.keepAudio)?'保留原声':'静音'}`),
          h('div',null,plan.value.bgm?`背景音乐：${plan.value.bgmName||'内置轻音乐'} · 音量 ${Math.round((plan.value.bgmVolume??options.value.bgmVolume)*100)}%`:'不添加背景音乐'),
          plan.value.transition?.type!=='none'&&plan.value.transitions?h('div',null,`实际转场：${plan.value.transitions.joins.filter(join=>join.duration>0).length} 处 · 总重叠 ${Number(plan.value.transitions.totalOverlap||0).toFixed(2)} 秒`):null,
          plan.value.removeRanges?.length?h('div',null,`已标记删除 ${plan.value.removeRanges.length} 个片段`):null,
          renderStoryboard(plan.value),
          plan.value.notes?.length?h('ul',null,plan.value.notes.map(note=>h('li',null,note))):null,
        ]):null,
        ]),
        result.value?h('div',{class:'smart-actions'},[h('span',{class:'smart-help'},'已生成视频'),h('button',{onClick:previewResult},'预览成片'),h('button',{onClick:()=>rpc.invoke('file.reveal',{path:result.value}).catch(fail)},'打开文件位置')]):null,
        summary.value?h('div',{class:'smart-plan',role:'status'},[
          h('strong',null,'本次自动处理'),
          h(QualityReport,{report:summary.value.qualityReport,path:result.value}),
          summary.value.editProjectPath?h('button',{onClick:()=>openEditableProject({path:result.value},router,store).catch(fail)},'继续精修 · 打开时间线'):null,
          summary.value.projectWarning?h('p',{class:'smart-error'},summary.value.projectWarning):null,
          summary.value.apiUsage?.apiCalls?h('p',{class:'smart-help'},`本次 API 调用 ${summary.value.apiUsage.apiCalls} / ${summary.value.apiUsage.limit} 次；实际费用以服务商账单为准。`):null,
          summary.value.requirementReport?.length?h('div',{class:'smart-verification'},[
            h('strong',null,summary.value.requirementReport.every(row=>row.status==='verified')?'执行核对：明确参数已满足':'执行核对：存在未完成项'),
            h('p',{class:'smart-help'},'以下核对尺寸、时长、音轨和已执行的剪辑参数；字幕内容、画面瑕疵与观感请结合成片检查和预览确认。'),
            h('details',null,[
              h('summary',null,`查看 ${summary.value.requirementReport.length} 项验收结果`),
              h('ul',null,summary.value.requirementReport.map((row,index)=>h('li',{key:`${row.key}-${index}`},`${row.status==='verified'?'已验收':'未通过'} · ${row.label}：${typeof row.actual==='object'?JSON.stringify(row.actual):row.actual}`))),
            ]),
          ]):null,
          summary.value.plan?h('div',null,`成片 ${Number(summary.value.duration??summary.value.plan.duration??0).toFixed(2)} 秒 · ${summary.value.plan.ratio||'自动'} · ${summary.value.plan.resolution||'原画'} · ${Number(summary.value.plan.speed??1).toFixed(3).replace(/\.?0+$/,'')} 倍速`):null,
          summary.value.plan?.minDuration?h('div',null,`最短要求 ${summary.value.plan.minDuration} 秒 · ${Number(summary.value.duration??summary.value.plan.duration)+.08>=summary.value.plan.minDuration?'已达到':'已导出最长可用成片，仍不足所设时长'}`):null,
          summary.value.plan?.transitions?h('div',null,`已加入 ${summary.value.plan.transitions.joins.filter(join=>join.duration>0).length} 处转场`):null,
          renderStoryboard(summary.value.plan),
          ...(summary.value.plan?.notes||[]).filter(note=>/自动将|最低 0.25|目标时长.*低于/.test(note)).map(note=>h('p',{class:'smart-help'},note)),
          ...(summary.value.intent?.summary||[]).map(item=>h('div',null,item)),
          summary.value.analysis?h('div',null,`${summary.value.analysis.modelName||'本地视觉模型'}：发现 ${(summary.value.analysis.ranges||[]).length} 个异常，优先安全裁景 ${(summary.value.analysis.spatialRepairs||[]).length} 个，必要时删减 ${(summary.value.analysis.temporalFallbacks||[]).length} 个`):null,
          ...(summary.value.analysis?.ranges||[]).map(range=>h('div',null,`第${range.index+1}段 ${Number(range.start).toFixed(2)}–${Number(range.end).toFixed(2)}秒：${(summary.value.analysis.spatialRepairs||[]).some(item=>item.index===range.index&&Math.abs(item.start-range.start)<1e-6&&Math.abs(item.end-range.end)<1e-6)?'安全裁景并保留原时长':'无法安全裁景，已删除对应片段'} · ${range.reason||'画面瑕疵'}`)),
          summary.value.subtitles?h('div',null,`已根据实际旁白生成 ${summary.value.subtitles.count??summary.value.subtitles.cueCount??summary.value.subtitles.segments?.length??0} 条字幕`):null,
          h('details',null,[h('summary',null,'查看处理说明'),...[...new Set([...(summary.value.plan?.notes||[]),...(summary.value.analysis?.notes||[]),...(summary.value.notes||[])])].map(note=>h('p',{class:'smart-help'},note))]),
        ]):null,
        error.value?h('p',{class:'smart-error',role:'alert'},error.value):null,
      ]),
      renderEffectWindow(),
    ]);
  },
});
export default SmartInputs;
