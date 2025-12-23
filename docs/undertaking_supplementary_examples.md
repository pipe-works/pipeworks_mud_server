# The Undertaking: Supplementary Code Examples and Best Practices

This document provides additional code examples, interaction patterns, and best practices for implementing The Undertaking's systems.

---

## Part 1: Content Library Structure (JSON)

### 1.1 Quirks Library

```json
{
  "quirks": [
    {
      "id": "quirk_panics_when_watched",
      "name": "Panics When Watched",
      "description": "You become flustered when observed by others",
      "category": "behavioral",
      "rarity": "common",
      "rarity_weight": 10,
      "mechanical_effect": {
        "trigger": "when_observed_by_npc",
        "trigger_description": "An NPC is watching the action",
        "axis_modifiers": {
          "stability": -2,
          "precision": -1
        },
        "severity": "moderate"
      },
      "discovery_method": "visible_on_issuance",
      "interaction_notes": "Interacts with high cunning to provide interpretability bonus"
    },
    {
      "id": "quirk_trembling_hands",
      "name": "Trembling Hands",
      "description": "Your hands shake slightly",
      "category": "physical",
      "rarity": "common",
      "rarity_weight": 8,
      "mechanical_effect": {
        "trigger": "always",
        "trigger_description": "Applies to all fine motor tasks",
        "axis_modifiers": {
          "precision": -1
        },
        "severity": "minor"
      },
      "discovery_method": "visible_on_issuance",
      "interaction_notes": "Affects fishing, crafting, writing, lockpicking"
    },
    {
      "id": "quirk_lucky_mishaps",
      "name": "Lucky Mishaps",
      "description": "Failures sometimes reinterpreted as successes",
      "category": "mental",
      "rarity": "rare",
      "rarity_weight": 3,
      "mechanical_effect": {
        "trigger": "on_failure",
        "trigger_description": "When an action would fail",
        "axis_modifiers": {
          "interpretability": 2
        },
        "severity": "major"
      },
      "discovery_method": "hidden_until_triggered",
      "interaction_notes": "Discovered only after first failure; provides narrative reinterpretation"
    },
    {
      "id": "quirk_obsessive_detail",
      "name": "Obsessive About Details",
      "description": "You focus too much on minor details",
      "category": "behavioral",
      "rarity": "uncommon",
      "rarity_weight": 5,
      "mechanical_effect": {
        "trigger": "on_success",
        "trigger_description": "When an action succeeds",
        "axis_modifiers": {
          "precision": 1,
          "timing": -1
        },
        "severity": "minor"
      },
      "discovery_method": "visible_on_issuance",
      "interaction_notes": "Improves precision but increases action time"
    },
    {
      "id": "quirk_risk_averse",
      "name": "Risk Averse",
      "description": "You avoid taking chances",
      "category": "behavioral",
      "rarity": "uncommon",
      "rarity_weight": 6,
      "mechanical_effect": {
        "trigger": "when_high_risk",
        "trigger_description": "When action has high failure risk",
        "axis_modifiers": {
          "stability": 1,
          "precision": 1
        },
        "severity": "minor"
      },
      "discovery_method": "visible_on_issuance",
      "interaction_notes": "Reduces risk in dangerous situations"
    }
  ]
}
```

### 1.2 Failings Library

