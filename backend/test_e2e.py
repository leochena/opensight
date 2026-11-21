"""端到端冒烟测试：验证 API 全链路（需先启动服务或使用 TestClient）。"""
import os
import tempfile

os.environ.setdefault("OPENSIGHT_CONFIG", "/nonexistent")  # 用默认配置(mock)
tmpdir = tempfile.mkdtemp(prefix="opensight_e2e_")
os.environ["OPENSIGHT_DATA_DIR"] = tmpdir

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402

client = TestClient(app)


def show(label, r):
    print(f"[{label}] {r.status_code} {str(r.json())[:160]}")
    assert r.status_code in (200, 201), f"{label} failed: {r.text}"


def main():
    show("health", client.get("/api/health"))
    show("config", client.get("/api/config"))

    g = client.post("/api/galleries", json={"name": "测试库", "description": "e2e"}).json()
    show("create gallery", client.post("/api/galleries", json={"name": "测试库2", "description": ""}))
    gid = g["id"]

    # 生成一张测试图片（Pillow，避免 opencv 依赖）
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), (200, 200, 200))
    bio = io.BytesIO()
    img.save(bio, format="JPEG")
    files = {"file": ("test.jpg", bio.getvalue(), "image/jpeg")}
    show("add person", client.post(f"/api/galleries/{gid}/persons?name=张三&note=测试&risk_ack=true", files=files))
    show("list persons", client.get(f"/api/galleries/{gid}/persons"))
    show("list galleries", client.get("/api/galleries"))

    show("create camera", client.post("/api/cameras", json={"name": "前门", "source": "rtsp://x/y", "kind": "rtsp"}))
    show("list cameras", client.get("/api/cameras"))
    cams = client.get("/api/cameras").json()
    show("toggle camera", client.post(f"/api/cameras/{cams[0]['id']}/toggle"))
    show("delete camera", client.delete(f"/api/cameras/{cams[0]['id']}"))

    show("notifications test", client.post("/api/notifications/test"))
    show("list events", client.get("/api/events"))
    show("audit", client.get("/api/audit"))
    show("cleanup", client.post("/api/events/cleanup"))
    show("purge all", client.post("/api/privacy/purge-all?confirm=DELETE"))
    show("galleries after purge", client.get("/api/galleries"))

    print("\nALL E2E CHECKS PASSED")


if __name__ == "__main__":
    main()
