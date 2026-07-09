from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


class CallStatus(str, enum.Enum):
    pending = "pending"
    ingested = "ingested"
    transcribed = "transcribed"
    analyzed = "analyzed"
    failed = "failed"
    non_sales_call = "non_sales_call"


class TagStatus(str, enum.Enum):
    active = "active"
    contested = "contested"
    dismissed = "dismissed"


class Org(Base):
    __tablename__ = "orgs"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    teams = relationship("Team", back_populates="org", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    org = relationship("Org", back_populates="teams")
    advisors = relationship("Advisor", back_populates="team", cascade="all, delete-orphan")


class Advisor(Base):
    __tablename__ = "advisors"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    team = relationship("Team", back_populates="advisors")
    calls = relationship("Call", back_populates="advisor", cascade="all, delete-orphan")


class Call(Base):
    __tablename__ = "calls"
    id = Column(Integer, primary_key=True)
    advisor_id = Column(Integer, ForeignKey("advisors.id"), nullable=False)
    source_type = Column(String(100), nullable=False)
    external_call_id = Column(String(255), nullable=False)
    audio_hash = Column(String(64), unique=True, nullable=False)
    status = Column(String(50), default=CallStatus.pending.value)
    diarization_quality = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    advisor = relationship("Advisor", back_populates="calls")
    segments = relationship("Segment", back_populates="call", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="call", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="call", cascade="all, delete-orphan")


class Segment(Base):
    __tablename__ = "segments"
    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False)
    speaker = Column(String(50), nullable=False)
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    call = relationship("Call", back_populates="segments")


class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False)
    dimension = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="scores")


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False)
    category = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)
    timestamp_ms = Column(Integer)
    quoted_line = Column(Text)
    reason = Column(Text)
    status = Column(String(50), default=TagStatus.active.value)
    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="tags")
    contests = relationship("Contest", back_populates="tag", cascade="all, delete-orphan")


class Contest(Base):
    __tablename__ = "contests"
    id = Column(Integer, primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), nullable=False)
    advisor_comment = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tag = relationship("Tag", back_populates="contests")