```json
{
  "failings": [
    {
      "id": "failing_numeracy",
      "name": "Poor Numeracy",
      "description": "You struggle with calculations and counting",
      "severity": "moderate",
      "affected_attributes": ["book_learning"],
      "trigger_conditions": ["when_counting", "when_calculating", "when_managing_resources"],
      "mechanical_effect": {
        "effect_type": "miscalculation",
        "magnitude": "10-20%",
        "applies_to": "resource_management",
        "applies_even_on_success": true,
        "example": "Succeed at harvesting grain but miscalculate yield by 15%"
      }
    },
    {
      "id": "failing_impulse_control",
      "name": "Poor Impulse Control",
      "description": "You act too quickly in time-sensitive situations",
      "severity": "severe",
      "affected_attributes": ["patience"],
      "trigger_conditions": ["when_time_sensitive", "when_stressed"],
      "mechanical_effect": {
        "effect_type": "early_action",
        "magnitude": "0.5-1 second early",
        "applies_to": "timing_dependent_actions",
        "applies_even_on_success": true,
        "example": "Reel in fishing line too early, before fish is fully hooked"
      }
    },
    {
      "id": "failing_depth_perception",
      "name": "Poor Depth Perception",
      "description": "You misjudge distances and depths",
      "severity": "severe",
      "affected_attributes": ["spatial_sense"],
      "trigger_conditions": ["when_judging_distance", "when_climbing", "when_jumping"],
      "mechanical_effect": {
        "effect_type": "misjudgment",
        "magnitude": "10-30% error",
        "applies_to": "spatial_tasks",
        "applies_even_on_success": true,
        "example": "Jump across a gap but land too close to the edge"
      }
    },
    {
      "id": "failing_memory",
      "name": "Poor Memory",
      "description": "You forget details easily",
      "severity": "moderate",
      "affected_attributes": ["book_learning"],
      "trigger_conditions": ["when_recalling_information", "when_following_complex_instructions"],
      "mechanical_effect": {
        "effect_type": "information_loss",
        "magnitude": "20-30% of details forgotten",
        "applies_to": "knowledge_tasks",
        "applies_even_on_success": true,
        "example": "Remember the location of a place but forget key landmarks"
      }
    }
  ]
}
```

### 1.3 Useless Bits Library

```json
{
  "useless_bits": [
    {
      "id": "useless_obsolete_measures",
      "name": "Expert in Obsolete Measurement Systems",
      "description": "You can convert between fathoms, cubits, and hand-spans",
      "why_useless": "Nobody uses these measurements anymore",
      "triggers": ["when_measuring", "when_converting_units"],
      "mechanical_effect": {
        "applies_to": "measurement_tasks",
        "bonus": "precision +2 for obsolete measurements",
        "penalty": "precision -1 for modern measurements",
        "net_effect": "Usually negative"
      },
      "example_scenario": "A merchant asks you to measure cloth in meters. You're excellent at cubits but terrible at meters."
    },
    {
      "id": "useless_bridge_names",
      "name": "Knows Every Bridge by Name",
      "description": "You can name any bridge in the city",
      "why_useless": "But you don't know where they go",
      "triggers": ["when_navigating", "when_identifying_bridges"],
      "mechanical_effect": {
        "applies_to": "navigation_tasks",
        "bonus": "can identify any bridge",
        "penalty": "spatial_sense -2 for finding bridges",
        "net_effect": "Useless for navigation"
      },
      "example_scenario": "You need to cross the river. You know the bridge is called the Merchant's Span, but you're lost trying to find it."
    },
    {
      "id": "useless_mushroom_identification",
      "name": "Can Identify Any Mushroom",
      "description": "You know the name, habitat, and spore pattern of every mushroom",
      "why_useless": "You can't cook any of them",
      "triggers": ["when_foraging", "when_cooking"],
      "mechanical_effect": {
        "applies_to": "foraging_and_cooking",
        "bonus": "can identify mushrooms with precision +3",
        "penalty": "cooking_with_mushrooms -2",
        "net_effect": "Can find food but can't prepare it"
      },
      "example_scenario": "You forage and find a delicious mushroom. But when you try to cook it, you ruin the dish."
    },
    {
      "id": "useless_bureaucratic_procedure",
      "name": "Expert in Obsolete Bureaucratic Procedures",
      "description": "You know the correct procedure for filing complaints from 1987",
      "why_useless": "The system changed in 1988",
      "triggers": ["when_filing_paperwork", "when_dealing_with_bureaucracy"],
      "mechanical_effect": {
        "applies_to": "bureaucratic_tasks",
        "bonus": "paperwork_efficiency +2 for 1987 procedures",
        "penalty": "paperwork_efficiency -3 for current procedures",
        "net_effect": "Makes you slower at modern bureaucracy"
      },
      "example_scenario": "You file a complaint using the correct 1987 procedure. It's rejected because the system changed."
    },
    {
      "id": "useless_ancient_languages",
      "name": "Fluent in Three Dead Languages",
      "description": "You speak Archaic Goblin, Old Merchant Cant, and Forgotten Dwarvish",
      "why_useless": "Nobody speaks these languages anymore",
      "triggers": ["when_communicating", "when_reading_ancient_texts"],
      "mechanical_effect": {
        "applies_to": "communication_and_reading",
        "bonus": "can read ancient texts",
        "penalty": "modern_language_communication -1",
        "net_effect": "Useful only in rare situations"
      },
      "example_scenario": "You can read an ancient scroll, but you can't understand the modern merchant's accent."
    }
  ]
}
```

