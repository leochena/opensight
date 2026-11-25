"""告警视频片段录制单测：环形缓冲裁剪 + 真实 MP4 产出。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("OPENSIGHT_CONFIG", "/nonexistent")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.recording import ClipRecorder, FrameBuffer  # noqa: E402


class BufferTests(unittest.TestCase):
    def test_buffer_trims_by_time(self):
        b = FrameBuffer(seconds=1.0, max_frames=100)
        base = time.time()
        for i in range(10):
            b.push(np.zeros((48, 64, 3), dtype=np.uint8), ts=base + i * 0.2)
        snap = b.snapshot()
        # 只保留最近 1 秒（约 5 帧）
        self.assertLessEqual(len(snap), 6)
        self.assertGreaterEqual(len(snap), 4)
        self.assertGreaterEqual(snap[-1].ts, base + 1.6)

    def test_buffer_hard_cap(self):
        b = FrameBuffer(seconds=999, max_frames=5)
        for i in range(20):
            b.push(np.zeros((48, 64, 3), dtype=np.uint8), ts=float(i))
        self.assertEqual(len(b.snapshot()), 5)


class RecorderTests(unittest.TestCase):
    def test_record_clip_produces_mp4(self):
        d = tempfile.mkdtemp(prefix="clip_test_")
        rec = ClipRecorder(video_dir=d, before_seconds=1, after_seconds=1, fps=10)
        now = time.time()
        history = [
            __import__("app.recording", fromlist=["TimedFrame"]).TimedFrame(
                ts=now + i * 0.1,
                frame=np.full((96, 128, 3), (i * 20) % 255, dtype=np.uint8),
            )
            for i in range(10)
        ]
        # 命中后继续供帧 1 秒
        counter = {"n": 0}

        def source():
            if counter["n"] >= 10:
                return None
            counter["n"] += 1
            return np.full((96, 128, 3), 200, dtype=np.uint8)

        path = rec.record_clip("test.mp4", history, source)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000)
        # 用 OpenCV 能重新打开并读到帧
        cap = cv2.VideoCapture(path)
        self.assertTrue(cap.isOpened())
        ok, frame = cap.read()
        cap.release()
        self.assertTrue(ok)
        self.assertEqual(frame.shape[:2], (96, 128))

    def test_async_record(self):
        d = tempfile.mkdtemp(prefix="clip_async_")
        rec = ClipRecorder(video_dir=d, before_seconds=1, after_seconds=0.5, fps=10)
        now = time.time()
        history = [
            __import__("app.recording", fromlist=["TimedFrame"]).TimedFrame(
                ts=now + i * 0.1, frame=np.zeros((64, 64, 3), dtype=np.uint8)
            )
            for i in range(5)
        ]
        result = {}
        rec.record_async("async.mp4", history, lambda: None, on_done=lambda p: result.setdefault("path", p))
        for _ in range(50):
            if "path" in result:
                break
            time.sleep(0.1)
        self.assertIn("path", result)
        self.assertIsNotNone(result["path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
