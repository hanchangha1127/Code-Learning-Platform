from pydantic import BaseModel
from app.db.models import PreferredDifficulty

class UserRead(BaseModel):
    id: int
    email: str
    username: str
    role: str
    status: str
    model_config = {"from_attributes": True}

class UserSettingsRead(BaseModel):
    preferred_language: str
    preferred_difficulty: PreferredDifficulty
    model_config = {"from_attributes": True}

class UserSettingsUpdate(BaseModel):
    preferred_language: str
    preferred_difficulty: PreferredDifficulty
