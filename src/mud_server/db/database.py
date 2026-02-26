"""Compatibility DB symbol surface for refactored repository modules.

This module intentionally provides a stable import path (``mud_server.db.database``)
while the concrete SQL implementations live in focused repository modules under
``mud_server.db``.

Design goals:
- Preserve existing call-site imports during the 0.3.10 refactor window.
- Keep exported symbols explicit so accidental API drift is visible in review.
- Avoid per-call wrapper indirection now that repository modules are decoupled.

Implementation notes:
- Public/runtime call sites should prefer ``mud_server.db.facade``.
- This compatibility module re-exports both public symbols and selected private
  helpers still referenced by focused DB tests.
- New database behaviors should be implemented in repository modules, then
  re-exported here only when part of the compatibility contract.
"""

from __future__ import annotations

from mud_server.db.admin_repo import (
    _quote_identifier,
    get_active_connections,
    get_all_chat_messages,
    get_all_sessions,
    get_all_users,
    get_all_users_detailed,
    get_character_locations,
    get_schema_map,
    get_table_names,
    get_table_rows,
    list_tables,
)
from mud_server.db.axis_repo import (
    _build_character_state_snapshot,
    _extract_axis_ordering_values,
    _fetch_character_axis_scores,
    _flatten_entity_axis_labels,
    _generate_state_seed,
    _get_axis_policy_hash,
    _refresh_character_current_snapshot,
    _resolve_axis_label_for_score,
    _resolve_axis_score_for_label,
    _seed_character_axis_scores,
    _seed_character_state_snapshot,
    apply_entity_state_to_character,
    get_character_axis_state,
    seed_axis_registry,
)
from mud_server.db.characters_repo import (
    _create_default_character,
    _generate_default_character_name,
    _resolve_character_name,
    _seed_character_location,
    character_exists,
    create_character_for_user,
    delete_character,
    get_character_by_id,
    get_character_by_name,
    get_character_by_name_in_world,
    get_character_inventory,
    get_character_name_by_id,
    get_character_room,
    get_characters_in_room,
    get_user_characters,
    resolve_character_name,
    set_character_inventory,
    set_character_room,
    tombstone_character,
)
from mud_server.db.chat_repo import add_chat_message, get_room_messages, prune_chat_messages
from mud_server.db.connection import get_connection
from mud_server.db.connection import get_db_path as _get_db_path
from mud_server.db.constants import DEFAULT_WORLD_ID
from mud_server.db.events_repo import (
    _get_or_create_event_type_id,
    _resolve_axis_id,
    apply_axis_event,
    get_character_axis_events,
)
from mud_server.db.schema import (
    create_session_invariant_triggers as _create_session_invariant_triggers,
)
from mud_server.db.schema import ensure_character_state_columns as _ensure_character_state_columns
from mud_server.db.schema import init_database
from mud_server.db.sessions_repo import (
    cleanup_expired_sessions,
    clear_all_sessions,
    create_session,
    get_active_characters,
    get_active_session_count,
    get_session_by_id,
    remove_session_by_id,
    remove_sessions_for_character,
    remove_sessions_for_character_count,
    remove_sessions_for_user,
    set_session_character,
    update_session_activity,
)
from mud_server.db.types import AxisRegistrySeedStats
from mud_server.db.users_repo import (
    activate_user,
    change_password_for_user,
    cleanup_expired_guest_accounts,
    create_user_with_password,
    deactivate_user,
    delete_user,
    get_user_account_origin,
    get_user_id,
    get_user_role,
    get_username_by_id,
    is_user_active,
    set_user_role,
    tombstone_user,
    unlink_characters_for_user,
    user_exists,
    verify_password_for_user,
)
from mud_server.db.worlds_repo import (
    _count_user_characters_in_world,
    _query_world_rows,
    _resolve_world_access_for_row,
    _user_has_world_permission,
    can_user_access_world,
    get_user_character_count_for_world,
    get_world_access_decision,
    get_world_admin_rows,
    get_world_by_id,
    list_worlds,
    list_worlds_for_user,
)

__all__ = [
    "AxisRegistrySeedStats",
    "DEFAULT_WORLD_ID",
    "_build_character_state_snapshot",
    "_count_user_characters_in_world",
    "_create_default_character",
    "_create_session_invariant_triggers",
    "_ensure_character_state_columns",
    "_extract_axis_ordering_values",
    "_fetch_character_axis_scores",
    "_flatten_entity_axis_labels",
    "_generate_default_character_name",
    "_generate_state_seed",
    "_get_axis_policy_hash",
    "_get_db_path",
    "_get_or_create_event_type_id",
    "_query_world_rows",
    "_quote_identifier",
    "_refresh_character_current_snapshot",
    "_resolve_axis_id",
    "_resolve_axis_label_for_score",
    "_resolve_axis_score_for_label",
    "_resolve_character_name",
    "_resolve_world_access_for_row",
    "_seed_character_axis_scores",
    "_seed_character_location",
    "_seed_character_state_snapshot",
    "_user_has_world_permission",
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
]
