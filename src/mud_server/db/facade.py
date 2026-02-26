"""Public DB facade module.

This module is the app-facing import surface for database operations.

Design goals:
1. Keep application layers importing a stable module path (``mud_server.db.facade``).
2. Enforce an explicit facade API contract for the 0.3.10 refactor phase.
3. Keep runtime call forwarding compatible with tests that monkeypatch
   ``mud_server.db.database.<symbol>``.

Implementation notes:
- ``_PUBLIC_API`` is intentionally explicit and versioned by source control.
  New facade symbols must be added here deliberately.
- ``_REMOVED_API`` lists legacy names removed during the refactor so callers
  get a clear upgrade message instead of a generic attribute error.
- Public callables are exposed as lightweight forwarding wrappers that resolve
  the current backing attribute at call time. This avoids dynamic module-class
  mutation while preserving monkeypatch compatibility for call sites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any as _Any

from mud_server.db import database as _database

if TYPE_CHECKING:
    # Type-checking view: expose database module symbols with precise types.
    # Runtime forwarding still happens through ``__getattr__`` and module
    # attribute forwarding below.
    from mud_server.db.database import *  # noqa: F401,F403


# Explicitly versioned public facade contract for app-layer imports.
_PUBLIC_API: tuple[str, ...] = (
    "DEFAULT_WORLD_ID",
    "activate_user",
    "add_chat_message",
    "apply_axis_event",
    "apply_entity_state_to_character",
    "can_user_access_world",
    "change_password_for_user",
    "character_exists",
    "cleanup_expired_guest_accounts",
    "cleanup_expired_sessions",
    "clear_all_sessions",
    "create_character_for_user",
    "create_session",
    "create_user_with_password",
    "deactivate_user",
    "delete_character",
    "delete_user",
    "get_active_characters",
    "get_active_connections",
    "get_active_session_count",
    "get_all_chat_messages",
    "get_all_sessions",
    "get_all_users",
    "get_all_users_detailed",
    "get_character_axis_events",
    "get_character_axis_state",
    "get_character_by_id",
    "get_character_by_name",
    "get_character_by_name_in_world",
    "get_character_inventory",
    "get_character_locations",
    "get_character_name_by_id",
    "get_character_room",
    "get_characters_in_room",
    "get_connection",
    "get_room_messages",
    "get_schema_map",
    "get_session_by_id",
    "get_table_names",
    "get_table_rows",
    "get_user_account_origin",
    "get_user_character_count_for_world",
    "get_user_characters",
    "get_user_id",
    "get_user_role",
    "get_username_by_id",
    "get_world_access_decision",
    "get_world_admin_rows",
    "get_world_by_id",
    "init_database",
    "is_user_active",
    "list_tables",
    "list_worlds",
    "list_worlds_for_user",
    "prune_chat_messages",
    "remove_session_by_id",
    "remove_sessions_for_character",
    "remove_sessions_for_character_count",
    "remove_sessions_for_user",
    "resolve_character_name",
    "seed_axis_registry",
    "set_character_inventory",
    "set_character_room",
    "set_session_character",
    "set_user_role",
    "tombstone_character",
    "tombstone_user",
    "unlink_characters_for_user",
    "update_session_activity",
    "user_exists",
    "verify_password_for_user",
)


# Legacy aliases removed in the 0.3.10 breaking-change window.
_REMOVED_API: tuple[str, ...] = (
    "activate_player",
    "cleanup_temporary_accounts",
    "create_player_with_password",
    "deactivate_player",
    "delete_player",
    "get_active_players",
    "get_all_players",
    "get_all_players_detailed",
    "get_player_account_origin",
    "get_player_inventory",
    "get_player_locations",
    "get_player_role",
    "get_player_room",
    "get_players_in_room",
    "is_player_active",
    "player_exists",
    "remove_session",
    "set_player_inventory",
    "set_player_role",
    "set_player_room",
)


def _resolve_public_attr(name: str) -> _Any:
    """Resolve a facade attribute against the explicit public API contract."""
    if name in _REMOVED_API:
        raise AttributeError(
            f"mud_server.db.facade.{name} was removed in 0.3.10; "
            "use the canonical user/character/session API instead."
        )
    if name not in _PUBLIC_API:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    try:
        return getattr(_database, name)
    except AttributeError as exc:
        raise AttributeError(
            f"mud_server.db.facade.{name} is declared public but missing from mud_server.db.database"
        ) from exc


def _build_callable_forwarder(name: str):
    """Create a forwarding callable that resolves the current DB symbol on call."""

    def _forwarder(*args: _Any, **kwargs: _Any) -> _Any:
        target = _resolve_public_attr(name)
        if not callable(target):
            raise TypeError(
                f"mud_server.db.facade.{name} is not callable in mud_server.db.database"
            )
        return target(*args, **kwargs)

    _forwarder.__name__ = name
    _forwarder.__qualname__ = name
    _forwarder.__doc__ = (
        f"Forward to ``mud_server.db.database.{name}`` using runtime attribute lookup."
    )
    return _forwarder


def _materialize_public_api() -> None:
    """Populate module globals for the explicit facade contract."""
    for name in _PUBLIC_API:
        target = _resolve_public_attr(name)
        if callable(target):
            globals()[name] = _build_callable_forwarder(name)
            continue
        globals()[name] = target


_materialize_public_api()


def __getattr__(name: str) -> _Any:
    """Provide directed migration errors for removed legacy facade symbols."""
    if name in _REMOVED_API:
        raise AttributeError(
            f"mud_server.db.facade.{name} was removed in 0.3.10; "
            "use the canonical user/character/session API instead."
        )
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    """
    Return combined facade module names and explicit public API names.

    Using ``_PUBLIC_API`` instead of ``dir(_database)`` keeps shell
    introspection aligned with the explicit contract and avoids leaking
    implementation-only names.
    """
    return sorted(set(globals()) | set(_PUBLIC_API))


__all__ = list(_PUBLIC_API)
