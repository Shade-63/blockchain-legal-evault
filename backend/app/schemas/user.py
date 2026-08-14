from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
import re

class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")
    display_name: Optional[str] = None
    role: str = Field(..., pattern="^(LAWYER|JUDGE|CLIENT|ADMIN)$", description="Role must be LAWYER, JUDGE, CLIENT, or ADMIN")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Invalid email format")
        return v

class UserLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str]
    role: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: lambda v: str(v)
        }
