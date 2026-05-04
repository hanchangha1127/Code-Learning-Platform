from typing import Annotated

from pydantic import AliasChoices, BaseModel, EmailStr, Field, StringConstraints

UsernameStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]{3,50}$",
    ),
]
SignupPasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=128)]
LoginPasswordStr = Annotated[str, StringConstraints(min_length=1, max_length=128)]
RefreshTokenStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=512)]
DisplayNameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SignUpRequest(BaseModel):
    email: EmailStr
    username: UsernameStr
    display_name: DisplayNameStr | None = Field(
        default=None,
        validation_alias=AliasChoices("display_name", "displayName"),
    )
    password: SignupPasswordStr


class LoginRequest(BaseModel):
    username: UsernameStr
    password: LoginPasswordStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: RefreshTokenStr


class LogoutRequest(BaseModel):
    refresh_token: RefreshTokenStr
