# scripts/create_tables.py
from app.db.session import engine
from app.db.base import Base
import app.db.models  # noqa: F401 (모델 import로 Base에 등록)

Base.metadata.create_all(bind=engine)
print("✅ tables created")

