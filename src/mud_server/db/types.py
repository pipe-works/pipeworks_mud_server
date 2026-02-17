"""Shared DB-layer dataclasses for repository contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class WorldAccessDecision:
    """
    Policy resolution result for account access and character creation in a world.

    Attributes:
        world_id: Target world identifier.
        can_access: True when the account may enter/select this world.
        can_create: True when the account may create another character there.
        access_mode: Effective world creation mode (open/invite).
        naming_mode: Effective naming mode (generated/manual).
        slot_limit_per_account: Max characters allowed for the account in this world.
        current_character_count: Existing characters owned by the account in this world.
        has_permission_grant: True when a world_permissions invite/grant exists.
        has_existing_character: True when the account already owns a character there.
        reason: Machine-friendly reason key for denials (for API/UI messaging).
    """

    world_id: str
    can_access: bool
    can_create: bool
    access_mode: str
    naming_mode: str
    slot_limit_per_account: int
    current_character_count: int
    has_permission_grant: bool
    has_existing_character: bool
    reason: str


@dataclass(slots=True)
class AxisRegistrySeedStats:
    """
    Summary of axis registry seeding work performed.

    Attributes:
        axes_upserted: Number of axis rows inserted or updated.
        axis_values_inserted: Number of axis_value rows inserted.
        axes_missing_thresholds: Number of axes that had no thresholds entry.
        axis_values_skipped: Number of axis_value rows skipped due to missing data.
    """

    axes_upserted: int
    axis_values_inserted: int
    axes_missing_thresholds: int
    axis_values_skipped: int
