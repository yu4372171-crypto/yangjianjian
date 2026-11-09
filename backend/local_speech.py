"""Offline multilingual transcription with the application's bundled Whisper runtime."""
import os
import sys


def _bootstrap_bundled_python():
    """Make the same packaged modules available to the DLL-based smoke runner."""
    if sys.version_info[:2] != (3, 13) or getattr(sys, "frozen", False):
        return
    internal = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_internal")
    executable = os.path.join(os.path.dirname(internal), "aive-business.exe")
    if not os.path.isfile(os.path.join(internal, "python313.dll")):
        return
    if any(getattr(finder, "_aive_speech_archive", False) for finder in sys.meta_path):
        return
    import _struct
    import marshal
    import zlib
    import _frozen_importlib
    with open(executable, "rb") as stream:
        content = stream.read()
    cookie = content.rfind(b"MEI\x0c\x0b\x0a\x0b\x0e")
    _, total, toc_offset, toc_size, version, _ = _struct.unpack("!8sIIII64s", content[cookie:cookie + 88])
    if version != 313:
        raise RuntimeError("The bundled backend must use Python 3.13")
    start = cookie + 88 - total
    toc = content[start + toc_offset:start + toc_offset + toc_size]
    offset = 0
    pyz = None
    bootstrap = {}
    while offset < len(toc):
        length, position, size, _, compressed, _ = _struct.unpack("!iIIIBc", toc[offset:offset + 18])
        name = toc[offset + 18:offset + length].rstrip(b"\0").decode("utf-8")
        if name == "PYZ.pyz":
            pyz = content[start + position:start + position + size]
            if compressed:
                pyz = zlib.decompress(pyz)
        elif name == "struct":
            record = content[start + position:start + position + size]
            bootstrap[name] = zlib.decompress(record) if compressed else record
        offset += length
    if pyz is None:
        raise RuntimeError("The bundled Python module archive is missing")
    records = dict(marshal.loads(pyz[_struct.unpack("!i", pyz[8:12])[0]:]))

    class Loader:
        def __init__(self, name):
            self.name = name

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            kind, position, size = records[self.name]
            base = os.path.join(internal, *self.name.split("."))
            module.__file__ = os.path.join(base, "__init__.py") if kind == 1 else base + ".py"
            if kind == 1:
                module.__path__ = [base]
            exec(marshal.loads(zlib.decompress(pyz[position:position + size])), module.__dict__)

    class Finder:
        _aive_speech_archive = True

        def find_spec(self, name, path=None, target=None):
            if name in records:
                return _frozen_importlib.ModuleSpec(name, Loader(name), is_package=records[name][0] == 1)

    # Frozen package initializers precede namespace folders containing .pyds.
    sys.meta_path.insert(0, Finder())
    # PyInstaller normally loads struct from CArchive before installing PYZ.
    # The embedding helper skips its bootloader, so load the genuine record.
    for name, record in bootstrap.items():
        if name not in sys.modules:
            module = type(sys)(name)
            module.__file__ = os.path.join(internal, name + ".py")
            sys.modules[name] = module
            exec(marshal.loads(record), module.__dict__)
    if internal not in sys.path:
        sys.path.insert(0, internal)
    sys._MEIPASS = internal
    sys.dont_write_bytecode = True


_bootstrap_bundled_python()

import hashlib
import json
import math
from pathlib import Path
import re
import threading
import wave