---

## Part 2: Item Quirks Library

```json
{
  "item_quirks": [
    {
      "id": "item_quirk_delayed_feedback",
      "name": "Delayed Feedback",
      "description": "This item provides delayed sensory feedback",
      "category": "sensory",
      "mechanical_effect": {
        "axis_modifiers": {
          "timing": 1
        },
        "applies_to_actions": ["fishing", "archery", "crafting"]
      },
      "interaction_with_character_quirks": {
        "quirk_patience_low": "Severely negative interaction",
        "quirk_obsessive_detail": "Positive interaction"
      },
      "context_dependent": true,
      "example": "A fishing pole with delayed feedback makes it harder for impatient goblins to detect bites"
    },
    {
      "id": "item_quirk_loose_mechanism",
      "name": "Loose Mechanism",
      "description": "This item's mechanism is loose and unpredictable",
      "category": "mechanical",
      "mechanical_effect": {
        "axis_modifiers": {
          "precision": -1,
          "stability": -1
        },
        "applies_to_actions": ["reeling", "winding", "precise_manipulation"]
      },
      "interaction_with_character_quirks": {
        "quirk_trembling_hands": "Negative interaction",
        "quirk_risk_averse": "Negative interaction"
      },
      "context_dependent": false,
      "example": "A loose reel on a fishing pole makes it harder to reel in smoothly"
    },
    {
      "id": "item_quirk_balanced_weight",
      "name": "Perfectly Balanced Weight",
      "description": "This item has exceptional weight distribution",
      "category": "physical",
      "mechanical_effect": {
        "axis_modifiers": {
          "precision": 1,
          "stability": 1
        },
        "applies_to_actions": ["all_physical_tasks"]
      },
      "interaction_with_character_quirks": {
        "quirk_trembling_hands": "Positive interaction",
        "quirk_grip_strength_low": "Positive interaction"
      },
      "context_dependent": false,
      "example": "A well-balanced tool is easier to use even with weak grip strength"
    },
    {
      "id": "item_quirk_unpredictable_behavior",
      "name": "Unpredictable Behavior",
      "description": "This item behaves differently each time it's used",
      "category": "chaotic",
      "mechanical_effect": {
        "axis_modifiers": {
          "stability": -2
        },
        "applies_to_actions": ["all_actions"]
      },
      "interaction_with_character_quirks": {
        "quirk_lucky_mishaps": "Positive interaction",
        "quirk_risk_averse": "Negative interaction"
      },
      "context_dependent": true,
      "example": "A cursed item that sometimes helps and sometimes hinders"
    },
    {
      "id": "item_quirk_maker_bias",
      "name": "Maker's Bias",
      "description": "This item works best for someone with the maker's attributes",
      "category": "personal",
      "mechanical_effect": {
        "axis_modifiers": {
          "precision": "variable based on attribute match"
        },
        "applies_to_actions": ["all_actions"]
      },
      "interaction_with_character_quirks": {
        "all_quirks": "Depends on maker's quirks"
      },
      "context_dependent": true,
      "example": "A fishing pole made by someone with low patience works poorly for patient goblins"
    }
  ]
}
```

---

## Part 3: Environmental Quirks Library

