"""Auth dependencies — get_current_user + role guard + data-scope helpers."""

import os
from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt

from fitnova.storage.db import get_session
from fitnova.storage.models import Advisor, Call

SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"


async def get_current_user(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(*roles: str):
    async def checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Not authorized for this role")
        return current_user
    return checker


def can_access_org(user: dict, org_id: int) -> bool:
    return user["org_id"] == org_id


def can_access_team(user: dict, team_id: int) -> bool:
    if user["role"] == "sales_director":
        return True
    return user.get("team_id") == team_id


def can_access_advisor(user: dict, advisor_id: int) -> bool:
    if user["role"] == "sales_director":
        return True
    if user["role"] == "team_leader":
        db = get_session()
        try:
            advisor = db.query(Advisor).filter(Advisor.id == advisor_id).first()
            return advisor is not None and advisor.team_id == user.get("team_id")
        finally:
            db.close()
    return user.get("advisor_id") == advisor_id


def can_access_call(user: dict, call_id: int) -> bool:
    db = get_session()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return False
        if user["role"] == "sales_director":
            return True
        if user["role"] == "team_leader":
            advisor = db.query(Advisor).filter(Advisor.id == call.advisor_id).first()
            return advisor is not None and advisor.team_id == user.get("team_id")
        return call.advisor_id == user.get("advisor_id")
    finally:
        db.close()
