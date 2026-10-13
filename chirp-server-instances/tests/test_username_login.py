"""0.5.10.s: usernames typed on an iPhone ("Josh ", capitalised) still log in."""
import os
import sys

from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.api.auth import find_by_username, username_taken  # noqa: E402

Base = declarative_base()


class U(Base):
    __tablename__ = "u"
    username = Column(String, primary_key=True)


def _db(*names):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add_all([U(username=n) for n in names])
    db.commit()
    return db


def test_capitalised_and_padded_username_matches():
    db = _db("josh", "annie")
    assert find_by_username(db, U, "Josh ").username == "josh"
    assert find_by_username(db, U, " ANNIE").username == "annie"
    assert find_by_username(db, U, "nobody") is None
    assert find_by_username(db, U, "  ") is None


def test_exact_match_wins_and_case_twins_stay_exact():
    db = _db("Sam", "sam")
    assert find_by_username(db, U, "Sam").username == "Sam"
    assert find_by_username(db, U, "sam").username == "sam"
    assert find_by_username(db, U, "SAM") is None   # ambiguous


def test_new_usernames_checked_without_case():
    db = _db("josh")
    assert username_taken(db, U, "Josh")
    assert username_taken(db, U, " josh ")
    assert not username_taken(db, U, "annie")


def test_rate_limit_key_uses_forwarded_address():
    from types import SimpleNamespace
    from app.api.auth import _login_rate_limit_key
    proxy = SimpleNamespace(host="172.17.0.20")
    a = SimpleNamespace(headers={"x-forwarded-for": "100.71.205.108, 172.17.0.20"}, client=proxy)
    b = SimpleNamespace(headers={"cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "10.0.0.1"}, client=proxy)
    c = SimpleNamespace(headers={}, client=proxy)
    assert _login_rate_limit_key("Annie ", a) == "annie:100.71.205.108"
    assert _login_rate_limit_key("annie", b) == "annie:203.0.113.9"
    assert _login_rate_limit_key("annie", c) == "annie:172.17.0.20"