```json
{
  "environmental_quirks": [
    {
      "id": "env_fast_flowing_water",
      "name": "Fast Flowing Water",
      "description": "Water moves quickly; affects timing and stability",
      "room_types": ["outdoor", "river", "stream"],
      "mechanical_effect": {
        "axis_modifiers": {
          "timing": 1,
          "stability": -1
        },
        "applies_to_actions": ["fishing", "wading", "swimming", "crossing"]
      },
      "severity": "moderate"
    },
    {
      "id": "env_slippery_ground",
      "name": "Slippery Ground",
      "description": "Muddy or icy banks reduce grip and stability",
      "room_types": ["outdoor", "river", "swamp"],
      "mechanical_effect": {
        "axis_modifiers": {
          "stability": -1
        },
        "applies_to_actions": ["walking", "standing", "climbing", "running"]
      },
      "severity": "minor"
    },
    {
      "id": "env_poor_lighting",
      "name": "Poor Lighting",
      "description": "Darkness or dim light affects visibility",
      "room_types": ["indoor", "cave", "night"],
      "mechanical_effect": {
        "axis_modifiers": {
          "precision": -1,
          "visibility": 1
        },
        "applies_to_actions": ["all_actions"]
      },
      "severity": "moderate"
    },
    {
      "id": "env_crowded",
      "name": "Crowded",
      "description": "Many people present; affects stability and visibility",
      "room_types": ["indoor", "marketplace", "tavern"],
      "mechanical_effect": {
        "axis_modifiers": {
          "stability": -1,
          "visibility": 1
        },
        "applies_to_actions": ["all_actions"]
      },
      "severity": "moderate"
    },
    {
      "id": "env_bureaucratic_oversight",
      "name": "Bureaucratic Oversight",
      "description": "Officials are watching; affects interpretability",
      "room_types": ["bureaucratic", "office", "courthouse"],
      "mechanical_effect": {
        "axis_modifiers": {
          "interpretability": -1,
          "visibility": 2
        },
        "applies_to_actions": ["all_actions"]
      },
      "severity": "moderate"
    }
  ]
}
```

---

## Part 4: API Interaction Examples

### 4.1 Character Issuance API Call

```python
"""
API: POST /characters/issue
Issue a new character to a player.
"""

import requests
import json

# Request
request_body = {
    "account_id": "player_001",
    "sex": "female"
}

response = requests.post(
    "http://localhost:8000/api/characters/issue",
    json=request_body,
    headers={"Authorization": "Bearer token_xyz"}
)

# Response (200 OK)
character_response = {
    "success": True,
    "character": {
        "character_id": "char_a7f2c9e1",
        "account_id": "player_001",
        "issued_date": "2025-12-21T14:32:18Z",
        "sex": "female",
        "full_name": "Grindlewick Thrum-of-Three-Keys (Acting)",
        "attributes": {
            "cunning": 8,
            "grip_strength": 3,
            "patience": 2,
            "spatial_sense": 7,
            "stamina": 5,
            "book_learning": 4,
            "luck_administrative": 6
        },
        "quirks": [
            {
                "quirk_id": "quirk_panics_when_watched",
                "name": "Panics When Watched",
                "is_hidden": False
            },
            {
                "quirk_id": "quirk_trembling_hands",
                "name": "Trembling Hands",
                "is_hidden": False
            },
            {
                "quirk_id": "quirk_lucky_mishaps",
                "name": "Lucky Mishaps",
                "is_hidden": True
            }
        ],
        "failings": [
            {
                "failing_id": "failing_numeracy",
                "name": "Poor Numeracy",
                "severity": "moderate"
            },
            {
                "failing_id": "failing_impulse_control",
                "name": "Poor Impulse Control",
                "severity": "severe"
            }
        ],
        "reputation": {
            "score": -5,
            "notes": "Rumoured to be a distant cousin of a disgraced guild master..."
        }
    },
    "message": "Character issued successfully. Welcome to The Undertaking."
}
```

### 4.2 Action Resolution API Call

