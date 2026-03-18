"""Tests for UserProfile model and service layer."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base
from users.models import UserProfile
from users.service import (
    InvalidWeightsError,
    create_user,
    get_user,
    list_users,
    update_weights,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_create_user(db_session: Session):
    user = create_user(db_session, "wendy", "Wendy")
    assert user.id is not None
    assert user.username == "wendy"
    assert user.display_name == "Wendy"
    assert user.topic_weights == "{}"
    assert user.created_at is not None


def test_get_user(db_session: Session):
    create_user(db_session, "wendy", "Wendy")
    found = get_user(db_session, "wendy")
    assert found is not None
    assert found.username == "wendy"


def test_get_user_not_found(db_session: Session):
    result = get_user(db_session, "nonexistent")
    assert result is None


def test_update_weights_valid(db_session: Session):
    create_user(db_session, "wendy", "Wendy")
    weights = {"ai": 2.5, "crypto": 1.0, "macro": 0.5}
    user = update_weights(db_session, "wendy", weights)
    assert user is not None
    stored = json.loads(user.topic_weights)
    assert stored == weights


def test_update_weights_invalid_topic(db_session: Session):
    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(InvalidWeightsError, match="Unknown topic"):
        update_weights(db_session, "wendy", {"bogus_topic": 1.0})


def test_update_weights_out_of_range(db_session: Session):
    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(InvalidWeightsError, match="out of range"):
        update_weights(db_session, "wendy", {"ai": 5.0})


def test_update_weights_immutability(db_session: Session):
    """Updating weights should not mutate the input dict."""
    create_user(db_session, "wendy", "Wendy")
    original_weights = {"ai": 1.0, "crypto": 2.0}
    snapshot = dict(original_weights)
    update_weights(db_session, "wendy", original_weights)
    assert original_weights == snapshot


def test_duplicate_username_raises(db_session: Session):
    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(IntegrityError):
        create_user(db_session, "wendy", "Wendy 2")
