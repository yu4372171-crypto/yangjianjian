"""One cancellable job turns real requirements into checked media operations."""
import copy
import importlib.util
import math
from pathlib import Path
import sys
import tempfile

from app.ui2.common import BridgeError
from app.workers.control import check_control


def _load(name):
    identifier='_aive_'+name
    module=sys.modules.get(identifier)
    if module is None:
        spec=importlib.util.spec_from_file_location(identifier,Path(__file__).with_name(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[identifier]=module
        try:spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(identifier,None);raise
    return module


def _load_intent():return _load('smart_intent')


def _fingerprint(path):
    try:
        stat=path.stat();return stat.st_size,stat.st_mtime_ns,stat.st_ino
    except OSError:raise BridgeError('SMART_EDIT_CHANGED','输入视频已变化，请重新开始')


def _detection_options(data):
    values=data.get('defectDetection',{})
    if not isinstance(values,dict) or set(values)-{'enabled','mode','threshold','padding'}:
        raise BridgeError('SMART_AUTO_INPUT','穿模检测设置格式无效')
    result={'enabled':'auto','mode':'balanced','threshold':.8,'padding':.1,**values}
    enabled=result['enabled']
    if not isinstance(enabled,bool) and not (isinstance(enabled,str) and enabled=='auto'):
        raise BridgeError('SMART_AUTO_INPUT','穿模检测开关必须为自动、开启或关闭')
    if not isinstance(result['mode'],str) or result['mode'] not in ('fast','balanced','precise'):
        raise BridgeError('SMART_AUTO_INPUT','请选择快速、均衡或精细穿模检测')
    for key,low,high in (('threshold',.65,.95),('padding',0,1)):
        value=result[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise BridgeError('SMART_AUTO_INPUT',f'穿模检测 {key} 必须在 {low}–{high} 之间')
        result[key]=float(value)
    return result


class SmartAutoMixin:
    def _workflow_configuration(self):
        result={'engine':'quality-workflow-1'}
        for kind in ('language','vision'):
            status=_load('ai_scheduler').get_scheduler_status(kind)
            result[kind]={key:status.get(key) for key in ('mode','model','localModelId','connectionId')}
            result[kind]['revision']=(status.get('connection') or {}).get('configurationRevision','')
        result['speech']=_load('local_speech').get_status().get('selectedModel','default')
        return result

    def video_getRecoverableEdits(self,data):
        _,directory=self._smart_project()
        return {'items':_load('workflow_store').WorkflowStore(directory).list()}

    def video_resumeAutoEdit(self,data):
        _,directory=self._smart_project()
        try:
            run=_load('workflow_store').WorkflowStore(directory).resume(data.get('id'),self._workflow_configuration())
            return self.video_autoEdit({**run.request,'resumeId':run.identifier})
        except ValueError as error:
            raise BridgeError('SMART_RESUME_INVALID',str(error)) from error

    def video_downloadSpeechModel(self,data):
        def work(progress,control):
            check_control(control)
            def report(value,message=''):
                check_control(control)
                progress(value,message)
            return _load('speech_model_download').install_model(report,control)
        return self.api.tasks.start('下载语音字幕模型',work,category='model',location={'route':'/editor/smart'})

    def video_autoStatus(self,data):
        return {'speech':_load('local_speech').get_status(),'vision':self.video_visionStatus({})['local'],'mode':'local'}

    def video_autoEdit(self,data):
        identity=self._smart_project()
        text=data.get('text')
        paths=data.get('paths')
        if not isinstance(text,str) or not text.strip() or len(text)>4000:
            raise BridgeError('SMART_AUTO_INPUT','请填写剪辑需求（最多4000字）')
        if not isinstance(paths,list) or not 1<=len(paths)<=50:
            raise BridgeError('SMART_AUTO_INPUT','请先放入1–50段视频')
        if data.get('mode','local') not in ('local','api','auto'):
            raise BridgeError('VISION_NOT_CONFIGURED','请选择本地、API 或自动视觉服务')
        detection=_detection_options(data)
        try:
            requirement_models=_load('requirement_models')
            requirement_model=requirement_models.validate_model_id(data.get('requirementModelId'))
            if requirement_model is None:requirement_model=requirement_models.get_status()['selectedModel']
        except RuntimeError as error:
            raise BridgeError(getattr(error,'code','SMART_REQUIREMENT_MODEL'),getattr(error,'message',str(error))) from error
        helpers=self._smart_helpers
        sources=[helpers['_local_path'](path,existing=True) for path in paths]
        snapshots=[_fingerprint(path) for path in sources]
        request=copy.deepcopy(data)
        request['requirementModelId']=requirement_model
        text=text.strip()
        try:
            storage=_load('workflow_store').WorkflowStore(identity[1])
            configuration=self._workflow_configuration()
            recovery=(storage.resume(request['resumeId'],configuration) if request.get('resumeId')
                      else storage.begin(request,configuration))
            if request.get('resumeId'):
                original=recovery.request
                if {k:v for k,v in request.items() if k!='resumeId'}!=original:
                    raise ValueError('恢复请求已变化，请按原任务继续或重新生成')
        except (ValueError,OSError) as error:
            raise BridgeError('SMART_RESUME_INVALID',str(error)) from error

        def bound():
            if self._smart_project()!=identity or [_fingerprint(path) for path in sources]!=snapshots:
                raise BridgeError('SMART_EDIT_CHANGED','项目或输入视频已变化，请重新开始自动剪辑')

        def work(progress,control):
            _load('ai_scheduler').clear_execution('language')
            check_control(control);bound()
            progress(1,'正在理解我的需求')
            infos=[]
            for source in sources:
                check_control(control);bound()
                infos.append(helpers['_probe'](self.api.ctx.ffmpeg_tool(),source))
            bound()
            defaults={key:request[key] for key in ('start','duration','minDuration','minSpeed','speed','ratio','resolution','keepAudio','bgm','bgmVolume') if key in request}
            defaults['totalDuration']=sum(info['duration'] for info in infos)
            try:defaults['options']=_load('smart_assembly').options(request,partial=True)
            except ValueError as error:raise BridgeError('SMART_AUTO_INPUT',str(error)) from error
            def intent_progress(value,message=''):
                if isinstance(value,str):progress(3,value)
                else:progress(2+min(7,max(0,value)*.07),message)
            try:
                dialogue_plan=request.get('dialoguePlan')
                cached_intent=recovery.get('intent')
                if cached_intent is not None:
                    intent=cached_intent
                    progress(8,'已恢复完成的需求理解')
                elif dialogue_plan is not None or str(requirement_model or '').startswith('text-'):
                    planner=_load('dialogue_planner')
                    context={'sourceCount':len(sources),'sourceDurations':[row['duration'] for row in infos]}
                    if dialogue_plan is None:
                        reply=planner.chat({'text':text,'messages':request.get('messages',[]),
                            'previousPlan':request.get('previousPlan'),'context':context,'defaults':defaults,
                            'requirementModelId':requirement_model},control=control,progress=intent_progress)
                        if reply['status']!='ready':
                            return {'needsClarification':True,'dialogue':reply,'requirements':text}
                        dialogue_plan=reply['plan']
                    dialogue_plan=planner.recover_plan(dialogue_plan,context,text)
                    intent=planner.plan_to_intent(dialogue_plan)
                else:
                    intent=_load_intent().interpret_requirements(text,defaults,model_id=request.get('requirementModelId'),control=control,
                        progress=intent_progress)
            except RuntimeError as error:
                raise BridgeError(getattr(error,'code','SMART_AUTO_INTENT'),getattr(error,'message',str(error))) from error
            check_control(control);bound()
            smart_intent=_load('smart_intent')
            intent=smart_intent.apply_explicit_requirements(intent,text)
            requirement_contract=smart_intent.explicit_requirement_contract(text)
            if intent.get('unsupported'):
                raise BridgeError('SMART_EDIT_UNSUPPORTED','这些要求目前无法执行：'+'；'.join(intent['unsupported'])+'。已停止生成，请调整要求。')
            intent=copy.deepcopy(intent)
            if 'visualCleanup' not in intent.get('specifiedFeatures',[]):
                if detection['enabled']!='auto':intent['visualCleanup']=detection['enabled']
            if intent.get('preserveFrames'):intent['visualCleanup']=False
            recovery.save('intent',intent)
            analysis=None
            source_crops={}
            removals=copy.deepcopy(request.get('removeRanges',[]))
            if not isinstance(removals,list):raise BridgeError('SMART_AUTO_INPUT','删除时间段格式无效')
            preserved_marks=bool(removals and intent.get('preserveFrames'))
            if intent.get('preserveFrames'):removals=[]
            if intent['visualCleanup']:
                progress(10,'正在自动检查穿模和明显画面异常')
                vision_data={'paths':[str(source) for source in sources],'text':text,'mode':_load('ai_scheduler').get_scheduler_status('vision')['mode'],
                    'modelId':request.get('modelId'),'detectionMode':detection['mode'],
                    'confidenceThreshold':detection['threshold'],'padding':detection['padding']}
                if 'sampleInterval' in request:vision_data['sampleInterval']=request['sampleInterval']
                analysis=recovery.get('analysis')
                if analysis is None:
                    vision=self._vision_work(vision_data)
                    analysis=vision(lambda percent,message='':progress(10+max(0,min(100,percent))*.3,message),control)
                    recovery.save('analysis',analysis)
                else:
                    analysis['analysisId']=''
                    analysis['recovered']=True
                    progress(39,'已恢复相同素材与模型配置的画面分析')
                bound();check_control(control)
                # The worker already applies the selected threshold and padding;
                # its accepted ranges remain bound to the review token and media.
                analysis=copy.deepcopy(analysis)
                analysis['allRanges']=copy.deepcopy(analysis['ranges'])
                analysis['automatic']=True
                spatial=_load('smart_vision').plan_spatial_repairs(analysis['ranges'],max_zoom=1.6)
                source_crops=copy.deepcopy(spatial['spatialRepairs'])
                analysis['spatialRepairs']=copy.deepcopy(spatial['spatialRepairs'])
                analysis['temporalFallbacks']=copy.deepcopy(spatial['temporalFallbacks'])
                temporal=[{'index':row['index'],'start':row['start'],'end':row['end']}
                    for row in analysis['temporalFallbacks']]
                boundaries={}
                for index in sorted({row['index'] for row in temporal}):
                    if infos[index].get('hasAudio'):
                        boundaries[index]=_load('media_quality').silence_boundaries(
                            self.api.ctx.ffmpeg_tool(),sources[index],infos[index]['duration'],control)
                temporal=_load('media_quality').align_removals(
                    temporal,boundaries,[row['duration'] for row in infos])
                analysis['alignedRemovals']=temporal
                removals.extend(temporal)
            bound();check_control(control)
            render_options={key:copy.deepcopy(request[key]) for key in ('speechLanguage','subtitleStyle','bgmTrack','effects','minDurationPolicy','transition','montageMode','shotDuration','fitMode','bgmDucking') if key in request}
            understood_options=copy.deepcopy(intent.get('options',{}))
            if 'subtitleStyle' in understood_options:
                subtitle_style=render_options.get('subtitleStyle',{})
                if not isinstance(subtitle_style,dict):raise BridgeError('SMART_AUTO_INPUT','字幕样式格式无效')
                if 'preset' in understood_options['subtitleStyle']:
                    for key in ('color','outline','shadow','bold'):subtitle_style.pop(key,None)
                render_options['subtitleStyle']={**subtitle_style,**understood_options.pop('subtitleStyle')}
            render_options.update(understood_options)
            if intent.get('preserveFrames'):render_options['montageMode']='sequential'
            # An understood built-in style must win over a stale custom file.
            bgm_path='' if 'bgmTrack' in understood_options else request.get('bgmPath','')
            operations=_load('edit_operations').validate_operations(intent.get('operations',[]),len(sources))
            ordered_sources,original_indices,ordered_removals=_load('edit_operations').prepare_sources(sources,infos,operations,removals)
            if source_crops:
                by_source={}
                for row in source_crops:
                    by_source.setdefault(row['index'],[]).append(copy.deepcopy(row))
                source_crops=[]
                for new_index,original_index in enumerate(original_indices):
                    for row in by_source.get(original_index,[]):
                        source_crops.append({**row,'index':new_index})
            changed_order=original_indices!=list(range(len(sources))) or ordered_removals!=removals
            planned=self.video_smartPlan({'paths':[str(source) for source in ordered_sources], 'text':intent['canonicalText'],
                'minDuration':request.get('minDuration',0),
                'spatialCrops':copy.deepcopy(source_crops),
                **intent['settings'],'removeRanges':ordered_removals,'analysisId':analysis['analysisId'] if analysis and not changed_order else '',
                'subtitles':intent['subtitles'],'bgmPath':bgm_path,
                **render_options})
            record=self._smart_plans[planned['planId']]
            record['workflow']=recovery
            record['validateExtra']=bound
            record['plan']['operations']=copy.deepcopy(operations)
            # The renderer resolves target/minimum duration, autospeed and
            # transitions before publishing the plan. Keep the nested settings
            # view in sync with those resolved top-level values instead of
            # restoring stale intent defaults such as duration=0.
            record['plan']['settings']={
                key:copy.deepcopy(record['plan'][key])
                for key in ('start','duration','minDuration','minSpeed','speed',
                    'ratio','resolution','keepAudio','bgm','bgmVolume')
                if key in record['plan']
            }
            record['plan']['spatialCrops']=copy.deepcopy(source_crops)
            for key,value in understood_options.items():
                if key in record['plan'].get('options',{}):
                    record['plan']['options'][key]=copy.deepcopy(value)
                else:
                    record['plan'][key]=copy.deepcopy(value)
            ledger=_load('requirement_ledger').RequirementLedger.build(
                {**record['plan'],'requirements':text})
            record['verifyDelivery']=lambda partial:self._verify_requirement_delivery(
                ledger,{**partial,'plan':{**record['plan'],'operations':operations},'analysis':analysis})
            for operation in operations:
                if operation['op']=='audioFade' and operation['target']=='music':
                    record['plan'].setdefault('musicFades',{}).update(operation['params'])
            record['plan']['requirements']=text
            record['plan']['recognized'].extend(name for name in ('旁白字幕' if intent['subtitles'] else '',
                '自动穿模裁剪/删减' if intent['visualCleanup'] else '') if name)
            if intent['subtitles']:record['plan']['notes'].append('从剪辑后的原始口播自动识别并烧录同步字幕，同时保存SRT文件。')
            if preserved_marks:record['plan']['notes'].append('按“保留画面”的明确需求，已忽略先前保存的删除时间标记。')
            if analysis:
                repaired=len(analysis.get('spatialRepairs',[]))
                removed=len(analysis.get('temporalFallbacks',[]))
                if repaired or removed:
                    record['plan']['notes'].append(
                        f'自动处理 {len(analysis["ranges"])} 个疑似画面异常：'
                        f'{repaired} 个只在异常时间段调整画面构图，'
                        f'{removed} 个无法安全裁掉时才删除对应时段；其余画面保持原样。')
                else:
                    record['plan']['notes'].append('画面分析未返回可执行的异常处理建议；成片可预览复核。')
                if 'visualCleanup' not in intent.get('specifiedFeatures',[]):
                    intent['summary'].append('按已开启的穿模检测选项检查画面，优先安全裁景，必要时删减片段')
            def completed_note(note):
                return note.replace('请预览复核后再确认删除','成片可预览复核').replace('请预览确认','成片可预览复核').replace('仍需预览确认','可在成片中复核')
            record['plan']['notes']=[completed_note(note) for note in record['plan']['notes']]
            if analysis:analysis['notes']=[completed_note(note) for note in analysis.get('notes',[])]
            bound();check_control(control)
            progress(40,'需求已理解，开始剪辑和导出')
            execution_progress=lambda percent,message='':progress(40+max(0,min(100,percent))*.59,message)
            visual_ops=[row for row in operations if row['op'] not in ('trim','removeRange','reorder','duplicate') and not (row['op']=='audioFade' and row['target']=='music')]
            if visual_ops:
                result=self._auto_composite_execute(record,visual_ops,original_indices,execution_progress,control,bound)
            else:
                result=self._smart_execute_record(record,execution_progress,control)
            # Render validates the captured context immediately before publishing.
            result.update(plan=copy.deepcopy(record['plan']),analysis=analysis,intent=intent,requirements=text)
            result['languageExecution']=_load('ai_scheduler').last_execution('language')
            result['requirementContract']=copy.deepcopy(requirement_contract)
            result['workflowId']=recovery.identifier
            if Path(result.get('path','')).is_file():
                try:
                    result['editProjectPath']=_load('editable_project').save(
                        record,result,operations,original_indices)
                except (ValueError,OSError) as error:
                    result['projectWarning']='成片已保留，精修工程保存失败：'+str(error)[:200]
            recovery.finish(result.get('path',''))
            return result

        def recoverable_work(progress,control):
            try:
                with _load('ai_scheduler').job_budget(request.get('maxApiCalls',100)):
                    result=work(progress,control)
                    if isinstance(result,dict):
                        result['apiUsage']=_load('ai_scheduler').budget_usage()
                    return result
            except BaseException as error:
                recovery.fail(getattr(error,'code','SMART_JOB_INTERRUPTED'))
                raise
            finally:
                recovery.release()
        recovery.claim()
        try:
            return self.api.tasks.start('按我的需求自动剪辑',recoverable_work,category='video',location={'route':'/editor/smart'})
        except BaseException:
            recovery.release()
            raise

    @staticmethod
    def _verify_requirement_delivery(ledger,result):
        try:
            return _load('requirement_ledger').verify(ledger,result)
        except ValueError as error:
            message=str(error)
            if message.startswith('SMART_REQUIREMENT_NOT_DELIVERED|'):
                message=message.split('|',1)[1]
            raise BridgeError('SMART_REQUIREMENT_NOT_DELIVERED',message) from error

    def _auto_composite_execute(self,record,operations,indices,progress,control,bound):
        """Render typed visuals before speech recognition and final music mixing."""
        smart=_load('smart_editing')
        self._smart_validate(record,verify_effect_content=True)
        temporary=Path(tempfile.mkdtemp(prefix='.aive-dialogue-',dir=record['directory']))
        ownership=smart._owned_directory(temporary,record['directory'])
        try:
            intermediate=temporary/'visuals.mp4'
            document=_load('edit_operations').build_document(record,operations,intermediate,indices)
            render,_=_load('timeline_compositor').make_work(self,document)
            def render_progress(value,message=''):
                self._smart_validate(record,verify_effect_content=True);check_control(control)
                progress(max(0,min(100,value))*.6,message)
                self._smart_validate(record,verify_effect_content=True)
            render(render_progress,control)
            self._smart_validate(record,verify_effect_content=True);check_control(control)
            plan=record['plan']
            # The compositor has already applied the resolved speed and final
            # duration. Reapplying the original minimum-duration policy here
            # would slow the finished clock a second time (for example, a
            # 2.93 s composite at 0.9x became 3.26 s after repacking).
            final=self.video_smartPlan({'paths':[str(intermediate)],'text':f'开始0秒，剪成{plan["duration"]:g}秒，1倍速',
                'start':0,'duration':plan['duration'],'minDuration':0,
                'minSpeed':.25,'minDurationPolicy':'available',
                'speed':1,'ratio':'自动','resolution':'原画','keepAudio':plan['keepAudio'],'bgm':plan['bgm'],'bgmVolume':plan['bgmVolume'],
                'bgmPath':str(record['bgmSource']) if record.get('bgmSource') else '',
                'subtitles':plan.get('subtitles',False),'speechLanguage':plan.get('speechLanguage','auto'),
                'subtitleStyle':plan.get('subtitleStyle',{}),'effects':[{k:v for k,v in item.items() if k not in ('name','kind')} for item in plan.get('effects',[])],'transition':{'type':'none','duration':0}})
            final_record=self._smart_plans[final['planId']]
            final_record['workflow']=record.get('workflow')
            final_record['validateExtra']=lambda:self._smart_validate(record,verify_effect_content=True)
            final_record['verifyDelivery']=record['verifyDelivery']
            final_record['plan']['requirements']=plan['requirements']
            final_record['plan']['operations']=copy.deepcopy(plan.get('operations',[]))
            final_record['plan']['musicFades']=plan.get('musicFades',{})
            final_record['plan']['bgmDucking']=plan.get('bgmDucking',False)
            return self._smart_execute_record(final_record,lambda value,message='':progress(60+max(0,min(100,value))*.4,message),control)
        finally:
            smart._cleanup_owned(temporary,ownership,record['directory'])
