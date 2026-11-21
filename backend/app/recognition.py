"""人脸识别引擎抽象层。

设计要点：
- backend = mock  : 用确定性哈希生成假向量，零依赖跑通全链路（默认）
- backend = insightface : 真实识别（需安装 insightface + onnxruntime 与模型包）
- backend = deepface    : 备选真实识别

无论哪个后端，对外接口一致：
    detect_faces(image_bgr) -> list[(bbox, embedding)]
    embedding_from_file(path) -> np.ndarray | None
    similarity(a, b) -> float  (余弦相似度, 0..1)
"""
from __future__ import annotations

import hashlib
import logging
from typing import List, Tuple

import numpy as np

from .config import settings

log = logging.getLogger("opensight.recognition")


class BaseEngine:
    name = "base"
    dim = 128

    def detect_faces(self, image):
        raise NotImplementedError

    def embedding_from_file(self, path: str):
        raise NotImplementedError

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).ravel()
        b = np.asarray(b, dtype=np.float32).ravel()
        if a.size == 0 or b.size == 0:
            return 0.0
        if a.size != b.size:
            n = min(a.size, b.size)
            a, b = a[:n], b[:n]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.clip(np.dot(a, b) / denom, -1.0, 1.0))


class MockEngine(BaseEngine):
    """确定性占位引擎：把图像字节哈希映射为固定向量。

    仅用于开发与演示，不做任何真实识别。识别结果不可用于任何实际判断。
    """

    name = "mock"

    def _vec_from_bytes(self, data: bytes) -> np.ndarray:
        h = hashlib.sha256(data).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-8)

    def embedding_from_file(self, path: str):
        with open(path, "rb") as f:
            return self._vec_from_bytes(f.read())

    def detect_faces(self, image):
        # 不做真实检测；返回整幅图的一个假人脸框 + 向量，保证链路可测试
        h, w = image.shape[:2]
        if h < 1 or w < 1:
            return []
        bbox = (int(w * 0.3), int(h * 0.2), int(w * 0.7), int(h * 0.6))
        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", image)
            data = buf.tobytes() if ok else image.tobytes()
        except Exception:
            data = image.tobytes()
        return [(bbox, self._vec_from_bytes(data))]


class InsightFaceEngine(BaseEngine):
    name = "insightface"
    dim = 512

    def __init__(self) -> None:
        from insightface.app import FaceAnalysis  # type: ignore
        cfg = settings["recognition"]
        providers = cfg.get("providers") or None
        self.app = FaceAnalysis(
            name=cfg.get("model", "buffalo_s"),
            providers=[providers] if providers else None,
        )
        ctx = 0  # GPU
        try:
            self.app.prepare(ctx_id=ctx, det_size=(640, 640))
        except Exception as e:
            log.warning("GPU 初始化失败，回退 CPU: %s", e)
            self.app.prepare(ctx_id=-1, det_size=(640, 640))

    def detect_faces(self, image):
        faces = self.app.get(image)
        out = []
        for f in faces:
            x1, y1, x2, y2 = [int(v) for v in f.bbox]
            emb = np.asarray(f.embedding, dtype=np.float32)
            out.append(((x1, y1, x2, y2), emb))
        return out

    def embedding_from_file(self, path: str):
        import cv2
        img = cv2.imread(path)
        if img is None:
            return None
        faces = self.detect_faces(img)
        if not faces:
            return None
        # 取最大人脸
        return max(faces, key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]))[1]


class DeepFaceEngine(BaseEngine):
    name = "deepface"
    dim = 512

    def embedding_from_file(self, path: str):
        from deepface import DeepFace  # type: ignore
        obj = DeepFace.represent(img_path=path, model_name="Facenet", enforce_detection=False)
        return np.asarray(obj[0]["embedding"], dtype=np.float32)

    def detect_faces(self, image):
        # DeepFace 逐帧成本较高，简化为整帧代表向量
        import cv2, tempfile, os
        fd, p = tempfile.mkstemp(suffix=".jpg")
        try:
            os.close(fd)
            cv2.imwrite(p, image)
            emb = self.embedding_from_file(p)
        finally:
            try:
                os.remove(p)
            except OSError:
                pass
        if emb is None:
            return []
        h, w = image.shape[:2]
        return [((0, 0, w, h), emb)]


def build_engine() -> BaseEngine:
    backend = settings["recognition"].get("backend", "mock").lower()
    try:
        if backend == "insightface":
            return InsightFaceEngine()
        if backend == "deepface":
            return DeepFaceEngine()
    except Exception as e:
        log.warning("后端 %s 初始化失败，降级为 mock：%s", backend, e)
    return MockEngine()


engine = build_engine()
