"""Pydantic models for API requests and responses."""

from pydantic import BaseModel
from typing import List, Optional


class LoginRequest(BaseModel):
    username: str


class CommandRequest(BaseModel):
    session_id: str
    command: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    session_id: Optional[str] = None


class CommandResponse(BaseModel):
    success: bool
    message: str


class StatusResponse(BaseModel):
    active_players: List[str]
    current_room: Optional[str]
    inventory: str
