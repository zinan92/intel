"""User profile CRUD operations with weight validation."""

import json

from sqlalchemy.orm import Session

from users.models import UserProfile

VALID_TOPICS = frozenset([
    "ai", "crypto", "macro", "geopolitics", "china-market", "us-market",
    "sector/tech", "sector/finance", "sector/energy",
    "trading", "regulation", "earnings", "commodities",
])

_WEIGHT_MIN = 0.0
_WEIGHT_MAX = 3.0


class InvalidWeightsError(ValueError):
    """Raised when topic weights fail validation."""


def create_user(session: Session, username: str, display_name: str) -> UserProfile:
    """Create a new user profile."""
    user = UserProfile(username=username, display_name=display_name)
    session.add(user)
    session.commit()
    return user


def get_user(session: Session, username: str) -> UserProfile | None:
    """Look up a user by username. Returns None if not found."""
    return session.query(UserProfile).filter_by(username=username).first()


def list_users(session: Session) -> list[UserProfile]:
    """Return all user profiles ordered by username."""
    return session.query(UserProfile).order_by(UserProfile.username).all()


def update_weights(
    session: Session, username: str, weights: dict[str, float]
) -> UserProfile | None:
    """Validate and persist topic weights for a user.

    Raises InvalidWeightsError if topics are unknown or values out of range.
    Returns None if the user does not exist.
    """
    unknown = set(weights.keys()) - VALID_TOPICS
    if unknown:
        raise InvalidWeightsError(
            f"Unknown topic(s): {', '.join(sorted(unknown))}"
        )

    for topic, value in weights.items():
        if not (_WEIGHT_MIN <= value <= _WEIGHT_MAX):
            raise InvalidWeightsError(
                f"Weight for '{topic}' is {value}, "
                f"out of range [{_WEIGHT_MIN}, {_WEIGHT_MAX}]"
            )

    user = get_user(session, username)
    if user is None:
        return None

    new_weights_json = json.dumps(weights, ensure_ascii=False)
    user.topic_weights = new_weights_json
    session.commit()
    return user
