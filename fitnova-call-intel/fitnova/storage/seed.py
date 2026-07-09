"""Seed logic callable from tests and scripts."""

from passlib.context import CryptContext
from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import Org, Team, Advisor, User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_data():
    session = get_session()
    try:
        if session.query(Org).first():
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
        session.commit()
    finally:
        session.close()


def seed_users():
    session = get_session()
    try:
        if session.query(User).first():
            return
        org = session.query(Org).first()
        alpha = session.query(Team).filter(Team.name == "Alpha Pod").first()
        beta = session.query(Team).filter(Team.name == "Beta Pod").first()
        advisors = {a.email: a for a in session.query(Advisor).all()}
        users = [
            User(email="director@fitnova.in", password_hash=pwd.hash("admin123"),
                 name="Sales Director", role="sales_director", org_id=org.id),
            User(email="alpha_lead@fitnova.in", password_hash=pwd.hash("lead123"),
                 name="Alpha Lead", role="team_leader", org_id=org.id, team_id=alpha.id),
            User(email="beta_lead@fitnova.in", password_hash=pwd.hash("lead123"),
                 name="Beta Lead", role="team_leader", org_id=org.id, team_id=beta.id),
            User(email="priya@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Priya Sharma", role="advisor", org_id=org.id,
                 team_id=alpha.id, advisor_id=advisors["priya@fitnova.in"].id),
            User(email="rahul@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Rahul Verma", role="advisor", org_id=org.id,
                 team_id=alpha.id, advisor_id=advisors["rahul@fitnova.in"].id),
            User(email="sneha@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Sneha Kapoor", role="advisor", org_id=org.id,
                 team_id=alpha.id, advisor_id=advisors["sneha@fitnova.in"].id),
            User(email="ananya@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Ananya Patel", role="advisor", org_id=org.id,
                 team_id=beta.id, advisor_id=advisors["ananya@fitnova.in"].id),
            User(email="vikram@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Vikram Singh", role="advisor", org_id=org.id,
                 team_id=beta.id, advisor_id=advisors["vikram@fitnova.in"].id),
            User(email="arjun@fitnova.in", password_hash=pwd.hash("advisor123"),
                 name="Arjun Nair", role="advisor", org_id=org.id,
                 team_id=beta.id, advisor_id=advisors["arjun@fitnova.in"].id),
        ]
        session.add_all(users)
        session.commit()
    finally:
        session.close()
