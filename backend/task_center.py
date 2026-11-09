"""Persistent local finished-video index and cancellable, exclusive downloads."""
from datetime import datetime
from contextlib import contextmanager
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid

from app.ui2.common import BridgeError
from app.workers.control import check_control

VIDEO_EXTENSIONS={'.mp4','.mov','.mkv','.webm','.avi','.m4v'}
_BATCH_PLANS={}
_BATCH_PLAN_LOCK=threading.Lock()
_BATCH_PLAN_SECONDS=30*60

def _error(message):
    raise BridgeError('TASK_CENTER_ERROR',message)

def _local(value):
    if not isinstance(value,str) or not value or any(ord(c)<32 for c in value) or '://' in value or value.startswith(('\\\\','//')):
        _error('请选择有效的本机文件路径')
    path=Path(value)
    if not path.is_absolute():_error('请选择完整的本机文件路径')
    path=path.resolve()
    if str(path).startswith(('\\\\','//')):_error('请选择本机保存目录')
    return path

def _stamp(path):
    stat=path.stat()
    return [stat.st_size,stat.st_mtime_ns,stat.st_ino]

def _filename(filename,source):
    if (not isinstance(filename,str) or not filename.strip() or len(filename)>180 or
        re.search(r'[\x00-\x1f<>:"/\\|?*]',filename) or filename.endswith((' ','.')) or
        re.fullmatch(r'(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])',filename.split('.')[0].rstrip(' '),re.I)):
        _error('文件名无效，请使用普通文件名，不要包含路径或特殊符号')
    if Path(filename).suffix.lower()!=source.suffix.lower():_error('保存文件的扩展名需要与原成片一致')
    return filename

def _path_key(path):
    return os.path.normcase(str(path)).casefold()

def _move_exclusive(source,target):
    # os.rename is exclusive on Windows. link/unlink gives the same no-overwrite
    # guarantee for the regular local files used by tests on other platforms.
    if os.name=='nt':os.rename(source,target)
    else:
        os.link(source,target)
        try:source.unlink()
        except BaseException:
            target.unlink()
            raise

def _public_batch(plan):
    value={'planId':plan['planId'],'kind':plan['kind'],'count':len(plan['items']),
           'totalBytes':sum(item['stamp'][0] for item in plan['items']),
           'items':[{key:item[key] for key in ('id','oldName','newName','path')} for item in plan['items']]}
    if plan['kind']=='download':value['folder']=plan['folder']
    return value

