import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import User
from passlib.context import CryptContext
init_db()
db = get_session()
u = db.query(User).filter(User.email == "priya@fitnova.in").first()
pwd = CryptContext(schemes=["bcrypt"])
print(f"Hash: {u.hashed_password[:30]}...")
print(f"Verify 'test123': {pwd.verify('test123', u.hashed_password)}")
print(f"Verify 'password': {pwd.verify('password', u.hashed_password)}")
db.close()
