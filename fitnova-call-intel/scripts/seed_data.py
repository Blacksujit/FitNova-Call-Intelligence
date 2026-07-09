"""Seed the database with one Org, two Teams, 3 Advisors per team, and demo users."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext
from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import Org, Team, Advisor, User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed():
    init_db()
    session = get_session()
    try:
        if session.query(Org).first():
            print("DB already seeded, skipping.")
            return

        org = Org(name="FitNova")
        session.add(org)
        session.flush()

        alpha = Team(org_id=org.id, name="Alpha Pod")
        beta = Team(org_id=org.id, name="Beta Pod")
        session.add_all([alpha, beta])
        session.flush()

        advisors = [
            Advisor(team_id=alpha.id, name="Priya Sharma", email="priya@fitnova.in"),
            Advisor(team_id=alpha.id, name="Rahul Verma", email="rahul@fitnova.in"),
            Advisor(team_id=alpha.id, name="Sneha Kapoor", email="sneha@fitnova.in"),
            Advisor(team_id=beta.id, name="Ananya Patel", email="ananya@fitnova.in"),
            Advisor(team_id=beta.id, name="Vikram Singh", email="vikram@fitnova.in"),
            Advisor(team_id=beta.id, name="Arjun Nair", email="arjun@fitnova.in"),
        ]
        session.add_all(advisors)
        session.flush()

        users = [
            User(
                email="director@fitnova.in", password_hash=pwd.hash("admin123"),
                name="Sales Director", role="sales_director", org_id=org.id,
            ),
            User(
                email="alpha_lead@fitnova.in", password_hash=pwd.hash("lead123"),
                name="Alpha Lead", role="team_leader", org_id=org.id, team_id=alpha.id,
            ),
            User(
                email="beta_lead@fitnova.in", password_hash=pwd.hash("lead123"),
                name="Beta Lead", role="team_leader", org_id=org.id, team_id=beta.id,
            ),
            User(
                email="priya@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Priya Sharma", role="advisor", org_id=org.id,
                team_id=alpha.id, advisor_id=advisors[0].id,
            ),
            User(
                email="rahul@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Rahul Verma", role="advisor", org_id=org.id,
                team_id=alpha.id, advisor_id=advisors[1].id,
            ),
            User(
                email="sneha@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Sneha Kapoor", role="advisor", org_id=org.id,
                team_id=alpha.id, advisor_id=advisors[2].id,
            ),
            User(
                email="ananya@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Ananya Patel", role="advisor", org_id=org.id,
                team_id=beta.id, advisor_id=advisors[3].id,
            ),
            User(
                email="vikram@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Vikram Singh", role="advisor", org_id=org.id,
                team_id=beta.id, advisor_id=advisors[4].id,
            ),
            User(
                email="arjun@fitnova.in", password_hash=pwd.hash("advisor123"),
                name="Arjun Nair", role="advisor", org_id=org.id,
                team_id=beta.id, advisor_id=advisors[5].id,
            ),
        ]
        session.add_all(users)
        session.commit()
        print(f"Seeded: {org.name} — 2 teams, {len(advisors)} advisors, {len(users)} users.")
        print()
        print("Demo logins:")
        print("  Sales Director : director@fitnova.in / admin123")
        print("  Team Leaders   : alpha_lead@fitnova.in / lead123")
        print("                  : beta_lead@fitnova.in / lead123")
        print("  Advisors       : <advisor-email> / advisor123")
        print("                  (priya, rahul, sneha, ananya, vikram, arjun @fitnova.in)")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
