"""Auth-specific tests: login flow, 401, 403, role scoping."""

from fastapi.testclient import TestClient
from fitnova.api.main import app


def test_health_always_open(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_protected_endpoint_returns_401_without_token(client):
    r = client.get("/incoming/list")
    assert r.status_code == 401


def test_login_with_valid_credentials(client):
    r = client.post("/auth/login", json={"email": "director@fitnova.in", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "sales_director"


def test_login_with_invalid_password_returns_401(client):
    r = client.post("/auth/login", json={"email": "director@fitnova.in", "password": "wrong"})
    assert r.status_code == 401


def test_login_with_nonexistent_email_returns_401(client):
    r = client.post("/auth/login", json={"email": "nobody@fitnova.in", "password": "admin123"})
    assert r.status_code == 401


def test_me_endpoint_returns_current_user(client):
    r = client.post("/auth/login", json={"email": "director@fitnova.in", "password": "admin123"})
    token = r.json()["access_token"]
    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "director@fitnova.in"


def test_me_without_token_returns_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_invalid_token_returns_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert r.status_code == 401


def test_team_leader_cannot_access_other_team(client):
    """Beta Lead cannot access Alpha Pod's team data."""
    r = client.post("/auth/login", json={"email": "beta_lead@fitnova.in", "password": "lead123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Alpha Pod is team_id=1, Beta Lead has team_id=2
    # Beta Lead should not see team 1
    r2 = client.get("/teams/1/summary", headers=headers)
    assert r2.status_code == 403


def test_advisor_cannot_see_other_advisor(client):
    """Priya cannot see Vikram's advisor data."""
    r = client.post("/auth/login", json={"email": "priya@fitnova.in", "password": "advisor123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Priya is advisor_id=1, Vikram is advisor_id=5
    r2 = client.get("/advisors/5/summary", headers=headers)
    assert r2.status_code == 403


def test_sales_director_can_see_any_team(client):
    r = client.post("/auth/login", json={"email": "director@fitnova.in", "password": "admin123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r2 = client.get("/teams/1/summary", headers=headers)
    assert r2.status_code == 200
    r3 = client.get("/teams/2/summary", headers=headers)
    assert r3.status_code == 200


def test_advisor_cannot_contest_other_advisors_tag(client, db, advisor, sample_call_audio, sd_headers):
    """Priya cannot contest tags on Vikram's calls."""
    from fitnova.pipeline.orchestrator import process_call as run_pipeline
    from fitnova.storage.models import Tag

    # Process call for Vikram (advisor_id=5) with audio that triggers tag creation
    vikram = db.query(type(advisor)).filter(type(advisor).email == "vikram@fitnova.in").first()
    audio = b"Advisor: I guaranteed you 100 percent results.\nCustomer: Okay let's proceed."
    run_pipeline("AUTH-CONTEST-OTHER-001", vikram.id, "test", audio, db)
    tag = db.query(Tag).filter(Tag.call.has(external_call_id="AUTH-CONTEST-OTHER-001")).first()

    # Priya tries to contest
    r = client.post("/auth/login", json={"email": "priya@fitnova.in", "password": "advisor123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r2 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "not fair"}, headers=headers)
    assert r2.status_code == 403


def test_advisor_can_contest_own_tag(client, db, advisor, sample_call_audio, sd_headers):
    """Priya can contest tags on her own calls."""
    from fitnova.pipeline.orchestrator import process_call as run_pipeline
    from fitnova.storage.models import Tag

    # Process call for Priya with audio that triggers tag creation
    audio = b"Advisor: This offer won't be available tomorrow.\nCustomer: When can I start?"
    run_pipeline("AUTH-CONTEST-OWN-001", advisor.id, "test", audio, db)
    tag = db.query(Tag).filter(Tag.call.has(external_call_id="AUTH-CONTEST-OWN-001")).first()

    r = client.post("/auth/login", json={"email": "priya@fitnova.in", "password": "advisor123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r2 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "not accurate"}, headers=headers)
    assert r2.status_code == 200


def test_register_creates_new_user(client):
    r = client.post("/auth/register", json={
        "email": "test_new_user@fitnova.in",
        "password": "newpass123",
        "name": "New User",
        "role": "advisor",
        "org_id": 1,
        "team_id": 1,
        "advisor_id": 1,
    })
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "test_new_user@fitnova.in"


def test_register_duplicate_email_returns_400(client):
    r = client.post("/auth/register", json={
        "email": "director@fitnova.in",
        "password": "test",
        "name": "Test",
        "role": "sales_director",
        "org_id": 1,
    })
    assert r.status_code == 400
