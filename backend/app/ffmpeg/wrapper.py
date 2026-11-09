"""Small FFmpeg locator shared by the recovered editing modules."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.ui2.common import BridgeError


class FFmpegError(RuntimeError):
    pass


def find_ffmpeg_dir(preferred: str = "") -> Path:
    candidates: list[Path] = []
    configured = (
        preferred
        or os.environ.get("YJJ_FFMPEG_DIR", "")
        or os.environ.get("AIVE_FFMPEG_DIR", "")
    )
    if configured:
        candidates.append(Path(configured).expanduser())

    from app.config.settings import app_data_dir

    roots = [
        Path(__file__).resolve().parents[2],
        app_data_dir(),
    ]
    for root in roots:
        candidates.extend(
            [
                root / "ffmpeg" / "bin",
                root / "runtime" / "ffmpeg" / "bin",
                root / "Backend" / "runtime" / "ffmpeg" / "bin",
            ]
        )

    located = shutil.which("ffmpeg")
    if located:
        candidates.append(Path(located).resolve().parent)

    for candidate in candidates:
        folder = candidate
        if folder.is_file():
            folder = folder.parent
        ffmpeg = folder / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe = folder / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if ffmpeg.is_file() and ffprobe.is_file():
            return folder.resolve()
    return Path()


class FFmpegTool:
    def __init__(self, ffmpeg_dir: str = ""):
        folder = find_ffmpeg_dir(ffmpeg_dir)
        suffix = ".exe" if os.name == "nt" else ""
        self.directory = folder
        self.ffmpeg = str(folder / ("ffmpeg" + suffix)) if folder else "ffmpeg"
        self.ffprobe = str(folder / ("ffprobe" + suffix)) if folder else "ffprobe"

    def probe_ok(self) -> bool:
        try:
            result = subprocess.run(
                [self.ffmpeg, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def require(self) -> None:
        if not self.probe_ok():
            raise BridgeError(
                "FFMPEG_REQUIRED",
                "未找到可用的 FFmpeg。请在设置中填写包含 ffmpeg.exe 和 ffprobe.exe 的目录。",
            )