MODEL_NAME = "small"
MODEL_REPO = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_SOURCE = "https://huggingface.co/" + MODEL_REPO + "/tree/" + MODEL_REVISION
MODEL_DIR = Path(__file__).resolve().parent / "runtime" / "local_speech" / "models" / MODEL_NAME
MODEL_FILES = (
    {"name": "model.bin", "size": 483546902, "sha256": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"},
    {"name": "config.json", "size": 2370, "sha256": "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"},
    {"name": "tokenizer.json", "size": 2203239, "sha256": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"},
    {"name": "vocabulary.txt", "size": 459861, "sha256": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"},
)
_verified_signature = None
_inference_lock = threading.Lock()

# Official Whisper language order, limited to the 99 language IDs in the
# pinned multilingual-small config/tokenizer (large-v3's yue is not supported).
# https://github.com/openai/whisper/blob/main/whisper/tokenizer.py
_LANGUAGES = {
    "en":"英语", "zh":"中文", "de":"德语", "es":"西班牙语", "ru":"俄语",
    "ko":"韩语", "fr":"法语", "ja":"日语", "pt":"葡萄牙语", "tr":"土耳其语",
    "pl":"波兰语", "ca":"加泰罗尼亚语", "nl":"荷兰语", "ar":"阿拉伯语", "sv":"瑞典语",
    "it":"意大利语", "id":"印尼语", "hi":"印地语", "fi":"芬兰语", "vi":"越南语",
    "he":"希伯来语", "uk":"乌克兰语", "el":"希腊语", "ms":"马来语", "cs":"捷克语",
    "ro":"罗马尼亚语", "da":"丹麦语", "hu":"匈牙利语", "ta":"泰米尔语", "no":"挪威语",
    "th":"泰语", "ur":"乌尔都语", "hr":"克罗地亚语", "bg":"保加利亚语", "lt":"立陶宛语",
    "la":"拉丁语", "mi":"毛利语", "ml":"马拉雅拉姆语", "cy":"威尔士语", "sk":"斯洛伐克语",
    "te":"泰卢固语", "fa":"波斯语", "lv":"拉脱维亚语", "bn":"孟加拉语", "sr":"塞尔维亚语",
    "az":"阿塞拜疆语", "sl":"斯洛文尼亚语", "kn":"卡纳达语", "et":"爱沙尼亚语", "mk":"马其顿语",
    "br":"布列塔尼语", "eu":"巴斯克语", "is":"冰岛语", "hy":"亚美尼亚语", "ne":"尼泊尔语",
    "mn":"蒙古语", "bs":"波斯尼亚语", "kk":"哈萨克语", "sq":"阿尔巴尼亚语", "sw":"斯瓦希里语",
    "gl":"加利西亚语", "mr":"马拉地语", "pa":"旁遮普语", "si":"僧伽罗语", "km":"高棉语",
    "sn":"绍纳语", "yo":"约鲁巴语", "so":"索马里语", "af":"南非荷兰语", "oc":"奥克语",
    "ka":"格鲁吉亚语", "be":"白俄罗斯语", "tg":"塔吉克语", "sd":"信德语", "gu":"古吉拉特语",
    "am":"阿姆哈拉语", "yi":"意第绪语", "lo":"老挝语", "uz":"乌兹别克语", "fo":"法罗语",
    "ht":"海地克里奥尔语", "ps":"普什图语", "tk":"土库曼语", "nn":"新挪威语", "mt":"马耳他语",
    "sa":"梵语", "lb":"卢森堡语", "my":"缅甸语", "bo":"藏语", "tl":"他加禄语",
    "mg":"马达加斯加语", "as":"阿萨姆语", "tt":"鞑靼语", "haw":"夏威夷语", "ln":"林加拉语",
    "ha":"豪萨语", "ba":"巴什基尔语", "jw":"爪哇语", "su":"巽他语",
}


def get_languages():
    return [{"code":"auto", "name":"自动检测"}] + [
        {"code":code, "name":name} for code,name in _LANGUAGES.items()]


class LocalSpeechError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def check_cancel(control=None):
    if control and control.get("cancelled") and control["cancelled"].is_set():
        try:
            from app.workers.control import _CancelledError
        except ImportError:
            raise LocalSpeechError("LOCAL_SPEECH_CANCELLED", "本地语音识别已取消")
        raise _CancelledError()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_ready():
    global _verified_signature
    try:
        manifest = MODEL_DIR / "manifest.json"
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        if metadata.get("repo") != MODEL_REPO or metadata.get("revision") != MODEL_REVISION:
            return False
        signature = [(str(MODEL_DIR.resolve()), manifest.stat().st_mtime_ns)]
        for item in MODEL_FILES:
            path = MODEL_DIR / item["name"]
            stat = path.stat()
            if stat.st_size != item["size"]:
                return False
            signature.append((stat.st_size, stat.st_mtime_ns))
        signature = tuple(signature)
        if signature != _verified_signature:
            if any(sha256_file(MODEL_DIR / item["name"]) != item["sha256"] for item in MODEL_FILES):
                return False
            _verified_signature = signature
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def get_status():
    ready = _model_ready()
    partial_bytes = 0
    try:
        for item in MODEL_FILES:
            partial = MODEL_DIR / (item["name"] + ".partial")
            if partial.is_file() and not partial.is_symlink():
                partial_bytes += min(item["size"], partial.stat().st_size)
    except OSError:
        partial_bytes = 0
    total = sum(item["size"] for item in MODEL_FILES)
    return {"ready": ready, "model": MODEL_NAME, "modelName": "Whisper small 多语言语音识别",
            "engine": "faster-whisper 1.2.1 / CTranslate2 4.8.2 / CPU int8",
            "sourceUrl": MODEL_SOURCE, "modelSize": total,
            "partialBytes": partial_bytes, "downloadedBytes": partial_bytes if not ready else total,
            "resumable": bool(partial_bytes) and not ready,
            "downloadSources": ["https://huggingface.co", "https://hf-mirror.com"],
            "message": "本地语音模型已就绪" if ready else (
                f"已保留 {partial_bytes / 1024**2:.1f} MB 下载进度，可继续下载"
                if partial_bytes else "本地语音模型尚未安装")}


def _new_model():
    if not _model_ready():
        raise LocalSpeechError("LOCAL_SPEECH_MODEL", "本地语音模型尚未安装或校验失败，请先安装语音模型")
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(str(MODEL_DIR), device="cpu", compute_type="int8",
                            cpu_threads=max(1, min(8, os.cpu_count() or 4)), num_workers=1,
                            local_files_only=True)
    except Exception as error:
        raise LocalSpeechError("LOCAL_SPEECH_ENGINE", "无法加载本地语音模型：" + str(error)) from error


def _wav_duration(path):
    try:
        candidate = Path(path).resolve(strict=True)
        if not candidate.is_file() or candidate.suffix.lower() != ".wav":
            raise ValueError("not a WAV file")
        with wave.open(str(candidate), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("expected mono PCM16 16kHz WAV")
            frames = stream.getnframes()
            if frames <= 0 or len(stream.readframes(frames)) != frames * 2:
                raise ValueError("empty or truncated WAV")
        return candidate, frames / 16000.0
    except (OSError, TypeError, ValueError, EOFError, wave.Error) as error:
        raise LocalSpeechError("LOCAL_SPEECH_INPUT", "语音识别需要完整的单声道 16kHz PCM16 WAV 音频") from error


def _bounded_row(start, end, text, lower, upper, word=False):
    try:
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end) or not isinstance(text, str):
            return None
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        # Whisper's leading word spaces carry English/Arabic/etc. boundaries.
        # Keep them while removing trailing controls and empty whitespace words.
        text = text.rstrip() if word else text.strip()
        start, end = round(max(lower, start), 3), round(min(upper, end), 3)
        # Rounding may move an edge outside a fractional audio duration.
        start, end = max(lower, start), min(upper, end)
        if not text.strip() or start >= end:
            return None
        return {"start": start, "end": end, "text": text}
    except (ValueError, TypeError, OverflowError):
        return None


def transcribe(audio_path, control=None, progress=None, language="auto"):
    check_cancel(control)
    if not isinstance(language, str) or language not in {"auto", *_LANGUAGES}:
        raise LocalSpeechError("LOCAL_SPEECH_LANGUAGE", "所选语言不受本地语音模型支持")
    path, duration = _wav_duration(audio_path)
    while not _inference_lock.acquire(timeout=.1):
        check_cancel(control)
    instance, iterator = None, None
    try:
        check_cancel(control)
        if progress:
            progress(0, "正在加载本地语音模型")
        instance = _new_model()
        check_cancel(control)
        iterator, info = instance.transcribe(str(path), language=None if language == "auto" else language, task="transcribe", beam_size=5,
                                             temperature=0.0, word_timestamps=True, vad_filter=True,
                                             vad_parameters={"min_silence_duration_ms": 500},
                                             condition_on_previous_text=False, chunk_length=15,
                                             initial_prompt="以下是简体中文的旁白。" if language == "zh" else None)
        rows, previous_end = [], 0.0
        for segment in iterator:
            check_cancel(control)
            row = _bounded_row(segment.start, segment.end, segment.text, previous_end, duration)
            if row is None:
                continue
            words, word_end = [], row["start"]
            for word in (getattr(segment, "words", None) or []):
                clean = _bounded_row(word.start, word.end, word.word, word_end, row["end"], word=True)
                if clean:
                    words.append(clean)
                    word_end = clean["end"]
            row["words"] = words
            rows.append(row)
            previous_end = row["end"]
            if progress:
                progress(min(99, int(10 + 89 * previous_end / duration)), "正在识别原声并生成原文字幕")
        check_cancel(control)
        if progress:
            progress(100, "语音识别完成" if rows else "未检测到可识别的旁白")
        return {"segments": rows, "language": getattr(info, "language", ""), "model": MODEL_NAME,
                "duration": duration, "notes": [] if rows else ["音频中未检测到可识别的旁白，未生成字幕。"]}
    except LocalSpeechError:
        raise
    except Exception as error:
        check_cancel(control)
        # Preserve the application's own cancellation exception.
        if type(error).__name__ == "_CancelledError":
            raise
        raise LocalSpeechError("LOCAL_SPEECH_FAILED", "本地语音识别失败：" + str(error)) from error
    finally:
        if iterator is not None and hasattr(iterator, "close"):
            iterator.close()
        native = getattr(instance, "model", None)
        if native is not None and hasattr(native, "unload_model"):
            try:
                native.unload_model()
            except Exception:
                pass
        instance = None
        _inference_lock.release()
