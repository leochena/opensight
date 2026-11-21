"""SQLite 数据库（本地）。"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


# 轻量迁移：为升级前的旧库补齐新增列（SQLite 的 create_all 不会改已有表结构）
_MIGRATIONS = [
    ("galleries", "kind", "TEXT DEFAULT 'face'"),
    ("persons", "species", "TEXT DEFAULT ''"),
    ("events", "subject_kind", "TEXT DEFAULT 'face'"),
]


def init_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in _MIGRATIONS:
            if table not in existing_tables:
                continue  # 新库已由 create_all 建好全部列
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