```python
"""
API: POST /actions/resolve
Resolve an action through the axis-based resolution system.
"""

# Request
request_body = {
    "character_id": "char_a7f2c9e1",
    "action_type": "fish",
    "room_id": "room_riverside_bend",
    "items_used": ["item_f3a8c2b9"]
}

response = requests.post(
    "http://localhost:8000/api/actions/resolve",
    json=request_body,
    headers={"Authorization": "Bearer token_xyz"}
)

# Response (200 OK)
resolution_response = {
    "success": True,
    "ledger_entry": {
        "ledger_id": "ledger_f7a9e2c1",
        "character_id": "char_a7f2c9e1",
        "action_type": "fish",
        "outcome": "failure",
        "axes": {
            "timing": {
                "base_modifier": 1,
                "deviation": 3,
                "final_value": 4
            },
            "precision": {
                "base_modifier": -1,
                "deviation": 2,
                "final_value": 1
            },
            "stability": {
                "base_modifier": -3,
                "deviation": 4,
                "final_value": 1
            },
            "visibility": {
                "base_modifier": 0,
                "deviation": 1,
                "final_value": 1
            },
            "interpretability": {
                "base_modifier": 2,
                "deviation": -1,
                "final_value": 1
            },
            "recovery_cost": {
                "base_modifier": 0,
                "deviation": 2,
                "final_value": 2
            }
        },
        "contributing_factors": [
            "character_quirk_trembling_hands",
            "character_failing_impulse_control",
            "item_quirk_delayed_feedback",
            "environmental_quirk_fast_flowing_water"
        ],
        "interpretation": "avoidable",
        "blame_weight": 0.8
    },
    "newspaper_article": {
        "article_id": "article_b2d4f8a3",
        "headline": "Third Time This Week: Grindlewick's Fishing Troubles Continue",
        "body_text": "At the Riverside Bend this afternoon, Grindlewick Thrum-of-Three-Keys (Acting) made another attempt at fishing...",
        "tone": "gossipy",
        "bias_toward_character": -0.05
    },
    "player_message": "The fish bit, but the delayed feedback from your pole meant you didn't feel it until too late..."
}
```

### 4.3 Item Creation API Call

```python
"""
API: POST /items/create
Create a new item.
"""

# Request
request_body = {
    "item_type": "fishing_pole",
    "creator_character_id": "char_a7f2c9e1",
    "maker_notes": "Shortened the handle to save weight—my grip strength isn't great.",
    "custom_quirks": [
        "item_quirk_delayed_feedback",
        "item_quirk_loose_reel"
    ]
}

response = requests.post(
    "http://localhost:8000/api/items/create",
    json=request_body,
    headers={"Authorization": "Bearer token_xyz"}
)

# Response (201 Created)
item_response = {
    "success": True,
    "item": {
        "item_id": "item_f3a8c2b9",
        "item_type": "fishing_pole",
        "creator_character_id": "char_a7f2c9e1",
        "created_date": "2025-12-21T15:45:22Z",
        "name": "Grindlewick's Weathered Fishing Pole",
        "description": "A fishing pole made from willow wood with a gut line...",
        "quirks": [
            {
                "quirk_id": "item_quirk_delayed_feedback",
                "name": "Delayed Feedback",
                "mechanical_effect": {
                    "timing_modifier": 1
                }
            },
            {
                "quirk_id": "item_quirk_loose_reel",
                "name": "Loose Reel",
                "mechanical_effect": {
                    "precision_modifier": -1,
                    "stability_modifier": -1
                }
            }
        ],
        "maker_profile": {
            "maker_attributes": {
                "cunning": 8,
                "grip_strength": 3,
                "patience": 2,
                "spatial_sense": 7,
                "stamina": 5,
                "book_learning": 4,
                "luck_administrative": 6
            },
            "maker_quirks": [
                "quirk_panics_when_watched",
                "quirk_trembling_hands",
                "quirk_lucky_mishaps"
            ]
        }
    },
    "message": "Item created successfully."
}
```

### 4.4 Room Creation API Call

