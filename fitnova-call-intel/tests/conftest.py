"""
Shared fixtures for all test suites — uses in-memory SQLite for isolation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from fitnova.storage.db import set_test_db, get_session
from fitnova.storage.models import (
    Base, Org, Team, Advisor, User, Call, Segment, Score, Tag, Contest,
    TagStatus,
)
from fitnova.storage.seed import seed_data, seed_users
from fitnova.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    set_test_db()
    seed_data()
    seed_users()


@pytest.fixture
def db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def advisor(db):
    advisor = db.query(Advisor).filter(Advisor.email == "priya@fitnova.in").first()
    if advisor:
        return advisor
    advisor = db.query(Advisor).first()
    if advisor:
        return advisor
    raise RuntimeError("No advisors in DB — run seed_data.py first")


@pytest.fixture
def sample_call_audio() -> bytes:
    return b"Advisor: Hello this is a test call.\nCustomer: Hi, I'm interested in your program."


# ── Auth token fixtures ────────────────────────────────────────────────

def _login(email: str, password: str) -> dict:
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sd_headers():
    """Sales Director auth headers."""
    return _login("director@fitnova.in", "admin123")


@pytest.fixture
def tl_headers():
    """Team Leader (Alpha Pod) auth headers."""
    return _login("alpha_lead@fitnova.in", "lead123")


@pytest.fixture
def advisor_headers():
    """Advisor (Priya Sharma) auth headers."""
    return _login("priya@fitnova.in", "advisor123")
