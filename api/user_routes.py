"""User profile API endpoints."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.database import get_session
from users.service import (
    InvalidWeightsError,
    create_user,
    get_user,
    list_users,
    update_weights,
)

user_router = APIRouter(prefix="/api")


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)


class UpdateWeightsRequest(BaseModel):
    weights: dict[str, float]


def _user_response(user) -> dict[str, Any]:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "topic_weights": json.loads(user.topic_weights or "{}"),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@user_router.post("/users")
def create_user_endpoint(req: CreateUserRequest) -> dict[str, Any]:
    session = get_session()
    try:
        from sqlalchemy.exc import IntegrityError
        try:
            user = create_user(session, req.username, req.display_name)
            return _user_response(user)
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="Username already exists")
    finally:
        session.close()


@user_router.get("/users")
def list_users_endpoint() -> list[dict[str, Any]]:
    session = get_session()
    try:
        users = list_users(session)
        return [_user_response(u) for u in users]
    finally:
        session.close()


@user_router.get("/users/{username}")
def get_user_endpoint(username: str) -> dict[str, Any]:
    session = get_session()
    try:
        user = get_user(session, username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_response(user)
    finally:
        session.close()


@user_router.put("/users/{username}/weights")
def update_weights_endpoint(username: str, req: UpdateWeightsRequest) -> dict[str, Any]:
    session = get_session()
    try:
        try:
            user = update_weights(session, username, req.weights)
        except InvalidWeightsError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_response(user)
    finally:
        session.close()
