"""Local video repair and ordered concatenation for the existing task bridge."""

from __future__ import annotations

import base64
from fractions import Fraction
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading

from app.ui2.common import BridgeError
from app.workers.control import check_control


_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _load_editor_extension(name):
    module_name = '_aive_' + name
    module = sys.modules.get(module_name)
    if module is None:
        path = Path(__file__).resolve().with_name(name + '.py')
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    return module


_drop_module = _load_editor_extension('smart_drop_upload')
_smart_module = _load_editor_extension('smart_editing')
_vision_module = _load_editor_extension('smart_vision')
_catalog_module = _load_editor_extension('vision_catalog')
_auto_module = _load_editor_extension('smart_auto')
_assets_module = _load_editor_extension('editor_assets')
_tasks_module = _load_editor_extension('task_center')
_timeline_module = _load_editor_extension('timeline_editing')
_hardware_module = _load_editor_extension('hardware_profile')
_requirements_module = _load_editor_extension('requirement_models')
_api_connections_module = _load_editor_extension('api_connections_rpc')
_updates_module = _load_editor_extension('app_updates')
_free_assets_module = _load_editor_extension('free_assets')


def _error(message, code="VIDEO_INVALID"):
    raise BridgeError(code, message)


def _local_path(value, *, existing):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        _error("请选择有效的本地文件路径")
    if "://" in value or value.startswith(("\\\\", "//")):
        _error("视频工具仅支持本机文件")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        _error("请选择完整的本地文件路径")
    try:
        path = candidate.resolve()
    except (OSError, ValueError, RuntimeError):
        _error("文件不存在或路径无法读取")
    if str(path).startswith(("\\\\", "//")):
        _error("视频工具仅支持本机文件")
    if existing and not path.is_file():
        _error("选择的视频文件不存在或无法读取")
    return path


def _output_path(value, inputs):
    path = _local_path(value, existing=False)
    if path.suffix.lower() != ".mp4":
        _error("输出文件请使用 .mp4 扩展名")
    if path in inputs:
        _error("输出路径不能与输入视频相同", "VIDEO_OUTPUT_EXISTS")
    if os.path.lexists(path):
        _error("输出文件已存在，请选择新的文件名", "VIDEO_OUTPUT_EXISTS")
    if not path.parent.is_dir():
        _error("输出目录不存在，请重新选择保存位置")
    return path


