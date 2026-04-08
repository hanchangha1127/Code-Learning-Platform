from pydantic import BaseModel, field_validator
from server.db.models import PreferredDifficulty

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

    @field_validator("preferred_language")
    @classmethod
    def normalize_preferred_language(cls, value: str) -> str:
        return str(value or "").strip().lower()
