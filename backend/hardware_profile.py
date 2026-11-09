"""Local, bounded hardware probes and heuristic model recommendations.

No download, network request, administrator access or persistent hardware ID is
needed. Missing measurements remain unknown rather than becoming capacity.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

_GIB = 1024 ** 3
_SPEECH_MODEL_BYTES = 486212372
_MIB = 1024 ** 2
_ROOT = Path(__file__).resolve().parent / 'runtime' / 'local_vision'
_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
_ESTIMATE_NOTICE = ('以下是保守经验估算，并非实测性能或运行保证；量化、视觉投影器、上下文、'
                    '输入帧数和其他程序都会影响占用。下载前仍须核对模型文件与配套 mmproj。')
# Existing vision_catalog.py catalogue entries; sizes include its suggested pair.
# RAM/VRAM budgets below are application heuristics, not published model specs.
_VISION = (
    {'repoId': 'ggml-org/Qwen3-VL-2B-Instruct-GGUF', 'name': 'Qwen3-VL 2B',
     'quantization': 'Q8_0', 'size': 2279480352, 'minRam': 8, 'workingRam': 4.5, 'vram': 5},
    {'repoId': 'ggml-org/Qwen2.5-VL-3B-Instruct-GGUF', 'name': 'Qwen2.5-VL 3B',
     'quantization': 'Q4 优先（以仓库文件为准）', 'size': 2774658784, 'minRam': 12, 'workingRam': 6, 'vram': 6},
    {'repoId': 'ggml-org/gemma-3-4b-it-GGUF', 'name': 'Gemma 3 4B',
     'quantization': 'Q4 优先（以仓库文件为准）', 'size': 3341008960, 'minRam': 16, 'workingRam': 8.5, 'vram': 8},
    {'repoId': 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'name': 'SmolVLM2 500M',
     'quantization': '选择仓库内可配对的 GGUF', 'size': 545593888, 'minRam': 4, 'workingRam': 1.75, 'vram': 2},
)

_CIM_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
$physicalMemory=@(Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity)
$os=Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
$gpus=@(Get-CimInstance Win32_VideoController | Select-Object Name)
$registryGpus=@(Get-ChildItem -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Video' | ForEach-Object {
  $key=Get-ItemProperty -LiteralPath (Join-Path $_.PSPath '0000')
  $bytes=$key.'HardwareInformation.qwMemorySize'
  if($bytes -is [byte[]] -and $bytes.Length -eq 8){$bytes=[BitConverter]::ToUInt64($bytes,0)}
  $name=$key.DriverDesc
  if($name -and ($bytes -is [uint64] -or $bytes -is [int64]) -and $bytes -gt 0){
    [pscustomobject]@{name=[string]$name;dedicatedBytes=$bytes}
  }
})
[pscustomobject]@{cpu=$cpu;physicalMemory=$physicalMemory;os=$os;gpus=$gpus;registryGpus=$registryGpus} | ConvertTo-Json -Compress -Depth 5
"""