class TaskHistory:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS outputs (id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=15)
        try:
            with db:yield db
        finally:db.close()

    def contains(self,path):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM outputs WHERE path=?',(str(Path(path).resolve()),)).fetchone() is not None

    def record(self,name,result,project='',created=None):
        if not isinstance(result,dict):return None
        value=result.get('path') or result.get('output_path')
        if not isinstance(value,str) or Path(value).suffix.lower() not in VIDEO_EXTENSIONS:return None
        path=_local(value)
        if not path.is_file():return None
        duration=result.get('duration',0)
        if type(duration) not in (float,int) or not math.isfinite(duration) or duration<0:duration=0
        payload={'name':str(name)[:150],'path':str(path),'filename':path.name,'project':str(project)[:200],
                 'duration':duration,'requirements':str(result.get('requirements',''))[:4000],'stamp':_stamp(path)}
        execution = {}
        candidates = dict(result['aiExecution']) if isinstance(result.get('aiExecution'), dict) else {}
        analysis = result.get('analysis') if isinstance(result.get('analysis'), dict) else {}
        candidates.update(language=result.get('languageExecution') or candidates.get('language'),
                          vision=analysis.get('execution') or candidates.get('vision'))
        for kind in ('language', 'vision'):
            row = candidates.get(kind)
            if not isinstance(row, dict) or row.get('executedProvider') not in ('api', 'local'):
                continue
            execution[kind] = {key: str(row.get(key, ''))[:200]
                              for key in ('executedProvider', 'connectionName', 'model', 'failureCode')}
            execution[kind]['localFallbackUsed'] = row.get('localFallbackUsed') is True
        if execution:
            payload['aiExecution'] = execution
        for key in ('requirementReport','qualityReport','apiUsage','editProjectPath','workflowId','projectWarning'):
            if key in result:
                payload[key]=result[key]
        identifier=uuid.uuid4().hex
        timestamp=created or datetime.now().isoformat(timespec='seconds')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id,payload FROM outputs WHERE path=?',(str(path),)).fetchone()
            if row and json.loads(row[1]).get('stamp')==payload['stamp']:
                return row[0]
            if row:
                # A fresh successful generation may reuse a removed output's
                # path. Give it a new identity so stale cards never download a
                # different video's bytes through the previous task's id.
                db.execute('UPDATE outputs SET id=?,created=?,payload=? WHERE path=?',
                           (identifier,timestamp,json.dumps(payload,ensure_ascii=False),str(path)))
            else:
                db.execute('INSERT INTO outputs VALUES (?,?,?,?)',
                           (identifier,str(path),timestamp,json.dumps(payload,ensure_ascii=False)))
        return identifier

    def list(self,limit=50,offset=0,search=''):
        # Search is literal text, never a SQL expression or LIKE wildcard.
        with self.connect() as db:
            rows=db.execute('SELECT id,created,payload FROM outputs WHERE instr(lower(payload),lower(?))>0 ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',
                            (search,limit,offset)).fetchall()
        items=[]
        for identifier,created,payload in rows:
            item=json.loads(payload);stamp=item.pop('stamp',None)
            try:available=Path(item['path']).is_file() and _stamp(Path(item['path']))==stamp
            except OSError:available=False
            items.append({**item,'id':identifier,'created_at':created,'available':available})
        return items

    def count(self,search=''):
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM outputs WHERE instr(lower(payload),lower(?))>0',(search,)).fetchone()[0]

    def get(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):_error('任务记录无效，请刷新任务中心')
        with self.connect() as db:
            row=db.execute('SELECT payload FROM outputs WHERE id=?',(identifier,)).fetchone()
        if not row:_error('任务记录不存在，请刷新任务中心')
        return json.loads(row[0])

    def download(self,identifier,folder,filename,progress,control,*,expected=None,on_published=None):
        check_control(control)
        item=self.get(identifier);source=_local(item['path']);directory=_local(folder)
        if not directory.is_dir():_error('保存目录不存在，请重新选择')
        _filename(filename,source)
        if expected is not None and (str(source)!=expected['source'] or item.get('stamp')!=expected['stamp']):
            _error('批量预览已失效，原成片记录发生变化，请重新预览')
        target=directory/filename
        if os.path.lexists(target):_error('目标文件已存在，请修改文件名；原文件不会被覆盖')
        try:
            if _stamp(source)!=item['stamp']:_error('原成片已发生变化，请重新生成或核对文件')
        except OSError:_error('原成片已移动或删除，无法下载，请检查原保存位置')
        identity=_stamp(directory)[2]
        temporary=None
        try:
            fd,temp=tempfile.mkstemp(prefix='.aive-download-',suffix='.partial',dir=directory)
            temporary=Path(temp)
            with os.fdopen(fd,'wb') as output,source.open('rb') as input_file:
                copied=0;size=item['stamp'][0]
                while True:
                    check_control(control)
                    block=input_file.read(4*1024*1024)
                    if not block:break
                    output.write(block);copied+=len(block)
                    progress(min(95,int(copied/max(1,size)*95)),'正在保存成片')
                output.flush();os.fsync(output.fileno())
            check_control(control)
            if _stamp(source)!=item['stamp'] or copied!=size:_error('复制期间原成片发生变化，请重试')
            if not directory.is_dir() or _stamp(directory)[2]!=identity:_error('保存目录已变化，请重新选择')
            published_stamp=_stamp(temporary)
            _move_exclusive(temporary,target)
            temporary=None
            # Register ownership before progress can observe cancellation. A batch
            # must also roll back a copy published immediately before cancellation.
            if on_published is not None:on_published(target,published_stamp)
            progress(100,'成片已保存')
            return {'path':str(target),'bytes':copied}
        except FileExistsError:_error('目标文件已存在，请修改文件名')
        except OSError:_error('保存失败，请检查磁盘空间和目录权限')
        finally:
            if temporary is not None:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass

    def plan_batch(self,data):
        if not isinstance(data,dict):_error('批量操作参数无效')
        kind=data.get('kind');identifiers=data.get('ids');naming=data.get('naming')
        if kind not in ('download','rename'):_error('请选择批量下载或批量改名')
        if (not isinstance(identifiers,list) or not 1<=len(identifiers)<=200 or
            any(not isinstance(value,str) for value in identifiers) or len(set(identifiers))!=len(identifiers)):
            _error('请选择 1 至 200 条不同的成片记录')
        if naming is not None:
            if (not isinstance(naming,dict) or not isinstance(naming.get('prefix'),str) or
                type(naming.get('start')) is not int or not 0<=naming['start']<=999999999 or
                type(naming.get('digits')) is not int or not 1<=naming['digits']<=6):
                _error('命名规则无效：前缀需为文字，起始编号为非负整数，位数为 1 至 6')
        elif kind=='rename':_error('批量改名需要设置命名规则')
        plan={'planId':uuid.uuid4().hex,'kind':kind,'items':[],
              'database':str(self.path.resolve()),'expires':time.monotonic()+_BATCH_PLAN_SECONDS}
        if kind=='download':
            folder=_local(data.get('folder'))
            if not folder.is_dir():_error('保存目录不存在，请重新选择')
            plan['folder']=str(folder);plan['folderIdentity']=_stamp(folder)[2]
        used=set()
        for index,identifier in enumerate(identifiers):
            item=self.get(identifier);source=_local(item['path'])
            try:
                if not source.is_file() or _stamp(source)!=item.get('stamp'):
                    _error('所选成片已发生变化或不可用，请刷新任务中心')
            except OSError:_error('所选成片已移动或删除，请刷新任务中心')
            directory=folder if kind=='download' else source.parent
            if naming is not None:
                filename=f"{naming['prefix']}{naming['start']+index:0{naming['digits']}d}{source.suffix}"
            else:
                filename=source.name;number=2
                while _path_key(directory/filename) in used:
                    filename=f'{source.stem} ({number}){source.suffix}';number+=1
            _filename(filename,source)
            target=directory/filename;key=_path_key(target)
            if key in used:_error('命名规则生成了重复的目标文件名，请调整规则')
            used.add(key)
            plan['items'].append({'id':identifier,'source':str(source),'stamp':list(item['stamp']),
                                  'directoryIdentity':_stamp(source.parent)[2],
                                  'oldName':source.name,'newName':filename,'path':str(target)})
        self._validate_batch(plan)
        with _BATCH_PLAN_LOCK:
            now=time.monotonic()
            for key in list(_BATCH_PLANS):
                if _BATCH_PLANS[key]['expires']<now:_BATCH_PLANS.pop(key,None)
            if len(_BATCH_PLANS)>=100:_BATCH_PLANS.pop(next(iter(_BATCH_PLANS)))
            _BATCH_PLANS[plan['planId']]=plan
        return _public_batch(plan)

    def take_batch(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):
            _error('批量预览无效，请重新预览')
        with _BATCH_PLAN_LOCK:
            plan=_BATCH_PLANS.get(identifier)
            if not plan or plan['database']!=str(self.path.resolve()) or plan['expires']<time.monotonic():
                _error('批量预览已失效，请重新预览')
            return _BATCH_PLANS.pop(identifier)

    def _validate_batch(self,plan,db=None):
        if db is None:
            with self.connect() as connection:return self._validate_batch(plan,connection)
        if plan['kind']=='download':
            folder=Path(plan['folder'])
            try:
                if _local(str(folder))!=folder or not folder.is_dir() or _stamp(folder)[2]!=plan['folderIdentity']:
                    _error('保存目录已变化，请重新选择并预览')
            except OSError:_error('保存目录已变化，请重新选择并预览')
        # The path column has a UNIQUE constraint; reject even an unavailable
        # record's claimed path rather than overwriting another record's identity.
        claimed={_path_key(Path(path)):identifier for identifier,path in db.execute('SELECT id,path FROM outputs')} if plan['kind']=='rename' else {}
        for item in plan['items']:
            row=db.execute('SELECT path,payload FROM outputs WHERE id=?',(item['id'],)).fetchone()
            if not row or row[0]!=item['source'] or json.loads(row[1]).get('stamp')!=item['stamp']:
                _error('批量预览已失效，成片记录发生变化，请重新预览')
            source=Path(item['source']);target=Path(item['path'])
            try:
                if (_local(str(source))!=source or not source.is_file() or _stamp(source)!=item['stamp'] or
                    _stamp(source.parent)[2]!=item['directoryIdentity']):
                    _error('批量预览已失效，原成片发生变化，请重新预览')
            except OSError:_error('原成片已移动或删除，请重新预览')
            noop=plan['kind']=='rename' and source==target
            if not noop and os.path.lexists(target):_error(f'目标文件已存在：{target.name}，请修改命名或保存目录')
            if claimed.get(_path_key(target),item['id'])!=item['id']:_error(f'目标文件名已存在于其他成片记录：{target.name}')

    def execute_batch(self,identifier,progress,control):
        return self.run_batch(self.take_batch(identifier),progress,control)

    def run_batch(self,plan,progress,control):
        check_control(control)
        if plan['kind']=='rename':return self._rename_batch(plan,progress,control)
        self._validate_batch(plan)
        owned=[];completed=0;total=max(1,sum(item['stamp'][0] for item in plan['items']))
        def published(path,stamp):owned.append((path,stamp))
        try:
            for index,item in enumerate(plan['items']):
                check_control(control)
                def update(percent,message):
                    value=min(99,int((completed+item['stamp'][0]*percent/100)/total*99))
                    progress(value,f'正在下载 {index+1}/{len(plan["items"])}：{item["newName"]}')
                self.download(item['id'],plan['folder'],item['newName'],update,control,expected=item,on_published=published)
                completed+=item['stamp'][0]
            # Sources and records may have changed while a previous copy ran.
            # Validate their identity without treating our published copies as conflicts.
            for item in plan['items']:
                current=self.get(item['id'])
                if current.get('path')!=item['source'] or current.get('stamp')!=item['stamp'] or _stamp(Path(item['source']))!=item['stamp']:
                    _error('下载期间原成片发生变化，请重新预览')
            check_control(control);progress(100,'批量下载完成');check_control(control)
            return self._batch_result(plan)
        except BaseException:
            retained=[]
            for path,stamp in reversed(owned):
                try:
                    if path.is_file() and _stamp(path)==stamp:path.unlink()
                    elif os.path.lexists(path):retained.append(str(path))
                except OSError:retained.append(str(path))
            if retained:_error('批量下载未完成，部分目标文件已变化或无法清理，请核对：'+'；'.join(retained))
            raise

    def _batch_result(self,plan):
        result=_public_batch(plan);result.pop('planId')
        for output,item in zip(result['items'],plan['items']):output['bytes']=item['stamp'][0]
        return result

    def _rename_batch(self,plan,progress,control):
        moved=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('SAVEPOINT batch_records')
            self._validate_batch(plan,db)
            originals={item['id']:json.loads(db.execute('SELECT payload FROM outputs WHERE id=?',(item['id'],)).fetchone()[0]) for item in plan['items']}
            try:
                for index,item in enumerate(plan['items']):
                    check_control(control)
                    source=Path(item['source']);target=Path(item['path'])
                    if (_stamp(source)!=item['stamp'] or _stamp(source.parent)[2]!=item['directoryIdentity'] or
                        _local(str(source))!=source):_error('改名期间原成片发生变化，请重新预览')
                    if str(source)!=str(target):
                        try:_move_exclusive(source,target)
                        except FileExistsError:_error(f'目标文件已存在：{target.name}，改名已撤回')
                        moved.append(item)
                    progress(min(99,int((index+1)/len(plan['items'])*99)),f'正在改名 {index+1}/{len(plan["items"])}：{item["newName"]}')
                check_control(control)
                for item in plan['items']:
                    target=Path(item['path'])
                    if _stamp(target)!=item['stamp'] or _stamp(target.parent)[2]!=item['directoryIdentity']:
                        _error('改名期间成片发生变化，操作已撤回')
                    payload={**originals[item['id']],'path':str(target),'filename':target.name,'stamp':_stamp(target)}
                    db.execute('UPDATE outputs SET path=?,payload=? WHERE id=?',
                               (str(target),json.dumps(payload,ensure_ascii=False),item['id']))
                progress(100,'批量改名完成');check_control(control)
                db.commit()
                return self._batch_result(plan)
            except BaseException:
                retained=[]
                for item in reversed(moved):
                    source=Path(item['source']);target=Path(item['path'])
                    try:
                        # Windows case-only renames refer to the same existing
                        # file at both spellings and can be safely reversed.
                        old_name_taken=os.path.lexists(source) and source!=target
                        if not target.is_file() or _stamp(target)!=item['stamp'] or old_name_taken:
                            retained.append(item);continue
                        _move_exclusive(target,source)
                    except OSError:retained.append(item)
                if retained:
                    # Keep records pointing at originals we could not restore.
                    # The transaction still holds the writer lock during repair.
                    try:
                        db.execute('ROLLBACK TO batch_records')
                        for item in retained:
                            target=Path(item['path'])
                            if target.is_file() and _stamp(target)==item['stamp']:
                                payload={**originals[item['id']],'path':str(target),'filename':target.name,'stamp':_stamp(target)}
                                db.execute('UPDATE outputs SET path=?,payload=? WHERE id=?',
                                           (str(target),json.dumps(payload,ensure_ascii=False),item['id']))
                        db.commit()
                    except (OSError,sqlite3.Error):
                        logging.getLogger(__name__).warning('Batch rename rollback could not repair all finished-video records')
                    _error('批量改名未完成，部分文件无法恢复，请核对原位置与以下位置：'+'；'.join(item['path'] for item in retained))
                raise

