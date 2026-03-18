from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
