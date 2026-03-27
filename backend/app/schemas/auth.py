from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Regular sign-up: real email + password. Internal username is assigned server-side."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    username: str
    email: str  # str not EmailStr: admin@internal.test etc. may fail strict validation
    profile_name: str = ""
    credits_balance: int
    paid_access: bool = False
    is_admin: bool = False


class ProfileUpdateRequest(BaseModel):
    profile_name: str = Field(default="", max_length=120)

    @field_validator("profile_name")
    @classmethod
    def strip_profile_name(cls, v: str) -> str:
        return (v or "").strip()[:120]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
    confirm_new_password: str = Field(min_length=8, max_length=200)