def _data_root():
    configured = os.environ.get('AIVE_DATA_DIR')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            _error('顾客数据目录必须是完整路径')
        return path.resolve()
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return Path(local).resolve() / 'YangyuTech' / 'AutoEdit'
    return Path.home() / 'AppData' / 'Local' / 'YangyuTech' / 'AutoEdit'


def _history():
    database = _data_root() / 'task_center' / 'history.sqlite3'
    history = TaskHistory(database)
    legacy = Path(__file__).with_name('runtime') / 'task_center' / 'history.sqlite3'
    if not legacy.is_file() or legacy.resolve() == database.resolve():
        return history
    # Older builds stored customer history beside the program. Import every
    # surviving record once so updates do not make prior finished videos vanish.
    try:
        previous = TaskHistory(legacy)
        with previous.connect() as source:
            rows = source.execute('SELECT created, payload FROM outputs ORDER BY created, id').fetchall()
        for created, payload in rows:
            item = json.loads(payload)
            path = item.get('path')
            if isinstance(path, str) and Path(path).is_file():
                history.record(item.get('name', '历史成片'), item,
                               project=item.get('project', ''), created=created)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        logging.getLogger(__name__).warning('Legacy task history migration could not be completed')
    return history

def _project_directory(api):
    # The frozen context's project_dir property raises when no project is open.
    if getattr(api.ctx,'project_id',None) is None:return None
    return getattr(api.ctx,'project_dir',None)

