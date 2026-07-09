"""Auth endpoints — login, register, me."""

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from fitnova.storage.db import get_session
from fitnova.storage.models import User

from .dependencies import get_current_user, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str
    org_id: int
    team_id: int | None = None
    advisor_id: int | None = None


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    org_id: int
    team_id: int | None
    advisor_id: int | None

    model_config = {"from_attributes": True}


def _create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "org_id": user.org_id,
        "team_id": user.team_id,
        "advisor_id": user.advisor_id,
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login")
def login(body: LoginRequest):
    db = get_session()
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user or not pwd.verify(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = _create_token(user)
        return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}
    finally:
        db.close()


@router.post("/register")
def register(body: RegisterRequest):
    db = get_session()
    try:
        existing = db.query(User).filter(User.email == body.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = User(
            email=body.email,
            password_hash=pwd.hash(body.password),
            name=body.name,
            role=body.role,
            org_id=body.org_id,
            team_id=body.team_id,
            advisor_id=body.advisor_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = _create_token(user)
        return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}
    finally:
        db.close()


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
