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
import os
import urllib.request
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
            root=settings.insightface_root,
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


class PetMockEngine(BaseEngine):
    """宠物识别占位引擎：确定性向量，零依赖跑通全链路（不做真实识别）。"""

    name = "pet-mock"

    def _vec_from_bytes(self, data: bytes) -> np.ndarray:
        h = hashlib.sha256(b"pet|" + data).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-8)

    def embedding_from_file(self, path: str):
        with open(path, "rb") as f:
            return self._vec_from_bytes(f.read())

    def detect_pets(self, image):
        # 不做真实检测：把整帧当作一个宠物候选，保证链路可测试
        h, w = image.shape[:2]
        if h < 1 or w < 1:
            return []
        return [((0, 0, w, h), self._vec_from_bytes(image.tobytes()))]

    # 复用统一接口名，worker 可无差别调用
    detect_faces = detect_pets


# open-noodle 宠物重识别模型（Apache-2.0，ONNX，输出 512 维 L2 归一化向量）
PET_MODEL_URLS = {
    "small": "https://huggingface.co/open-noodle/pet-recognition-small/resolve/main/recognition/model.onnx",
    "base": "https://huggingface.co/open-noodle/pet-recognition-base/resolve/main/recognition/model.onnx",
    "large": "https://huggingface.co/open-noodle/pet-recognition-large/resolve/main/recognition/model.onnx",
}
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)


class PetOnnxEngine(BaseEngine):
    """真实宠物重识别：open-noodle ONNX 模型，onnxruntime 推理。

    - 输入 224x224 RGB，ImageNet 归一化；输出 512 维 L2 归一化 embedding
    - 权重首次使用自动下载到 OPENSIGHT_MODEL_DIR（默认 ~/.cache/opensight/models），
      之后完全离线；offset 提供 model_path 指定本地文件
    - 相似度即余弦/点积；因该模型常态分数偏低，宠物阈值建议 0.25~0.45
    """

    name = "pet-onnx"
    dim = 512

    def __init__(self) -> None:
        import onnxruntime as ort  # type: ignore

        pets = settings.get("pets", {})
        size = str(pets.get("model_size", "small") or "small").lower()
        if size not in PET_MODEL_URLS:
            size = "small"
        local = str(pets.get("model_path", "") or "").strip()
        if not local:
            # 优先用镜像内置模型；找不到再回退旧缓存目录（兼容非 Docker 运行）
            baked = os.path.join(settings.model_dir, f"pet-recognition-{size}.onnx")
            if os.path.exists(baked) and os.path.getsize(baked) > 1000:
                local = baked
            else:
                cache = os.path.join(
                    os.path.expanduser("~"), ".cache", "opensight", "models"
                )
                os.makedirs(cache, exist_ok=True)
                local = os.path.join(cache, f"pet-recognition-{size}.onnx")
        if not os.path.exists(local) or os.path.getsize(local) < 1000:
            log.info("内置/缓存均无模型，下载宠物识别模型 %s -> %s", size, local)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            urllib.request.urlretrieve(PET_MODEL_URLS[size], local)
        self.model_path = local
        self.session = ort.InferenceSession(local, providers=["CPUExecutionProvider"])

    def _embed(self, rgb) -> np.ndarray | None:
        from PIL import Image

        im = rgb if isinstance(rgb, Image.Image) else Image.fromarray(rgb.astype(np.uint8))
        im = im.convert("RGB").resize((224, 224))
        x = np.asarray(im, dtype=np.float32).transpose(2, 0, 1) / 255.0
        x = ((x[None, ...] - _IMAGENET_MEAN) / _IMAGENET_STD).astype(np.float32)
        v = self.session.run(["embedding"], {"input": x})[0][0]
        v = np.asarray(v, dtype=np.float32).ravel()
        n = float(np.linalg.norm(v))
        return (v / n).astype(np.float32) if n > 0 else None

    def embedding_from_file(self, path: str):
        from PIL import Image

        if not os.path.exists(path):
            return None
        return self._embed(Image.open(path))

    def detect_pets(self, image):
        # worker 传入的是 BGR（cv2），转换为 RGB；整帧作为候选
        rgb = image[:, :, ::-1] if image.ndim == 3 and image.shape[2] == 3 else image
        emb = self._embed(rgb)
        if emb is None:
            return []
        h, w = image.shape[:2]
        return [((0, 0, w, h), emb)]

    detect_faces = detect_pets


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


def build_pet_engine() -> BaseEngine:
    backend = str(settings.get("pets", {}).get("backend", "pet-mock") or "pet-mock").lower()
    # 兼容旧配置键 recognition.pet_backend
    if settings["recognition"].get("pet_backend"):
        backend = str(settings["recognition"]["pet_backend"]).lower()
    try:
        if backend in ("pet-onnx", "pet-reid"):
            return PetOnnxEngine()
    except Exception as e:
        log.warning("宠物后端 %s 初始化失败，降级为 pet-mock：%s", backend, e)
    return PetMockEngine()


engine = build_engine()
pet_engine = build_pet_engine()


def engine_for_kind(kind: str) -> BaseEngine:
    """按比对库类型选择识别引擎。"""
    return pet_engine if kind == "pet" else engine
