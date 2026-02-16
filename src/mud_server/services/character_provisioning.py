"""
Shared character provisioning service used by admin and player APIs.

Why this module exists:
    The codebase previously duplicated character creation logic across route
    handlers. This service centralizes deterministic name generation, DB create
    retries, and optional entity-state seeding so every caller follows one
    canonical behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from secrets import randbelow
from typing import Any

import requests

from mud_server.config import config
from mud_server.db import database

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CharacterProvisioningResult:
    """
    Result payload for generated-character provisioning.

    Attributes:
        success: True when provisioning completed and DB rows were persisted.
        reason: Stable reason key for caller-level error mapping.
        message: Human-readable status message.
        character_id: Created character id when successful.
        character_name: Created character name when successful.
        world_id: Target world id for the created character.
        seed: Deterministic provisioning seed used for name/entity generation.
        entity_state: Raw entity payload when fetched successfully.
        entity_state_error: Non-fatal warning when entity seeding fails.
    """

    success: bool
    reason: str
    message: str
    character_id: int | None = None
    character_name: str | None = None
    world_id: str | None = None
    seed: int | None = None
    entity_state: dict[str, Any] | None = None
    entity_state_error: str | None = None


def generate_provisioning_seed() -> int:
    """
    Generate a replayable, non-zero seed for provisioning flows.

    We intentionally use ``secrets.randbelow`` rather than module-global RNG
    state to avoid coupling name/entity generation to gameplay randomness.
    """
    return randbelow(2_147_483_647) + 1


def _fetch_generated_name(
    seed: int,
    *,
    class_key: str = "first_name",
) -> tuple[str | None, str | None]:
    """
    Request one name token from the external name-generation API.

    Returns:
        Tuple ``(name, error_message)``. On success, ``error_message`` is None.
    """
    if not config.integrations.namegen_enabled:
        return None, "Name generation integration is disabled."

    base_url = config.integrations.namegen_base_url.strip().rstrip("/")
    if not base_url:
        return None, "Name generation integration is enabled but no base URL is configured."

    endpoint = f"{base_url}/api/generate"
    payload = {
        "class_key": class_key,
        "package_id": 1,
        "syllable_key": "all",
        "generation_count": 1,
        "unique_only": True,
        "output_format": "json",
        "render_style": "title",
        "seed": seed,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=config.integrations.namegen_timeout_seconds,
        )
        if response.status_code != 200:
            return None, f"Name generation API returned HTTP {response.status_code}."
        body = response.json()
        if not isinstance(body, dict):
            return None, "Name generation API returned a non-object payload."
        names = body.get("names")
        if not isinstance(names, list) or not names or not isinstance(names[0], str):
            return None, "Name generation API did not return a valid name."
        generated_name = names[0].strip()
        if not generated_name:
            return None, "Name generation API returned an empty name."
        return generated_name, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Name generation API request failed: %s", exc)
        return None, "Name generation API unavailable."
    except ValueError:
        logger.warning("Name generation API returned invalid JSON.")
        return None, "Name generation API returned invalid JSON."


def fetch_generated_full_name(seed: int) -> tuple[str | None, str | None]:
    """
    Generate a deterministic ``first last`` character name for provisioning.

    The same base seed is used for both lookups with an offset for the surname
    so retry attempts remain deterministic across deployments.
    """
    first_name, first_error = _fetch_generated_name(seed, class_key="first_name")
    if first_name is None:
        return None, first_error or "Unable to generate first name."

    last_name, last_error = _fetch_generated_name(seed + 1, class_key="last_name")
    if last_name is None:
        return None, last_error or "Unable to generate last name."

    full_name = f"{first_name.strip()} {last_name.strip()}".strip()
    if " " not in full_name:
        return None, "Name generation API returned an invalid full name."
    return full_name, None


def fetch_entity_state_for_seed(seed: int) -> tuple[dict[str, Any] | None, str | None]:
    """
    Fetch an optional entity-state payload for a provisioning seed.

    Entity-state integration is non-fatal: character creation continues even if
    the upstream call fails.
    """
    if not config.integrations.entity_state_enabled:
        return None, None

    base_url = config.integrations.entity_state_base_url.strip().rstrip("/")
    if not base_url:
        return None, "Entity state integration is enabled but no base URL is configured."

    endpoint = f"{base_url}/api/entity"
    payload = {
        "seed": seed,
        "include_prompts": config.integrations.entity_state_include_prompts,
    }
    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=config.integrations.entity_state_timeout_seconds,
        )
        if response.status_code != 200:
            return None, f"Entity state API returned HTTP {response.status_code}."
        body = response.json()
        if not isinstance(body, dict):
            return None, "Entity state API returned a non-object payload."
        return body, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Entity state API request failed during provisioning: %s", exc)
        return None, "Entity state API unavailable."
    except ValueError:
        logger.warning("Entity state API returned invalid JSON during provisioning.")
        return None, "Entity state API returned invalid JSON."


def get_world_slot_capacity(user_id: int, world_id: str) -> tuple[int, int]:
    """
    Return ``(current_count, slot_limit)`` for account ownership in one world.
    """
    policy = config.resolve_world_character_policy(world_id)
    slot_limit = max(0, int(policy.slot_limit_per_account))
    current_count = database.get_user_character_count_for_world(user_id, world_id)
    return current_count, slot_limit


def provision_generated_character_for_user(
    *,
    user_id: int,
    world_id: str,
    max_attempts: int = 8,
) -> CharacterProvisioningResult:
    """
    Create a generated-name character with optional entity-state axis seeding.

    The flow is intentionally deterministic per retry sequence:
        1. Resolve slot capacity early and fail fast if world budget is full.
        2. Generate ``first last`` names from deterministic seeds.
        3. Retry on unique-name collisions.
        4. Apply optional entity-state deltas as a non-fatal post-step.
    """
    current_count, slot_limit = get_world_slot_capacity(user_id, world_id)
    if current_count >= slot_limit:
        return CharacterProvisioningResult(
            success=False,
            reason="slot_limit_reached",
            message=(
                "No character slots are available in this world. "
                f"{current_count}/{slot_limit} already used."
            ),
        )

    base_seed = generate_provisioning_seed()
    chosen_name: str | None = None
    chosen_seed: int | None = None
    for attempt in range(max_attempts):
        candidate_seed = base_seed + attempt
        generated_name, name_error = fetch_generated_full_name(candidate_seed)
        if generated_name is None:
            return CharacterProvisioningResult(
                success=False,
                reason="name_generation_failed",
                message=name_error or "Unable to generate character name.",
            )

        if database.create_character_for_user(
            user_id,
            generated_name,
            world_id=world_id,
            state_seed=candidate_seed,
        ):
            chosen_name = generated_name
            chosen_seed = candidate_seed
            break

    if chosen_name is None or chosen_seed is None:
        return CharacterProvisioningResult(
            success=False,
            reason="name_collision_exhausted",
            message="Unable to allocate a unique generated character name. Try again.",
        )

    character = database.get_character_by_name(chosen_name)
    if character is None:
        return CharacterProvisioningResult(
            success=False,
            reason="character_lookup_failed",
            message="Character creation did not persist correctly.",
        )

    character_id = int(character["id"])
    entity_state, entity_state_error = fetch_entity_state_for_seed(chosen_seed)
    if entity_state is not None:
        try:
            database.apply_entity_state_to_character(
                character_id=character_id,
                world_id=world_id,
                entity_state=entity_state,
                seed=chosen_seed,
            )
        except Exception:  # nosec B110 - caller receives controlled error payload
            logger.exception(
                "Failed to apply entity-state payload for character %s",
                character_id,
            )
            entity_state_error = "Entity state axis seeding failed."

    return CharacterProvisioningResult(
        success=True,
        reason="ok",
        message="Character created successfully.",
        character_id=character_id,
        character_name=chosen_name,
        world_id=world_id,
        seed=chosen_seed,
        entity_state=entity_state,
        entity_state_error=entity_state_error,
    )
