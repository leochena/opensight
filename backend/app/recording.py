"""告警视频片段录制：环形帧缓冲 + 命中时导出前后若干秒 MP4。

设计要点：
- 每帧（不只是检测帧）都喂进环形缓冲，保证命中时"事前"画面完整
- 缓冲按时间戳裁剪，内存有硬上限（默认 5 秒 × 12fps × 640x480 ≈ 55MB/路）
- 命中时另起线程：先写缓冲里的历史帧，再继续采集 N 秒新帧，编码为 MP4
- 录制失败不影响识别主链路，只记日志
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional

import cv2
import numpy as np

from .config import settings

log = logging.getLogger("opensight.recording")


@dataclass
class TimedFrame:
    ts: float
    frame: np.ndarray


class FrameBuffer:
    """按时间裁剪的环形帧缓冲，线程安全。"""

    def __init__(self, seconds: float = 5.0, max_frames: int = 120) -> None:
        self.seconds = seconds
        self.max_frames = max_frames
        self._buf: Deque[TimedFrame] = deque()
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, ts: Optional[float] = None) -> None:
        ts = time.time() if ts is None else ts
        with self._lock:
            self._buf.append(TimedFrame(ts=ts, frame=frame.copy()))
            # 丢弃过期帧
            cutoff = ts - self.seconds
            while self._buf and self._buf[0].ts < cutoff:
                self._buf.popleft()
            # 硬上限保护
            while len(self._buf) > self.max_frames:
                self._buf.popleft()

    def snapshot(self) -> list[TimedFrame]:
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


class ClipRecorder:
    """把环形缓冲的历史帧 + 命中后的实时帧编码成 MP4。"""

    def __init__(
        self,
        video_dir: str,
        before_seconds: float = 5.0,
        after_seconds: float = 5.0,
        fps: float = 12.0,
        codec: str = "mp4v",
    ) -> None:
        self.video_dir = video_dir
        self.before_seconds = before_seconds
        self.after_seconds = after_seconds
        self.fps = fps
        self.codec = codec
        os.makedirs(video_dir, exist_ok=True)

    def _fit_frame(self, frame: np.ndarray, target: tuple[int, int]) -> np.ndarray:
        """统一尺寸并转为 BGR（VideoWriter 需要 BGR）。"""
        h, w = frame.shape[:2]
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif frame.shape[2] == 3:
            # 前端/PIL 来的是 RGB，OpenCV 写入按 BGR 解释；这里统一按传入约定
            pass
        if (w, h) != target:
            frame = cv2.resize(frame, target)
        return frame

    def record_clip(
        self,
        filename: str,
        history: list[TimedFrame],
        frame_source: Callable[[], Optional[np.ndarray]],
    ) -> Optional[str]:
        """同步录制一个片段，返回文件路径；frame_source 返回 None 表示流结束。"""
        if not history:
            return None
        target = (history[0].frame.shape[1], history[0].frame.shape[0])
        path = os.path.join(self.video_dir, filename)
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*self.codec), self.fps, target)
        if not writer.isOpened():
            log.warning("视频编码器初始化失败: %s", path)
            return None
        written = 0
        try:
            for tf in history:
                writer.write(self._fit_frame(tf.frame, target))
                written += 1
            # 命中后继续采集 after_seconds
            deadline = time.time() + self.after_seconds
            while time.time() < deadline:
                frame = frame_source()
                if frame is None:
                    break
                writer.write(self._fit_frame(frame, target))
                written += 1
                time.sleep(max(0.0, 1.0 / self.fps - 0.001))
        except Exception as e:
            log.warning("录制视频片段失败: %s", e)
            return None
        finally:
            writer.release()
        if written == 0:
            if os.path.exists(path):
                os.remove(path)
            return None
        return path

    def record_async(
        self,
        filename: str,
        history: list[TimedFrame],
        frame_source: Callable[[], Optional[np.ndarray]],
        on_done: Optional[Callable[[Optional[str]], None]] = None,
    ) -> threading.Thread:
        """在后台线程录制，避免阻塞识别循环。"""

        def run() -> None:
            try:
                path = self.record_clip(filename, history, frame_source)
                if on_done:
                    on_done(path)
            except Exception as e:
                log.warning("后台录制异常: %s", e)
                if on_done:
                    on_done(None)

        t = threading.Thread(target=run, daemon=True, name=f"clip-{filename}")
        t.start()
        return t


def build_recorder() -> Optional[ClipRecorder]:
    """按配置构建录像器；未启用返回 None。"""
    cfg = settings.get("events", {})
    if not cfg.get("save_video", False):
        return None
    try:
        return ClipRecorder(
            video_dir=settings.video_dir,
            before_seconds=float(cfg.get("video_before_seconds", 5)),
            after_seconds=float(cfg.get("video_after_seconds", 5)),
            fps=float(cfg.get("video_fps", 12)),
        )
    except Exception as e:
        log.warning("录像器初始化失败，视频功能禁用: %s", e)
        return None
