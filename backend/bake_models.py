"""Docker 构建期脚本：把识别模型下载并固化进镜像，实现开箱即用（运行时零下载）。

用法：在 Dockerfile 中 `RUN python bake_models.py`。
产物：
  /opt/opensight/models/pet-recognition-{size}.onnx   宠物重识别模型
  /opt/opensight/insightface/models/buffalo_sc/...     人脸检测识别模型

运行时若镜像内已有这些模型，代码直接加载，不访问网络；
仅当用户切换到镜像未内置的 model_size（如 base/large）时才按需下载。
"""
from __future__ import annotations

import os
import sys
import urllib.request

MODELS_DIR = os.getenv("OPENSIGHT_MODEL_DIR", "/opt/opensight/models")
IFACE_ROOT = os.getenv("INSIGHTFACE_ROOT", "/opt/opensight/insightface")
PET_MODEL_SIZE = os.getenv("OPENSIGHT_PET_MODEL_SIZE", "small")

PET_MODEL_URLS = {
    "small": "https://huggingface.co/open-noodle/pet-recognition-small/resolve/main/recognition/model.onnx",
    "base": "https://huggingface.co/open-noodle/pet-recognition-base/resolve/main/recognition/model.onnx",
    "large": "https://huggingface.co/open-noodle/pet-recognition-large/resolve/main/recognition/model.onnx",
}
PET_SIZES = {"small": 89_000_000, "base": 348_000_000, "large": 1_200_000_000}


def download_pet(size: str) -> None:
    size = size if size in PET_MODEL_URLS else "small"
    dst = os.path.join(MODELS_DIR, f"pet-recognition-{size}.onnx")
    if os.path.exists(dst) and os.path.getsize(dst) > PET_SIZES[size] * 0.9:
        print(f"[bake] 宠物模型已存在：{dst}")
        return
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[bake] 下载宠物模型 {size} -> {dst}", flush=True)
    urllib.request.urlretrieve(PET_MODEL_URLS[size], dst)
    print(f"[bake] 宠物模型完成：{os.path.getsize(dst)} bytes", flush=True)


def download_face(model: str = "buffalo_sc") -> None:
    # insightface 的 FaceAnalysis 在构造时自动下载模型包到 root 目录
    from insightface.app import FaceAnalysis  # type: ignore

    app = FaceAnalysis(name=model, root=IFACE_ROOT, providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    print(f"[bake] 人脸模型完成：{IFACE_ROOT}/models/{model}", flush=True)


def main() -> None:
    print(f"[bake] MODELS_DIR={MODELS_DIR} IFACE_ROOT={IFACE_ROOT}", flush=True)
    download_pet(PET_MODEL_SIZE)
    try:
        download_face("buffalo_sc")
    except Exception as e:  # 人脸下载失败不应阻断宠物模型入镜，但需明确报错
        print(f"[bake] 人脸模型下载失败：{e}", file=sys.stderr, flush=True)
        raise
    print("[bake] 全部模型已固化到镜像", flush=True)


if __name__ == "__main__":
    main()