```python
"""
API: POST /rooms/create
Create a new room.
"""

# Request
request_body = {
    "room_type": "outdoor",
    "creator_character_id": "char_a7f2c9e1",
    "name": "The Riverside Bend",
    "description": "A gentle curve in the river where the water slows and deepens...",
    "connected_rooms": {
        "north": "room_forest_path",
        "south": "room_riverside_workshop",
        "east": "room_rocky_outcrop",
        "west": "room_willow_grove"
    },
    "environmental_quirks": [
        "env_fast_flowing_water",
        "env_slippery_ground"
    ],
    "difficulty_level": 5
}

response = requests.post(
    "http://localhost:8000/api/rooms/create",
    json=request_body,
    headers={"Authorization": "Bearer token_xyz"}
)

# Response (201 Created)
room_response = {
    "success": True,
    "room": {
        "room_id": "room_riverside_bend",
        "room_type": "outdoor",
        "creator_character_id": "char_a7f2c9e1",
        "created_date": "2025-12-21T16:12:45Z",
        "name": "The Riverside Bend",
        "description": "A gentle curve in the river...",
        "difficulty_level": 5,
        "environmental_quirks": [
            {
                "quirk_id": "env_fast_flowing_water",
                "name": "Fast Flowing Water",
                "mechanical_effect": {
                    "timing_modifier": 1,
                    "stability_modifier": -1
                }
            },
            {
                "quirk_id": "env_slippery_ground",
                "name": "Slippery Ground",
                "mechanical_effect": {
                    "stability_modifier": -1
                }
            }
        ],
        "connections": {
            "north": "room_forest_path",
            "south": "room_riverside_workshop",
            "east": "room_rocky_outcrop",
            "west": "room_willow_grove"
        }
    },
    "message": "Room created successfully and added to the world."
}
```

---

## Part 5: Error Handling and Edge Cases

### 5.1 Character Issuance Errors

```python
"""
Error handling for character issuance.
"""

# Error 1: Invalid sex
error_response = {
    "success": False,
    "error": "INVALID_SEX",
    "message": "Sex must be 'male' or 'female'",
    "status_code": 400
}

# Error 2: Account already has character
error_response = {
    "success": False,
    "error": "CHARACTER_ALREADY_EXISTS",
    "message": "This account already has an issued character",
    "status_code": 409
}

# Error 3: Content library not loaded
error_response = {
    "success": False,
    "error": "CONTENT_LIBRARY_ERROR",
    "message": "Could not load content library for character generation",
    "status_code": 500
}
```

### 5.2 Action Resolution Edge Cases

```python
"""
Edge cases in action resolution.
"""

# Edge Case 1: Character has no items but action requires items
# Resolution: Use default/unarmed version of action
# Example: Character tries to fish without a pole → uses hands instead

# Edge Case 2: Room has no environmental quirks
# Resolution: Use default environmental modifiers (all 0)
# Example: Character acts in a neutral room → no environmental effects

# Edge Case 3: Item quirk conflicts with character quirk
# Resolution: Both modifiers apply (can stack positively or negatively)
# Example: Delayed Feedback item + Low Patience = severe timing penalty

# Edge Case 4: Multiple quirks trigger on same action
# Resolution: All applicable quirks apply their modifiers
# Example: "Panics When Watched" + "Trembling Hands" both apply

# Edge Case 5: Axis deviation exceeds threshold
# Resolution: Cascading failure check using stability axis
# Example: Timing deviation too high → check stability → cascade if low

# Edge Case 6: Ledger entry already exists for this action
# Resolution: Update existing entry instead of creating duplicate
# Example: Retry same action → updates ledger with new outcome
```

### 5.3 Item Creation Edge Cases

```python
"""
Edge cases in item creation.
"""

# Edge Case 1: Maker's attributes very different from item's quirks
# Resolution: Item still carries maker's decisions (frozen)
# Example: Weak goblin makes heavy tool → tool is heavy regardless of user

# Edge Case 2: Item has conflicting quirks
# Resolution: Both quirks apply (can cancel out or amplify)
# Example: "Delayed Feedback" + "Quick Response" = neutral timing

# Edge Case 3: Item creator is deleted/inactive
# Resolution: Item persists; maker_profile is historical record
# Example: Deleted character's items still exist and carry their quirks

# Edge Case 4: Item has no quirks assigned
# Resolution: Item functions as baseline (no modifiers)
# Example: Simple tool with no special properties
```

