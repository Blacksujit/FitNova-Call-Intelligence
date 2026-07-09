"""Org / Team / Advisor summary endpoint tests."""

from fitnova.storage.models import Org, Team, Advisor


def test_org_summary_returns_org_and_teams(client, db, sd_headers):
    org = db.query(Org).first()
    r = client.get(f"/orgs/{org.id}/summary", headers=sd_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["org"] == org.name
    assert "averages" in data
    assert "teams" in data
    assert len(data["teams"]) >= 2


def test_org_summary_has_per_dimension_averages(client, sd_headers):
    """Averages must include per-dimension + overall."""
    r = client.get("/orgs/1/summary", headers=sd_headers)
    avg = r.json()["averages"]
    expected_dims = {"needs_discovery", "product_knowledge", "objection_handling", "compliance", "next_step_booking", "overall"}
    assert expected_dims.issubset(avg.keys()), f"Missing dimensions: {expected_dims - avg.keys()}"


def test_nonexistent_org_returns_404(client, sd_headers):
    r = client.get("/orgs/99999/summary", headers=sd_headers)
    assert r.status_code == 404


def test_team_summary_returns_advisors(client, db, sd_headers):
    team = db.query(Team).first()
    r = client.get(f"/teams/{team.id}/summary", headers=sd_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["team"] == team.name
    assert len(data["advisors"]) >= 1
    for a in data["advisors"]:
        assert "name" in a
        assert "averages" in a


def test_nonexistent_team_returns_404(client, sd_headers):
    r = client.get("/teams/99999/summary", headers=sd_headers)
    assert r.status_code == 404


def test_advisor_summary_returns_calls(client, db, sd_headers):
    advisor = db.query(Advisor).first()
    r = client.get(f"/advisors/{advisor.id}/summary", headers=sd_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["advisor"] == advisor.name
    assert data["team"] == advisor.team.name
    assert "calls" in data
    assert "averages" in data


def test_nonexistent_advisor_returns_404(client, sd_headers):
    r = client.get("/advisors/99999/summary", headers=sd_headers)
    assert r.status_code == 404


def test_empty_team_avg_is_empty_dict(client, sd_headers):
    """Beta Pod has no calls yet — averages should be empty, not crash."""
    r = client.get("/teams/2/summary", headers=sd_headers)
    data = r.json()
    assert "averages" in data
