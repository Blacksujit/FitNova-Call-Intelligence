"""
Shared fixtures for all test suites.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from fitnova.storage.db import get_session
from fitnova.storage.models import Advisor
from fitnova.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


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
    raise RuntimeError("No advisors in DB — run main.py first to seed the DB")


@pytest.fixture
def sample_call_audio() -> bytes:
    return b"Advisor: Hello this is a test call.\nCustomer: Hi, I'm interested in your program."