---

## Part 6: Database Query Examples

### 6.1 Retrieve Character with All Related Data

```sql
-- Get a complete character profile
SELECT
    c.*,
    GROUP_CONCAT(q.name) as quirk_names,
    GROUP_CONCAT(f.name) as failing_names,
    GROUP_CONCAT(u.name) as useless_bit_names
FROM characters c
LEFT JOIN quirks q ON q.quirk_id IN (
    SELECT json_each.value FROM json_each(c.quirk_ids)
)
LEFT JOIN failings f ON f.failing_id IN (
    SELECT json_each.value FROM json_each(c.failing_ids)
)
LEFT JOIN useless_bits u ON u.useless_bit_id IN (
    SELECT json_each.value FROM json_each(c.useless_bit_ids)
)
WHERE c.character_id = 'char_a7f2c9e1'
GROUP BY c.character_id;
```

### 6.2 Retrieve Recent Ledger Entries for a Character

```sql
-- Get last 10 actions for a character
SELECT
    l.*,
    n.headline,
    n.body_text,
    n.tone
FROM ledger l
LEFT JOIN newspaper n ON l.ledger_id = n.ledger_id
WHERE l.character_id = 'char_a7f2c9e1'
ORDER BY l.action_timestamp DESC
LIMIT 10;
```

### 6.3 Find All Items Created by a Character

```sql
-- Get all items created by a specific character
SELECT
    i.*,
    GROUP_CONCAT(iq.name) as quirk_names
FROM items i
LEFT JOIN item_quirks iq ON iq.item_quirk_id IN (
    SELECT json_each.value FROM json_each(i.quirk_ids)
)
WHERE i.creator_character_id = 'char_a7f2c9e1'
GROUP BY i.item_id
ORDER BY i.created_date DESC;
```

### 6.4 Retrieve All Rooms Connected to a Specific Room

```sql
-- Get all rooms connected to a room
WITH room_connections AS (
    SELECT
        room_id,
        json_each.key as direction,
        json_each.value as connected_room_id
    FROM rooms, json_each(connected_rooms)
    WHERE room_id = 'room_riverside_bend'
)
SELECT
    r.room_id,
    r.name,
    rc.direction,
    r.room_type,
    r.difficulty_level
FROM room_connections rc
JOIN rooms r ON r.room_id = rc.connected_room_id;
```

### 6.5 Find Characters with Specific Quirks

```sql
-- Find all characters with "Panics When Watched" quirk
SELECT
    c.character_id,
    c.given_name,
    c.family_name,
    c.reputation_score
FROM characters c
WHERE json_extract(c.quirk_ids, '$[*]') LIKE '%quirk_panics_when_watched%'
ORDER BY c.reputation_score DESC;
```

### 6.6 Calculate Character Statistics

```sql
-- Get statistics for a character's recent actions
SELECT
    c.character_id,
    c.given_name,
    c.family_name,
    COUNT(l.ledger_id) as total_actions,
    SUM(CASE WHEN l.outcome = 'success' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN l.outcome = 'failure' THEN 1 ELSE 0 END) as failures,
    ROUND(SUM(CASE WHEN l.outcome = 'success' THEN 1 ELSE 0 END) * 100.0 / COUNT(l.ledger_id), 2) as success_rate,
    ROUND(AVG(l.blame_weight), 2) as average_blame_weight
FROM characters c
LEFT JOIN ledger l ON c.character_id = l.character_id
    AND l.action_timestamp > datetime('now', '-7 days')
WHERE c.character_id = 'char_a7f2c9e1'
GROUP BY c.character_id;
```

---

## Part 7: Testing Scenarios

### 7.1 Character Issuance Test