def _number(value, maximum=1024 ** 5, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = float(value)
        if not math.isfinite(parsed) or parsed < (0 if zero else 1) or parsed > maximum:
            return None
        return int(parsed)
    except (ValueError, OverflowError):
        return None


def _text(value, limit=160):
    if not isinstance(value, str):
        return ''
    return ''.join(char for char in value if ord(char) >= 32 and ord(char) != 127).strip()[:limit]


def _rows(value):
    return [value] if isinstance(value, dict) else [row for row in value[:32] if isinstance(row, dict)] if isinstance(value, list) else []


def _vendor(name):
    lowered = name.casefold()
    if 'nvidia' in lowered:
        return 'NVIDIA'
    if any(word in lowered for word in ('amd', 'radeon', 'advanced micro')):
        return 'AMD'
    if 'intel' in lowered:
        return 'Intel'
    return 'unknown'


def normalize_hardware(raw, *, nvidia_csv=''):
    """Normalize allowlisted values only; AdapterRAM/shared memory are ignored."""
    raw = raw if isinstance(raw, dict) else {}
    cpu_rows = _rows(raw.get('cpu'))
    names = list(dict.fromkeys(_text(row.get('Name') or row.get('name')) for row in cpu_rows))
    def cores(normalized, cim):
        values = [_number(row.get(normalized, row.get(cim)), 4096) for row in cpu_rows]
        return min(sum(values), 4096) if values and all(value is not None for value in values) else None
    ram = raw.get('ram') if isinstance(raw.get('ram'), dict) else {}
    operating = raw.get('os') if isinstance(raw.get('os'), dict) else {}
    total = _number(ram.get('totalBytes'))
    available = _number(ram.get('availableBytes'), zero=True)
    dimms = [_number(row.get('Capacity')) for row in _rows(raw.get('physicalMemory'))]
    if total is None and dimms and all(size is not None for size in dimms):
        total = _number(sum(dimms))
    if total is None and (size := _number(operating.get('TotalVisibleMemorySize'))):
        total = _number(size * 1024)
    if available is None and (size := _number(operating.get('FreePhysicalMemory'), zero=True)) is not None:
        available = _number(size * 1024, zero=True)
    if total is not None and available is not None:
        available = min(available, total)
    gpus = []
    registry = _rows(raw.get('registryGpus'))
    for row in _rows(raw.get('gpus')):
        name = _text(row.get('name') or row.get('Name'))
        if not name:
            continue
        memory = _number(row.get('dedicatedBytes'), 1024 ** 4)
        source = _text(row.get('source'), 40) if memory is not None else 'unknown'
        if memory is None:
            matches = {_number(entry.get('dedicatedBytes'), 1024 ** 4) for entry in registry
                       if _text(entry.get('name')).casefold() == name.casefold()}
            matches.discard(None)
            if len(matches) == 1:
                memory, source = matches.pop(), 'registry-qwMemorySize'
        gpus.append({'name': name, 'vendor': _vendor(name), 'dedicatedBytes': memory,
                     'source': source or 'local', 'accelerator': 'unverified'})
    if isinstance(nvidia_csv, str) and len(nvidia_csv) <= 16384:
        used = set()
        for row in list(csv.reader(io.StringIO(nvidia_csv)))[:16]:
            if len(row) != 2:
                continue
            name, memory_mib = _text(row[0]), _number(row[1].strip(), 1024 ** 2)
            if not name or memory_mib is None:
                continue
            index = next((index for index, gpu in enumerate(gpus) if index not in used
                          and gpu['name'].casefold() == name.casefold()), None)
            if index is None:
                index = len(gpus)
                gpus.append({'name': name, 'vendor': 'NVIDIA', 'accelerator': 'unverified'})
            used.add(index)
            gpus[index].update(dedicatedBytes=memory_mib * _MIB, source='nvidia-smi')
    disk = raw.get('disk') if isinstance(raw.get('disk'), dict) else {}
    previous = raw.get('detection') if isinstance(raw.get('detection'), dict) else {}
    warnings = [_text(warning, 240) for warning in previous.get('warnings', [])[:16]
                if isinstance(warning, str)] if isinstance(previous.get('warnings'), list) else []
    if total is None:
        warnings.append('未读取到物理内存容量，无法确认本地模型适配。')
    if available is None:
        warnings.append('未读取到当前可用内存，请关闭其他程序后重新检测。')
    free = _number(disk.get('freeBytes'), zero=True)
    if free is None:
        warnings.append('模型存储盘可用空间未知，下载前请确认磁盘空间。')
    if not gpus or any(gpu['dedicatedBytes'] is None for gpu in gpus):
        warnings.append('部分显卡或独立显存未知；共享内存不计入独立显存，保留 CPU 运行建议。')
    warnings = list(dict.fromkeys(warnings))
    return {'cpu': {'name': ' / '.join(name for name in names if name)[:240] or None,
                    'physicalCores': cores('physicalCores', 'NumberOfCores'),
                    'logicalCores': cores('logicalCores', 'NumberOfLogicalProcessors')},
            'ram': {'totalBytes': total, 'availableBytes': available}, 'gpus': gpus,
            'disk': {'freeBytes': free, 'totalBytes': _number(disk.get('totalBytes')), 'scope': 'model-storage'},
            'platform': _text(raw.get('platform')) or platform.system(),
            'detection': {'status': 'partial' if warnings else 'complete', 'warnings': warnings}}


def _powershell_path():
    root = os.environ.get('SystemRoot', r'C:\Windows')
    candidate = Path(root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return str(candidate) if candidate.is_file() else shutil.which('powershell.exe')


def _nvidia_smi_path():
    candidates = (Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/nvidia-smi.exe',
                  Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'NVIDIA Corporation/NVSMI/nvidia-smi.exe')
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which('nvidia-smi')


def _probe(args, timeout):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=timeout, shell=False, creationflags=_FLAGS)
    if result.returncode or len(result.stdout) > 128 * 1024:
        raise ValueError('hardware probe unavailable')
    return result.stdout.decode('utf-8-sig', 'replace')


def detect_hardware():
    """Probe the model-storage volume and local Windows hardware without IDs."""
    raw, probe_warnings, nvidia = {'platform': platform.system()}, [], ''
    command = _powershell_path() if os.name == 'nt' else None
    if command:
        try:
            data = json.loads(_probe([command, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', _CIM_SCRIPT], 8))
            if isinstance(data, dict):
                raw.update(data)
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            probe_warnings.append('Windows 硬件查询超时或不可用，已保留能够读取的项目。')
    else:
        probe_warnings.append('当前系统未提供 Windows 本地硬件查询，部分参数未知。')
    if smi := _nvidia_smi_path():
        try:
            nvidia = _probe([smi, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], 4)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            probe_warnings.append('NVIDIA 显存查询不可用，未将共享内存用作显存。')
    # Existing ancestor only; detection never creates a folder or accepts a path
    # from the bridge. Both local model stores live on this application volume.
    folder = _ROOT
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    try:
        total, _, free = shutil.disk_usage(folder)
        raw['disk'] = {'totalBytes': total, 'freeBytes': free}
    except OSError:
        probe_warnings.append('模型存储盘空间无法读取。')
    result = normalize_hardware(raw, nvidia_csv=nvidia)
    result['detection']['warnings'] += probe_warnings
    if probe_warnings:
        result['detection']['status'] = 'partial'
    return result


def _fit(profile, min_ram, working_ram, disk_needed):
    total = profile['ram']['totalBytes']
    available = profile['ram']['availableBytes']
    free = profile['disk']['freeBytes']
    warnings = []
    insufficient = False
    if total is not None and total < min_ram:
        insufficient = True
        warnings.append('物理内存不足，建议至少 %.0f GiB。' % (min_ram / _GIB))
    if available is not None and available < working_ram + .5 * _GIB:
        insufficient = True
        warnings.append('当前可用内存不足；关闭其他程序后重新检测，避免与语音模型同时加载。')
    if disk_needed and free is not None and free < disk_needed:
        insufficient = True
        warnings.append('模型存储盘可用磁盘空间不足，请先释放空间。')
    if insufficient:
        return 'insufficient', warnings
    if total is None or available is None or (disk_needed and free is None):
        warnings.append('关键硬件容量未知，暂时无法确认适配。')
        return 'unknown', warnings
    return 'recommended', warnings


def recommend_models(profile, installed_models=(), *, speech_installed=False,
                     speech_partial_bytes=0):
    """Use single-adapter VRAM and current free RAM; never sum GPU memories."""
    profile = normalize_hardware(profile)
    installed = _rows(installed_models) if isinstance(installed_models, list) else []
    max_vram = max((gpu['dedicatedBytes'] or 0 for gpu in profile['gpus']
                    if gpu['vendor'] in ('NVIDIA', 'AMD', 'Intel')), default=0)
    vision = []
    for entry in _VISION:
        matches = [row for row in installed if _number(row.get('size')) and
                   (row.get('repoId') == entry['repoId'] or
                    (not row.get('repoId') and row.get('id') == 'qwen3-vl-2b-q8' and
                     entry['repoId'] == 'ggml-org/Qwen3-VL-2B-Instruct-GGUF' and
                     row.get('sourceUrl') == 'https://huggingface.co/' + entry['repoId']))]
        existing = min(matches, key=lambda row: row['size']) if matches else None
        size = existing['size'] if existing else entry['size']
        ram = max(int(entry['workingRam'] * _GIB), math.ceil(size * 1.6 + _GIB))
        vram = max(int(entry['vram'] * _GIB), math.ceil(size * 1.5 + _GIB))
        disk = 0 if existing else math.ceil(size * 1.15 + _GIB)
        fit, warnings = _fit(profile, entry['minRam'] * _GIB, ram, disk)
        accelerated = max_vram >= vram
        execution = 'vulkan-candidate' if accelerated else 'cpu'
        if accelerated:
            warnings.append('显存容量可尝试 Vulkan 加速；驱动、引擎支持和实际速度需加载模型后验证。')
        else:
            warnings.append('单张显卡独立显存不足或未知，建议 CPU 运行；视频分析可能较慢。')
        if entry['repoId'].endswith('gemma-3-4b-it-GGUF'):
            warnings.append('Gemma 为开放权重模型，下载前请阅读其专用许可证。')
        if entry['repoId'].endswith('SmolVLM2-500M-Video-Instruct-GGUF'):
            warnings.append('轻量模型对细微穿模和异常画面的判断能力有限，请复核剪辑建议。')
        quantization = entry['quantization']
        if existing:
            found = re.search(r'(?i)(Q\d(?:_[A-Z0-9]+)*)', str(existing.get('modelSourceFile', '')))
            quantization = found.group(1).upper() if found else '已安装文件的量化版本'
        if fit == 'insufficient':
            reason = '当前容量不足，请查看内存与磁盘提示后重新检测。'
        elif fit == 'unknown':
            reason = '关键容量未知，暂时无法确认适配。'
        else:
            reason = '容量符合经验预算，可尝试 Vulkan 加速。' if accelerated else '容量符合经验预算，可先尝试 CPU 运行。'
        vision.append({'repoId': entry['repoId'], 'name': entry['name'],
                       'quantization': quantization, 'fit': fit,
                       'reason': ('已安装；' if existing else '') + reason,
                       'execution': execution, 'estimatedDownloadBytes': 0 if existing else size,
                       'estimatedRamBytes': ram, 'minimumTotalRamBytes': entry['minRam'] * _GIB,
                       'estimatedVramBytes': vram, 'estimatedDiskBytes': disk,
                       'installed': bool(existing), 'installedModelId': existing.get('id') if existing else None,
                       'sourceUrl': 'https://huggingface.co/' + entry['repoId'], 'warnings': warnings})
    preferred = next((row for row in vision if row['fit'] == 'recommended'), None)
    # Match the existing CPU int8 speech loader; no unsupported model selector.
    speech_size = _SPEECH_MODEL_BYTES
    if type(speech_partial_bytes) is not int or not 0 <= speech_partial_bytes <= speech_size:
        speech_partial_bytes = 0
    remaining = 0 if speech_installed else speech_size - speech_partial_bytes
    speech_disk = 0 if speech_installed else remaining + _GIB
    speech_fit, speech_warnings = _fit(profile, 4 * _GIB, 1.5 * _GIB, speech_disk)
    speech = {'model': 'small', 'name': 'Whisper small 多语言', 'execution': 'cpu-int8',
              'fit': speech_fit, 'reason': '应用当前支持的本地语音模型，使用 CPU int8 运行。',
              'estimatedDownloadBytes': remaining,
              'estimatedRamBytes': int(1.5 * _GIB), 'estimatedDiskBytes': speech_disk,
              'installed': bool(speech_installed),
              'partialBytes': speech_partial_bytes, 'resumable': not speech_installed and speech_partial_bytes > 0,
              'warnings': speech_warnings,
              'sourceUrl': 'https://huggingface.co/Systran/faster-whisper-small'}
    warnings = list(profile['detection']['warnings'])
    if any(any('磁盘' in warning for warning in row['warnings']) for row in vision) or any('磁盘' in warning for warning in speech_warnings):
        warnings.append('部分模型下载所需磁盘空间不足。')
    warnings.append('视觉与语音占用分别估算；建议按顺序运行，避免同时加载导致内存不足。')
    return {'vision': vision, 'speech': speech,
            'preferredVisionRepoId': preferred['repoId'] if preferred else None,
            'summary': ('建议先使用 ' + preferred['name']) if preferred else '暂无能够确认适配的视觉模型，请查看容量提示。',
            'warnings': warnings, 'estimateNotice': _ESTIMATE_NOTICE, 'autoDownload': False}


def _installed_vision_models():
    # VideoActions loads the existing catalogue before this mixin. Reuse its
    # validated manifests; standalone probing does not import or create stores.
    catalog = sys.modules.get('_aive_vision_catalog')
    if catalog is None:
        return []
    try:
        return catalog.installed_models()
    except (OSError, ValueError):
        return []


def _speech_status():
    speech = sys.modules.get('_aive_local_speech')
    auto = sys.modules.get('_aive_smart_auto')
    try:
        if speech is None and auto is not None:
            speech = auto._load('local_speech')
        status = speech.get_status() if speech else {}
        if not isinstance(status, dict):
            status = {}
        partial = status.get('partialBytes', 0)
        if type(partial) is not int or partial < 0:
            partial = 0
        ready = status.get('ready') is True
        if type(partial) is not int or not 0 <= partial <= _SPEECH_MODEL_BYTES:
            partial = 0
        return ready, partial
    except (OSError, ValueError, ImportError, AttributeError):
        return False, 0


def _speech_installed():
    return _speech_status()[0]


class HardwareProfileMixin:
    def video_hardwareProfile(self, payload):
        # No bridge-provided command, output path or hardware override is used.
        profile = detect_hardware()
        installed, partial = _speech_status()
        return {'profile': profile, 'recommendations': recommend_models(
            profile, _installed_vision_models(), speech_installed=installed,
            speech_partial_bytes=partial)}
