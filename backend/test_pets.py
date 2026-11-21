"""宠物识别链路单测：库类型、物种、引擎分组、事件主体类型、旧库迁移。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

os.environ["OPENSIGHT_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_config.yaml")
os.environ.setdefault("OPENSIGHT_DATA_DIR", tempfile.mkdtemp(prefix="opensight_pets_"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.recognition import engine, engine_for_kind, pet_engine  # noqa: E402

client = TestClient(app)


class PetEngineTests(unittest.TestCase):
    def test_mock_engines_are_zero_dependency(self):
        self.assertEqual(engine.name, "mock")
        self.assertEqual(pet_engine.name, "pet-mock")

    def test_engine_for_kind(self):
        self.assertIs(engine_for_kind("pet"), pet_engine)
        self.assertIs(engine_for_kind("face"), engine)
        self.assertIs(engine_for_kind(""), engine)

    def test_pet_mock_vector_is_deterministic_and_separate(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (120, 90), (180, 160, 140))
        bio = io.BytesIO()
        img.save(bio, format="JPEG")
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(bio.getvalue())
            path = f.name
        try:
            a = pet_engine.embedding_from_file(path)
            b = pet_engine.embedding_from_file(path)
            self.assertIsNotNone(a)
            self.assertTrue((a == b).all())
            self.assertGreater(pet_engine.similarity(a, b), 0.99)
            # 同一张图在人脸与宠物引擎中的向量不应相同（命名空间隔离）
            face_vec = engine.embedding_from_file(path)
            self.assertFalse((a == face_vec).all())
        finally:
            os.unlink(path)


class RealModelTests(unittest.TestCase):
    """真实 ONNX 模型集成测试：仅在模型可用时运行，验证embedding有效。"""

    def test_pet_onnx_real_embedding(self):
        model_path = os.path.join(
            os.path.expanduser("~"), ".cache", "opensight", "models",
            "pet-recognition-small.onnx",
        )
        img_dir = os.path.join(
            os.path.expanduser("~"), ".cache", "opensight", "testimgs",
        )
        if not os.path.exists(model_path) or not os.path.isdir(img_dir):
            self.skipTest("本地无缓存模型/测试图，跳过（CI 环境可选）")
        try:
            from app.recognition import PetOnnxEngine
        except Exception as e:
            self.skipTest(f"onnxruntime 未安装：{e}")

        engine = PetOnnxEngine.__new__(PetOnnxEngine)  # 绕过 config 下载逻辑
        import onnxruntime as ort
        engine.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        a = engine.embedding_from_file(os.path.join(img_dir, "dog1.jpg"))
        b = engine.embedding_from_file(os.path.join(img_dir, "dog2.jpg"))
        self.assertIsNotNone(a)
        self.assertEqual(a.shape, (512,))
        self.assertAlmostEqual(float((a ** 2).sum()), 1.0, places=3)  # L2 归一化
        sim = float(engine.similarity(a, b))
        self.assertGreater(sim, -1.0)
        self.assertLess(sim, 1.0)


class PetApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_pet_gallery_and_species_roundtrip(self):
        g = client.post("/api/galleries", json={"name": "我家狗", "description": "后院", "kind": "pet"}).json()
        self.assertEqual(g["kind"], "pet")
        gid = g["id"]

        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), (210, 200, 190))
        bio = io.BytesIO()
        img.save(bio, format="JPEG")
        files = {"file": ("dog.jpg", bio.getvalue(), "image/jpeg")}
        r = client.post(
            f"/api/galleries/{gid}/persons?name=旺财&species=金毛&note=后院拍摄&risk_ack=true",
            files=files,
        )
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["species"], "金毛")

        persons = client.get(f"/api/galleries/{gid}/persons").json()
        self.assertTrue(any(x["species"] == "金毛" for x in persons))

        # 人脸库不受影响，仍默认为 face
        fg = client.post("/api/galleries", json={"name": "家人"}).json()
        self.assertEqual(fg["kind"], "face")

        # 清理
        client.delete(f"/api/galleries/{gid}")
        client.delete(f"/api/galleries/{fg['id']}")

    def test_config_exposes_both_engines(self):
        cfg = client.get("/api/config").json()
        self.assertIn("engine", cfg)
        self.assertIn("pet_engine", cfg)


class MigrationTests(unittest.TestCase):
    def test_old_database_gets_new_columns(self):
        """模拟老库：只有旧列，init_db 后应补齐 kind/species/subject_kind。"""
        from sqlalchemy import create_engine, text

        path = os.path.join(tempfile.mkdtemp(prefix="opensight_mig_"), "old.db")
        old = create_engine(f"sqlite:///{path}")
        with old.begin() as c:
            c.execute(text("CREATE TABLE galleries (id INTEGER PRIMARY KEY, name TEXT, description TEXT, created_at DATETIME)"))
            c.execute(text("CREATE TABLE persons (id INTEGER PRIMARY KEY, gallery_id INTEGER, name TEXT, note TEXT, image_path TEXT, embedding_path TEXT, created_at DATETIME)"))
            c.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY, camera_id INTEGER, camera_name TEXT, person_id INTEGER, person_name TEXT, gallery_id INTEGER, similarity REAL, snapshot_path TEXT, status TEXT, note TEXT, created_at DATETIME)"))

        import app.database as database
        original_engine = database.engine
        database.engine = old
        try:
            database.init_db()
            with old.begin() as c:
                cols_g = {r[1] for r in c.execute(text("PRAGMA table_info(galleries)"))}
                cols_p = {r[1] for r in c.execute(text("PRAGMA table_info(persons)"))}
                cols_e = {r[1] for r in c.execute(text("PRAGMA table_info(events)"))}
            self.assertIn("kind", cols_g)
            self.assertIn("species", cols_p)
            self.assertIn("subject_kind", cols_e)
        finally:
            database.engine = original_engine


if __name__ == "__main__":
    unittest.main(verbosity=2)
