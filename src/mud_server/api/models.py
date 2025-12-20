"""Pydantic models for API requests and responses."""

from pydantic import BaseModel
from typing import List, Optional, Any, Dict


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    password_confirm: str


class ChangePasswordRequest(BaseModel):
    session_id: str
    old_password: str
    new_password: str


class UserManagementRequest(BaseModel):
    session_id: str
    target_username: str
    action: str  # "promote", "demote", "ban", "unban", "change_role"
    new_role: Optional[str] = None


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
    role: Optional[str] = None


class RegisterResponse(BaseModel):
    success: bool
    message: str


class CommandResponse(BaseModel):
    success: bool
    message: str


class StatusResponse(BaseModel):
    active_players: List[str]
    current_room: Optional[str]
    inventory: str


class UserListResponse(BaseModel):
    users: List[Dict[str, Any]]


class DatabasePlayersResponse(BaseModel):
    players: List[Dict[str, Any]]


class DatabaseSessionsResponse(BaseModel):
    sessions: List[Dict[str, Any]]


class DatabaseChatResponse(BaseModel):
    messages: List[Dict[str, Any]]


class UserManagementResponse(BaseModel):
    success: bool
    message: str