```python
"""
Test: Character issuance produces valid, immutable characters
"""

def test_character_issuance():
    issuer = CharacterIssuer(db, library)

    # Issue a character
    character = issuer.issue_character('player_001', 'female')

    # Verify all required fields
    assert character['character_id'] is not None
    assert character['sex'] == 'female'
    assert character['given_name'] is not None
    assert character['family_name'] is not None
    assert len(character['attributes']) == 7
    assert 2 <= len(character['quirks']) <= 4
    assert len(character['failings']) >= 0
    assert len(character['useless_bits']) >= 1
    assert character['reputation']['score'] is not None

    # Verify immutability (character is sealed)
    assert character['is_active'] == True

    # Verify attributes are in valid range
    for attr_name, attr_value in character['attributes'].items():
        assert 1 <= attr_value <= 10, f"{attr_name} out of range: {attr_value}"

    print("✓ Character issuance test passed")
```

### 7.2 Action Resolution Test

```python
"""
Test: Action resolution produces consistent outcomes
"""

def test_action_resolution():
    engine = ResolutionEngine(db)

    # Resolve an action
    ledger_entry, newspaper = engine.resolve_action(
        character_id='char_a7f2c9e1',
        action_type='fish',
        room_id='room_riverside_bend',
        items_used=['item_f3a8c2b9'],
        seed='test_seed_001'
    )

    # Verify ledger entry
    assert ledger_entry['ledger_id'] is not None
    assert ledger_entry['outcome'] in ['success', 'partial_success', 'failure']
    assert 0.0 <= ledger_entry['blame_weight'] <= 1.0
    assert ledger_entry['interpretation'] in ['avoidable', 'inevitable', 'fortunate']

    # Verify all axes have deviations
    for axis_name in ['timing', 'precision', 'stability', 'visibility', 'interpretability', 'recovery_cost']:
        assert axis_name in ledger_entry['deviations']

    # Verify newspaper article
    assert newspaper['article_id'] is not None
    assert newspaper['headline'] is not None
    assert newspaper['body_text'] is not None
    assert newspaper['tone'] in ['gossipy', 'formal', 'sympathetic']

    # Verify deterministic replay
    ledger_entry_2, _ = engine.resolve_action(
        character_id='char_a7f2c9e1',
        action_type='fish',
        room_id='room_riverside_bend',
        items_used=['item_f3a8c2b9'],
        seed='test_seed_001'
    )

    # Same seed should produce same outcome
    assert ledger_entry['outcome'] == ledger_entry_2['outcome']
    assert ledger_entry['deviations'] == ledger_entry_2['deviations']

    print("✓ Action resolution test passed")
```

### 7.3 Item Quirk Interaction Test

```python
"""
Test: Item quirks interact correctly with character quirks
"""

def test_item_quirk_interaction():
    forge = ItemForge(db, library)

    # Create an item with delayed feedback
    item = forge.create_item(
        item_type='fishing_pole',
        creator_character_id='char_a7f2c9e1',
        custom_quirks=['item_quirk_delayed_feedback', 'item_quirk_loose_reel']
    )

    # Verify quirks are assigned
    assert len(item['quirks']) >= 2
    assert any(q['quirk_id'] == 'item_quirk_delayed_feedback' for q in item['quirks'])

    # Verify maker profile is captured
    assert item['maker_profile']['maker_attributes'] is not None
    assert item['maker_profile']['maker_quirks'] is not None

    # Verify item is usable
    assert item['is_available'] == True
    assert item['current_location'] is None  # Not yet placed in world

    print("✓ Item quirk interaction test passed")
```

---

## Conclusion

These supplementary examples demonstrate:

1. **Content Library Structure**: How quirks, failings, useless bits, and environmental quirks are organized
2. **API Interactions**: How the backend systems communicate with the frontend
3. **Error Handling**: How edge cases are managed
4. **Database Queries**: How to retrieve complex data relationships
5. **Testing**: How to verify system behavior

The Undertaking's architecture is designed to be:
- **Deterministic**: Same seed produces same outcome
- **Modular**: Each system (character, item, room, action) is independent
- **Extensible**: Players can create new content using the same tools
- **Narrative-Rich**: Hard truth (ledger) and soft truth (newspaper) create emergent stories