def _capture(args, *, timeout=20):
    try:
        process = subprocess.run(
            [str(x) for x in args], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=timeout, creationflags=_FLAGS,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _error("无法读取视频，请确认文件可用且 FFmpeg 已安装", "VIDEO_PROBE_FAILED")
    if process.returncode:
        _error("无法读取视频，请检查视频文件是否完整", "VIDEO_PROBE_FAILED")
    return process.stdout


def _probe(tool, path):
    raw = _capture([
        tool.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_streams", "-show_format", "-of", "json", path,
    ])
    try:
        info = json.loads(raw)
        streams = info.get("streams", [])
        videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
        video = next((s for s in videos if s.get("disposition", {}).get("default")), None)
        if video is None:
            video = next(iter(videos))
        width, height = int(video["width"]), int(video["height"])
        try:
            sar = float(Fraction(video.get("sample_aspect_ratio", "1:1").replace(":", "/")))
        except (ValueError, ZeroDivisionError):
            sar = 1.0
        if not math.isfinite(sar) or sar <= 0:
            sar = 1.0
        width = max(1, int(round(width * sar)))
        rotation = float(video.get("tags", {}).get("rotate", 0))
        for side in video.get("side_data_list", []):
            if "rotation" in side:
                rotation = float(side["rotation"])
        if int(round(rotation / 90)) % 2:
            width, height = height, width
        duration = float(video.get("duration") or info.get("format", {}).get("duration") or 0)
        try:
            fps = float(Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30"))
        except (ValueError, ZeroDivisionError):
            fps = 30.0
        if width <= 0 or height <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid video dimensions or duration")
        if not math.isfinite(fps) or fps <= 0:
            fps = 30.0
        return {
            "path": str(path), "width": width, "height": height,
            "duration": duration, "fps": min(fps, 120.0),
            "hasAudio": any(s.get("codec_type") == "audio" for s in streams),
            "_videoStream": int(video["index"]),
        }
    except (ValueError, KeyError, TypeError, StopIteration):
        _error("文件没有可处理的视频画面或时长", "VIDEO_PROBE_FAILED")


def _run_ffmpeg(tool, args, duration, progress, control, workdir, *, start=0, span=95):
    """Drain progress separately so cancellation can stop only our child process."""
    check_control(control)
    messages = queue.Queue()
    command = [
        tool.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1", "-y", *[str(x) for x in args],
    ]
    with tempfile.TemporaryFile(dir=workdir) as error_log:
        try:
            child = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=error_log, text=True, encoding="utf-8", errors="replace",
                creationflags=_FLAGS, shell=False, cwd=str(workdir),
            )
        except OSError:
            _error("无法启动 FFmpeg，请检查安装目录", "VIDEO_PROCESS_FAILED")

        def read_progress():
            for line in child.stdout:
                key, _, value = line.strip().partition("=")
                if key == "out_time_us":
                    try:
                        messages.put(float(value) / 1_000_000)
                    except ValueError:
                        pass

        reader = threading.Thread(target=read_progress, daemon=True)
        reader.start()
        try:
            while True:
                check_control(control)
                try:
                    elapsed = messages.get(timeout=0.1)
                except queue.Empty:
                    elapsed = None
                if elapsed is not None:
                    percent = start + span * min(1.0, max(0.0, elapsed) / max(duration, 0.001))
                    progress(min(97, int(percent)), "正在处理视频")
                if child.poll() is not None:
                    break
            check_control(control)
            if child.returncode:
                error_log.seek(0, os.SEEK_END)
                end = error_log.tell()
                error_log.seek(max(0, end - 1800))
                detail = error_log.read().decode("utf-8", "replace").strip()
                _error("视频处理失败：" + (detail or "FFmpeg 无法完成处理"), "VIDEO_PROCESS_FAILED")
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            reader.join(timeout=3)
            child.stdout.close()


def _commit(stage, output, progress, control):
    progress(98, "正在保存输出视频")
    check_control(control)
    try:
        # Windows rename fails atomically if the destination appeared meanwhile.
        # The hard-link equivalent preserves that contract on other platforms.
        if os.name == "nt":
            os.rename(stage, output)
        else:
            os.link(stage, output)
            stage.unlink()
    except FileExistsError:
        _error("输出文件已存在，请选择新的文件名", "VIDEO_OUTPUT_EXISTS")
    except OSError:
        _error("无法保存输出，请检查目录权限和可用空间", "VIDEO_SAVE_FAILED")


class VideoActions(_drop_module.UploadMixin, _smart_module.SmartEditingMixin, _vision_module.VisionMixin, _catalog_module.VisionCatalogMixin, _auto_module.SmartAutoMixin, _assets_module.EditorAssetsMixin, _tasks_module.TaskCenterMixin, _timeline_module.TimelineEditingMixin, _hardware_module.HardwareProfileMixin, _requirements_module.RequirementModelsMixin, _api_connections_module.ApiConnectionsMixin, _updates_module.AppUpdatesMixin, _free_assets_module.FreeAssetsMixin):
    def __init__(self, api):
        self.api = api
        self._init_drop_uploads()
        self._smart_helpers = globals()
        _drop_module.install_lifecycle_hook(type(api))
        _updates_module.install_lifecycle_hook(type(api))
        _tasks_module.install(api)

    def video_probe(self, data):
        path = _local_path(data.get("path"), existing=True)
        tool = self.api.ctx.ffmpeg_tool()
        info = _probe(tool, path)
        scale = min(1.0, 640 / max(info["width"], info["height"]))
        preview_width = max(1, round(info["width"] * scale))
        preview_height = max(1, round(info["height"] * scale))
        jpeg = _capture([
            tool.ffmpeg, "-hide_banner", "-loglevel", "error",
            "-protocol_whitelist", "file,pipe", "-ss", str(min(1.0, info["duration"] / 3)),
            "-i", path, "-map", f"0:{info['_videoStream']}", "-frames:v", "1", "-vf",
            f"scale={preview_width}:{preview_height},setsar=1",
            "-q:v", "4", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1",
        ], timeout=20)
        if not jpeg or len(jpeg) > 1_000_000:
            _error("无法生成视频预览", "VIDEO_PREVIEW_FAILED")
        info["preview"] = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        info.pop("_videoStream")
        return info

    def video_removeWatermark(self, data):
        source = _local_path(data.get("path"), existing=True)
        output = _output_path(data.get("output"), [source])
        tool = self.api.ctx.ffmpeg_tool()
        info = _probe(tool, source)
        rect = data.get("rect")
        if not isinstance(rect, dict):
            _error("请框选需要修复的水印区域")
        values = [rect.get(key) for key in ("x", "y", "width", "height")]
        if any(not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) or int(n) != n for n in values):
            _error("水印区域坐标必须为整数像素")
        x, y, width, height = map(int, values)
        if x < 0 or y < 0 or width < 2 or height < 2 or x + width > info["width"] or y + height > info["height"]:
            _error("水印区域超出画面范围或尺寸过小")

        def work(progress, control):
            check_control(control)
            with tempfile.TemporaryDirectory(prefix=".aive-video-", dir=output.parent) as temporary:
                folder = Path(temporary)
                stage = folder / "output.mp4"
                # A two-pixel border lets delogo handle selections at frame edges.
                filters = f"scale={info['width']}:{info['height']},setsar=1,pad=iw+4:ih+4:2:2,delogo=x={x+2}:y={y+2}:w={width}:h={height}:show=0,crop=iw-4:ih-4:2:2,pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0"
                _run_ffmpeg(tool, [
                    "-protocol_whitelist", "file,pipe", "-i", source,
                    "-map", f"0:{info['_videoStream']}", "-map", "0:a:0?", "-vf", filters,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0",
                    "-movflags", "+faststart", stage,
                ], info["duration"], progress, control, folder)
                _probe(tool, stage)
                _commit(stage, output, progress, control)
            return {"path": str(output), "width": info["width"], "height": info["height"], "duration": info["duration"]}

        return self.api.tasks.start("视频消除水印", work, category="video", location={"route": "/video-tools"})

    def video_concat(self, data):
        paths = data.get("paths")
        if not isinstance(paths, list) or len(paths) < 2:
            _error("请至少选择两段视频进行拼接")
        sources = [_local_path(path, existing=True) for path in paths]
        output = _output_path(data.get("output"), sources)
        tool = self.api.ctx.ffmpeg_tool()

        def work(progress, control):
            check_control(control)
            infos = []
            for source in sources:
                check_control(control)
                infos.append(_probe(tool, source))
            first = infos[0]
            width, height = first["width"] + first["width"] % 2, first["height"] + first["height"] % 2
            fps = first["fps"]
            durations = [max(1, math.ceil(i["duration"] * fps - 0.0001)) / fps for i in infos]
            total = sum(durations)
            finished = 0
            with tempfile.TemporaryDirectory(prefix=".aive-video-", dir=output.parent) as temporary:
                folder = Path(temporary)
                for index, (source, info, duration) in enumerate(zip(sources, infos, durations)):
                    check_control(control)
                    progress(int(85 * finished / total), f"正在处理第 {index + 1}/{len(sources)} 段视频")
                    segment = folder / f"segment-{index:05d}.mkv"
                    args = ["-protocol_whitelist", "file,pipe", "-i", source]
                    if not info["hasAudio"]:
                        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                    filters = f"scale={info['width']}:{info['height']},setsar=1,scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps:.8f},tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration:.8f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
                    args += [
                        "-map", f"0:{info['_videoStream']}", "-map", "0:a:0" if info["hasAudio"] else "1:a:0",
                        "-vf", filters, "-af", f"aresample=48000:async=1:first_pts=0,apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS",
                        "-t", f"{duration:.8f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-map_metadata", "-1", segment,
                    ]
                    _run_ffmpeg(tool, args, duration, progress, control, folder, start=85 * finished / total, span=85 * duration / total)
                    finished += duration
                manifest = folder / "segments.txt"
                manifest.write_text("".join(f"file 'segment-{i:05d}.mkv'\n" for i in range(len(sources))), encoding="utf-8")
                stage = folder / "output.mp4"
                _run_ffmpeg(tool, [
                    "-protocol_whitelist", "file,pipe", "-f", "concat", "-safe", "0", "-i", manifest,
                    "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", "aresample=48000:async=1:first_pts=0", "-map_metadata", "-1", "-movflags", "+faststart", stage,
                ], total, progress, control, folder, start=85, span=12)
                completed = _probe(tool, stage)
                _commit(stage, output, progress, control)
            return {"path": str(output), "width": width, "height": height, "duration": completed["duration"], "count": len(sources)}

        return self.api.tasks.start("视频顺序拼接", work, category="video", location={"route": "/video-tools"})