def install(api):
    tasks=api.tasks
    if getattr(tasks,'_finished_video_history',False) or not callable(getattr(tasks,'list',None)):return
    original=tasks.start
    def start(name,work,category='other',location=None):
        project=str(_project_directory(api) or '')
        def wrapped(progress,control):
            result=work(progress,control)
            if category not in ('download','taskRename','update') and isinstance(result,dict):
                try:
                    identifier=_history().record(name,result,project=Path(project).name if project else '')
                    if identifier:result['archiveId']=identifier
                except (OSError,sqlite3.Error,BridgeError):
                    logging.getLogger(__name__).warning('Finished video index could not be saved; original output retained')
                    result['taskCenterWarning']='成片已生成，但任务记录保存失败；请先打开成片位置保存文件。'
            return result
        return original(name,wrapped,category=category,location=location)
    tasks.start=start;tasks._finished_video_history=True

class TaskCenterMixin:
    def video_getTaskProject(self,data):
        history=_history()
        if data.get('id'):
            row=history.get(data['id'])
        else:
            path=str(_local(data.get('path')))
            with history.connect() as db:
                found=db.execute('SELECT payload FROM outputs WHERE path=?',(path,)).fetchone()
            if not found:_error('请先在任务中心找到已生成的成片')
            row=json.loads(found[0])
        output=_local(row['path'])
        if not output.is_file() or row.get('stamp')!=_stamp(output):
            _error('成片已变化，请刷新任务中心')
        project=output.parent/'editable-project.json'
        if project.is_symlink() or project.resolve().parent!=output.parent or not project.is_file():
            _error('此任务没有可编辑工程；请用新版重新生成')
        if project.stat().st_size>5*1024**2:_error('精修工程超过可读取大小')
        value=json.loads(project.read_text('utf8'))
        if value.get('schema')!=1 or value.get('referenceOutput')!=str(output):
            _error('精修工程与当前成片不匹配')
        for path,size,modified in value.get('sourceStamps',[]):
            source=_local(path)
            if not source.is_file() or (source.stat().st_size,source.stat().st_mtime_ns)!=(size,modified):
                _error('原始素材已移动或变化，请恢复素材后继续精修')
        return value

    def video_getTaskHistory(self,data):
        history=_history()
        # Recover finished tasks from this process and older committed smart edits.
        tasks=getattr(self.api.tasks,'list',None)
        for task in tasks() if callable(tasks) else []:
            if task.get('status')=='done' and task.get('category')!='download':
                result=task.get('result')
                if isinstance(result,dict) and result.get('path') and (not history.contains(result['path']) or result.get('taskCenterWarning')):
                    history.record(task.get('name','视频生成'),result)
        project=_project_directory(self.api)
        recovered=getattr(self,'_recovered_task_projects',set())
        if project and str(project) not in recovered:
            root=Path(project).resolve()
            for path in (root/'smart_edits').glob('*/result.mp4'):
                if not path.resolve().is_relative_to(root) or history.contains(path):continue
                try:
                    info=self._smart_helpers['_probe'](self.api.ctx.ffmpeg_tool(),path)
                    history.record('智能剪辑成片',info,project=root.name,created=datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'))
                except (OSError,BridgeError):continue
            recovered.add(str(project));self._recovered_task_projects=recovered
        page=data.get('page',1);size=data.get('pageSize',30);search=data.get('search','')
        if type(page) is not int or not 1<=page<=100000 or type(size) is not int or not 1<=size<=100 or not isinstance(search,str) or len(search)>200:_error('任务查询参数无效')
        return {'items':history.list(size,(page-1)*size,search),'total':history.count(search)}

    def video_downloadTask(self,data):
        history=_history();identifier=data.get('id');history.get(identifier)
        folder,filename=data.get('folder'),data.get('filename')
        def work(progress,control):return history.download(identifier,folder,filename,progress,control)
        return self.api.tasks.start('下载成片',work,category='download',location={'route':'/tasks'})

    def video_planTaskBatch(self,data):
        return _history().plan_batch(data)

    def video_executeTaskBatch(self,data):
        if not isinstance(data,dict):_error('批量操作参数无效')
        history=_history();plan=history.take_batch(data.get('planId'))
        history._validate_batch(plan)
        def work(progress,control):return history.run_batch(plan,progress,control)
        return self.api.tasks.start('批量下载成片' if plan['kind']=='download' else '批量修改成片文件名',work,
                                    category='download' if plan['kind']=='download' else 'taskRename',location={'route':'/tasks'})
