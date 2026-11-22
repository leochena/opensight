FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 构建期把人脸(buffalo_sc)与宠物(ONNX)模型固化进镜像，运行时零下载、开箱即用。
# 如需更大宠物模型，构建前设置 OPENSIGHT_PET_MODEL_SIZE=base|large。
COPY bake_models.py /app/
RUN python bake_models.py

ENV OPENSIGHT_MODEL_DIR=/opt/opensight/models \
    INSIGHTFACE_ROOT=/opt/opensight/insightface

COPY app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
