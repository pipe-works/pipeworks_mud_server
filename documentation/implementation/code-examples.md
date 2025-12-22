# The Undertaking: Backend Code Examples and In-Game Output

This document demonstrates the backend architecture of The Undertaking through pseudo Python, JSON, and SQLite code, showing both the system's internal flow and the player-facing output.

---

## Part 1: Database Schema (SQLite)

### 1.1 Character Table

```sql
-- Characters are issued, not created. Once sealed, they are immutable.
CREATE TABLE characters (
    character_id TEXT PRIMARY KEY,           -- UUID: unique identifier
    account_id TEXT NOT NULL,                -- Links to player account
    issued_date TIMESTAMP NOT NULL,          -- When the goblin was issued
    sex TEXT NOT NULL,                       -- Only choice: 'male' or 'female'
    
    -- Name components (immutable once issued)
    given_name TEXT NOT NULL,                -- e.g., "Grindlewick"
    family_name TEXT NOT NULL,               -- e.g., "Thrum-of-Three-Keys"
    honorific TEXT,                          -- e.g., "(Acting)", "(Provisional)"
    
    -- Core Attributes (7 stats, distributed unevenly)
    cunning INTEGER NOT NULL,                -- Range: 1-10
    grip_strength INTEGER NOT NULL,          -- Range: 1-10
    patience INTEGER NOT NULL,               -- Range: 1-10
    spatial_sense INTEGER NOT NULL,          -- Range: 1-10
    stamina INTEGER NOT NULL,                -- Range: 1-10
    book_learning INTEGER NOT NULL,          -- Range: 1-10
    luck_administrative INTEGER NOT NULL,    -- Range: 1-10
    
    -- Quirks (2-4 mandatory traits with mechanical effects)
    quirk_ids TEXT NOT NULL,                 -- JSON array: ["quirk_001", "quirk_042"]
    
    -- Failings (persistent deficiencies)
    failing_ids TEXT NOT NULL,               -- JSON array: ["failing_numeracy", "failing_depth_perception"]
    
    -- Useless Bits (specializations that rarely help)
    useless_bit_ids TEXT NOT NULL,           -- JSON array: ["useless_obsolete_measures", "useless_bridge_names"]
    
    -- Starting Reputation (inherited bias)
    reputation_score REAL NOT NULL,          -- Range: -100 to +100
    reputation_notes TEXT,                   -- e.g., "Rumoured to be a cousin of a guild master"
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_action_timestamp TIMESTAMP
);

-- Index for quick lookups
CREATE INDEX idx_characters_account ON characters(account_id);
CREATE INDEX idx_characters_active ON characters(is_active);
```

### 1.2 Quirks Reference Table

```sql
-- Quirks are mechanical traits that affect resolution
CREATE TABLE quirks (
    quirk_id TEXT PRIMARY KEY,               -- e.g., "quirk_panics_when_watched"
    name TEXT NOT NULL,                      -- e.g., "Panics When Watched"
    description TEXT NOT NULL,               -- Mechanical description
    
    -- Axis Modifiers (how this quirk affects resolution axes)
    timing_modifier INTEGER DEFAULT 0,       -- -2 to +2
    precision_modifier INTEGER DEFAULT 0,
    stability_modifier INTEGER DEFAULT 0,
    visibility_modifier INTEGER DEFAULT 0,
    interpretability_modifier INTEGER DEFAULT 0,
    recovery_cost_modifier INTEGER DEFAULT 0,
    
    -- Trigger Condition
    trigger_condition TEXT NOT NULL,         -- e.g., "when_observed_by_npc"
    trigger_description TEXT,
    
    -- Category
    category TEXT NOT NULL,                  -- e.g., "behavioral", "physical", "mental"
    rarity TEXT NOT NULL                     -- e.g., "common", "uncommon", "rare"
);
```

### 1.3 Failings Reference Table

```sql
-- Failings are persistent deficiencies that apply even on "success"
CREATE TABLE failings (
    failing_id TEXT PRIMARY KEY,             -- e.g., "failing_numeracy"
    name TEXT NOT NULL,                      -- e.g., "Poor Numeracy"
    description TEXT NOT NULL,               -- What this failing means
    
    -- Mechanical Effect
    affected_attributes TEXT NOT NULL,       -- JSON array: ["book_learning"]
    effect_description TEXT,                 -- e.g., "Miscalculates resources by 10-20%"
    
    -- Severity
    severity TEXT NOT NULL                   -- e.g., "minor", "moderate", "severe"
);
```

### 1.4 Items Table

```sql
-- Items are frozen decisions of another goblin
CREATE TABLE items (
    item_id TEXT PRIMARY KEY,                -- UUID
    creator_character_id TEXT,               -- Who made this item (if player-created)
    item_type TEXT NOT NULL,                 -- e.g., "fishing_pole", "ledger", "quill"
    
    -- Item Identity
    name TEXT NOT NULL,                      -- e.g., "Weathered Fishing Pole"
    description TEXT NOT NULL,               -- Narrative description
    created_date TIMESTAMP NOT NULL,
    
    -- Item Quirks (items have quirks just like characters)
    quirk_ids TEXT NOT NULL,                 -- JSON array: ["item_quirk_delayed_feedback"]
    
    -- Item History (frozen decisions)
    maker_notes TEXT,                        -- e.g., "Shortened the handle to save weight"
    material TEXT,                           -- e.g., "willow wood, gut line"
    condition TEXT NOT NULL,                 -- e.g., "worn", "serviceable", "pristine"
    
    -- Location
    current_location TEXT,                   -- room_id or character_id
    is_available BOOLEAN DEFAULT TRUE
);
```

### 1.5 Item Quirks Reference Table

```sql
-- Item quirks are mechanical properties of items
CREATE TABLE item_quirks (
    item_quirk_id TEXT PRIMARY KEY,          -- e.g., "item_quirk_delayed_feedback"
    name TEXT NOT NULL,                      -- e.g., "Delayed Feedback"
    description TEXT NOT NULL,
    
    -- Mechanical Effect
    timing_modifier INTEGER DEFAULT 0,
    precision_modifier INTEGER DEFAULT 0,
    stability_modifier INTEGER DEFAULT 0,
    
    -- Interaction Notes
    interacts_with_character_quirks TEXT,    -- JSON: which quirks it interacts with
    context_dependent BOOLEAN DEFAULT TRUE   -- Does it behave differently in different contexts?
);
```

### 1.6 Rooms Table

```sql
-- Rooms are the locations where actions happen
CREATE TABLE rooms (
    room_id TEXT PRIMARY KEY,                -- UUID or location code
    creator_character_id TEXT,               -- Who built this room (if player-created)
    
    -- Room Identity
    name TEXT NOT NULL,                      -- e.g., "The Riverside Bend"
    description TEXT NOT NULL,               -- Narrative description
    created_date TIMESTAMP NOT NULL,
    
    -- Room Properties
    room_type TEXT NOT NULL,                 -- e.g., "outdoor", "indoor", "bureaucratic"
    difficulty_level INTEGER,                -- Affects resolution (1-10)
    
    -- Connections
    connected_rooms TEXT NOT NULL,           -- JSON: {"north": "room_002", "south": "room_001"}
    
    -- Environmental Quirks (rooms can have quirks too)
    environmental_quirks TEXT,               -- JSON array: ["fast_flowing_water", "poor_lighting"]
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_modified TIMESTAMP
);
```

### 1.7 Ledger Table (Hard Truth)

```sql
-- The ledger is the immutable record of what actually happened
CREATE TABLE ledger (
    ledger_id TEXT PRIMARY KEY,              -- UUID
    character_id TEXT NOT NULL,              -- Who performed the action
    action_type TEXT NOT NULL,               -- e.g., "fish", "craft", "negotiate"
    room_id TEXT,                            -- Where it happened
    
    -- Timestamp
    action_timestamp TIMESTAMP NOT NULL,
    
    -- Resolution Data
    outcome TEXT NOT NULL,                   -- e.g., "success", "failure", "partial_success"
    
    -- Contributing Factors (deterministic, replayable)
    contributing_factors TEXT NOT NULL,      -- JSON array of factor IDs
    
    -- Axis Deviations (how far from ideal on each axis)
    timing_deviation INTEGER,
    precision_deviation INTEGER,
    stability_deviation INTEGER,
    visibility_deviation INTEGER,
    interpretability_deviation INTEGER,
    recovery_cost_deviation INTEGER,
    
    -- Interpretation Data
    interpretation TEXT NOT NULL,            -- e.g., "avoidable", "inevitable", "lucky"
    blame_weight REAL NOT NULL,              -- 0.0 to 1.0: how much blame falls on the character
    
    -- Items and Equipment Used
    items_used TEXT,                         -- JSON array of item_ids
    
    -- Seed (for deterministic replay)
    resolution_seed TEXT NOT NULL,           -- Allows exact replay of this action
    
    -- Status
    is_public BOOLEAN DEFAULT FALSE          -- Has the newspaper written about this?
);

CREATE INDEX idx_ledger_character ON ledger(character_id);
CREATE INDEX idx_ledger_timestamp ON ledger(action_timestamp);
```

### 1.8 Newspaper Table (Soft Truth)

```sql
-- The newspaper is the narrative interpretation of ledger events
CREATE TABLE newspaper (
    article_id TEXT PRIMARY KEY,             -- UUID
    ledger_id TEXT NOT NULL UNIQUE,          -- Links to the ledger entry
    
    -- Article Identity
    headline TEXT NOT NULL,                  -- e.g., "Third Time This Week"
    body_text TEXT NOT NULL,                 -- Full narrative account
    
    -- Narrative Properties
    tone TEXT NOT NULL,                      -- e.g., "gossipy", "formal", "sympathetic"
    bias_toward_character REAL,              -- -1.0 to +1.0: how favorable is the coverage?
    
    -- Publication
    published_date TIMESTAMP NOT NULL,
    publication_source TEXT,                 -- e.g., "The Daily Ledger", "Tavern Gossip"
    
    -- Interpretation Choices
    blamed_party TEXT,                       -- Who the newspaper blames
    praised_party TEXT,                      -- Who the newspaper praises
    
    FOREIGN KEY (ledger_id) REFERENCES ledger(ledger_id)
);

CREATE INDEX idx_newspaper_ledger ON newspaper(ledger_id);
```

---

## Part 2: Character Creation Flow (Python Pseudo Code)

### 2.1 Character Issuance System

```python
"""
CHARACTER ISSUANCE SYSTEM
=========================
Players choose only their sex. Everything else is generated and sealed.
"""

import json
import random
import uuid
from datetime import datetime
from typing import Dict, List, Tuple


class CharacterIssuer:
    """
    Responsible for generating complete, immutable goblin characters.
    This is NOT character creation—it is character issuance.
    """
    
    def __init__(self, database_connection, content_library):
        """
        Args:
            database_connection: SQLite connection
            content_library: Loaded quirks, failings, names, etc.
        """
        self.db = database_connection
        self.library = content_library
        self.random = random.Random()  # Seeded for determinism
    
    def issue_character(self, account_id: str, sex: str) -> Dict:
        """
        Issue a complete goblin character to a player.
        
        Args:
            account_id: The player's account ID
            sex: 'male' or 'female' (only player choice)
        
        Returns:
            Dictionary containing the issued character's complete profile
        """
        
        # Step 1: Generate Name (from weighted pools)
        name_components = self._generate_name(sex)
        
        # Step 2: Distribute Attributes (deliberately uneven)
        attributes = self._generate_attributes()
        
        # Step 3: Assign Quirks (2-4 mandatory traits)
        quirks = self._assign_quirks()
        
        # Step 4: Assign Failings (persistent deficiencies)
        failings = self._assign_failings(attributes)
        
        # Step 5: Assign Useless Bits (specializations that rarely help)
        useless_bits = self._assign_useless_bits()
        
        # Step 6: Generate Starting Reputation (inherited bias)
        reputation = self._generate_reputation(name_components, attributes)
        
        # Step 7: Create Character Record
        character_id = str(uuid.uuid4())
        character = {
            'character_id': character_id,
            'account_id': account_id,
            'issued_date': datetime.now().isoformat(),
            'sex': sex,
            'given_name': name_components['given_name'],
            'family_name': name_components['family_name'],
            'honorific': name_components.get('honorific'),
            'attributes': attributes,
            'quirks': quirks,
            'failings': failings,
            'useless_bits': useless_bits,
            'reputation': reputation,
            'is_active': True
        }
        
        # Step 8: Persist to Database
        self._save_character_to_database(character)
        
        return character
    
    def _generate_name(self, sex: str) -> Dict:
        """
        Generate a name from weighted pools.
        Names are often embarrassing, too long, or bureaucratically awkward.
        """
        given_names = self.library['given_names'][sex]
        family_names = self.library['family_names']
        honorifics = self.library['honorifics']
        
        # Weighted selection (some names more common than others)
        given_name = self.random.choices(
            given_names['names'],
            weights=given_names['weights']
        )[0]
        
        family_name = self.random.choices(
            family_names['names'],
            weights=family_names['weights']
        )[0]
        
        # 30% chance of an honorific
        honorific = None
        if self.random.random() < 0.3:
            honorific = self.random.choice(honorifics)
        
        return {
            'given_name': given_name,
            'family_name': family_name,
            'honorific': honorific
        }
    
    def _generate_attributes(self) -> Dict:
        """
        Distribute 7 core attributes unevenly by design.
        Some goblins are naturally competent; others are not.
        
        Total points: 42 (6 per attribute on average)
        But distributed with high variance.
        """
        attributes = {}
        attribute_names = [
            'cunning',
            'grip_strength',
            'patience',
            'spatial_sense',
            'stamina',
            'book_learning',
            'luck_administrative'
        ]
        
        # Use a weighted distribution to create variance
        # Some attributes will be high (8-10), others low (1-3)
        for attr in attribute_names:
            # Roll 3d4 + 1 for each attribute (range 4-13, capped at 10)
            value = min(10, sum(self.random.randint(1, 4) for _ in range(3)))
            attributes[attr] = value
        
        return attributes
    
    def _assign_quirks(self) -> List[Dict]:
        """
        Assign 2-4 mandatory quirks.
        Quirks are mechanical traits that affect how actions resolve.
        Some quirks are hidden until discovered through failure.
        """
        num_quirks = self.random.randint(2, 4)
        available_quirks = self.library['quirks']
        
        # Weight selection toward common quirks
        selected_quirks = self.random.choices(
            available_quirks,
            weights=[q.get('rarity_weight', 1) for q in available_quirks],
            k=num_quirks
        )
        
        # Some quirks are hidden
        quirks = []
        for quirk in selected_quirks:
            quirk_data = {
                'quirk_id': quirk['id'],
                'name': quirk['name'],
                'is_hidden': self.random.random() < 0.2  # 20% chance hidden
            }
            quirks.append(quirk_data)
        
        return quirks
    
    def _assign_failings(self, attributes: Dict) -> List[Dict]:
        """
        Assign persistent deficiencies based on low attributes.
        A goblin with poor numeracy will miscalculate resources even on success.
        """
        failings = []
        
        # Low book_learning → numeracy failing
        if attributes['book_learning'] <= 3:
            failings.append({
                'failing_id': 'failing_numeracy',
                'name': 'Poor Numeracy',
                'severity': 'severe'
            })
        elif attributes['book_learning'] <= 5:
            failings.append({
                'failing_id': 'failing_numeracy',
                'name': 'Poor Numeracy',
                'severity': 'moderate'
            })
        
        # Low spatial_sense → depth perception failing
        if attributes['spatial_sense'] <= 3:
            failings.append({
                'failing_id': 'failing_depth_perception',
                'name': 'Poor Depth Perception',
                'severity': 'severe'
            })
        
        # Low patience → impulse control failing
        if attributes['patience'] <= 2:
            failings.append({
                'failing_id': 'failing_impulse_control',
                'name': 'Poor Impulse Control',
                'severity': 'severe'
            })
        
        return failings
    
    def _assign_useless_bits(self) -> List[Dict]:
        """
        Assign specializations that sound helpful but rarely are.
        Examples:
        - Expert in obsolete measurement systems
        - Knows every bridge by name but not where they go
        - Can identify any mushroom (but can't cook)
        """
        useless_bits = self.library['useless_bits']
        num_bits = self.random.randint(1, 3)
        
        selected_bits = self.random.choices(useless_bits, k=num_bits)
        
        return [
            {
                'useless_bit_id': bit['id'],
                'name': bit['name'],
                'description': bit['description']
            }
            for bit in selected_bits
        ]
    
    def _generate_reputation(self, name_components: Dict, attributes: Dict) -> Dict:
        """
        Generate starting reputation (inherited bias before the player has done anything).
        Rumours, clerical errors, family assumptions, and guild expectations.
        """
        base_reputation = self.random.randint(-20, 20)
        
        # Name affects reputation
        if name_components.get('honorific'):
            base_reputation += 10  # Honorifics suggest status
        
        # Rumors and clerical errors
        reputation_notes = self._generate_reputation_notes(name_components)
        
        return {
            'score': base_reputation,
            'notes': reputation_notes
        }
    
    def _generate_reputation_notes(self, name_components: Dict) -> str:
        """Generate rumours and clerical errors about the character."""
        rumors = self.library['reputation_rumors']
        selected_rumors = self.random.choices(rumors, k=self.random.randint(1, 3))
        
        return "; ".join(selected_rumors)
    
    def _save_character_to_database(self, character: Dict) -> None:
        """Persist the character to the database."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO characters (
                character_id, account_id, issued_date, sex,
                given_name, family_name, honorific,
                cunning, grip_strength, patience, spatial_sense,
                stamina, book_learning, luck_administrative,
                quirk_ids, failing_ids, useless_bit_ids,
                reputation_score, reputation_notes, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            character['character_id'],
            character['account_id'],
            character['issued_date'],
            character['sex'],
            character['given_name'],
            character['family_name'],
            character['honorific'],
            character['attributes']['cunning'],
            character['attributes']['grip_strength'],
            character['attributes']['patience'],
            character['attributes']['spatial_sense'],
            character['attributes']['stamina'],
            character['attributes']['book_learning'],
            character['attributes']['luck_administrative'],
            json.dumps([q['quirk_id'] for q in character['quirks']]),
            json.dumps([f['failing_id'] for f in character['failings']]),
            json.dumps([u['useless_bit_id'] for u in character['useless_bits']]),
            character['reputation']['score'],
            character['reputation']['notes'],
            character['is_active']
        ))
        
        self.db.commit()
```

### 2.2 Character Issuance JSON Example

```json
{
  "character_id": "char_a7f2c9e1",
  "account_id": "player_001",
  "issued_date": "2025-12-21T14:32:18Z",
  "sex": "female",
  
  "name": {
    "given_name": "Grindlewick",
    "family_name": "Thrum-of-Three-Keys",
    "honorific": "(Acting)",
    "full_name": "Grindlewick Thrum-of-Three-Keys (Acting)"
  },
  
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
      "description": "Stability reduced by 2 when an NPC is observing",
      "is_hidden": false,
      "mechanical_effect": {
        "trigger": "when_observed_by_npc",
        "stability_modifier": -2
      }
    },
    {
      "quirk_id": "quirk_trembling_hands",
      "name": "Trembling Hands",
      "description": "Precision reduced by 1 in fine motor tasks",
      "is_hidden": false,
      "mechanical_effect": {
        "trigger": "always",
        "precision_modifier": -1
      }
    },
    {
      "quirk_id": "quirk_lucky_mishaps",
      "name": "Lucky Mishaps",
      "description": "Failures sometimes reinterpreted as successes",
      "is_hidden": true,
      "mechanical_effect": {
        "trigger": "on_failure",
        "interpretability_modifier": 2
      }
    }
  ],
  
  "failings": [
    {
      "failing_id": "failing_numeracy",
      "name": "Poor Numeracy",
      "description": "Miscalculates resources by 10-20% even on success",
      "severity": "moderate",
      "affected_attributes": ["book_learning"]
    },
    {
      "failing_id": "failing_impulse_control",
      "name": "Poor Impulse Control",
      "description": "Acts too quickly in time-sensitive situations",
      "severity": "severe",
      "affected_attributes": ["patience"]
    }
  ],
  
  "useless_bits": [
    {
      "useless_bit_id": "useless_obsolete_measures",
      "name": "Expert in Obsolete Measurement Systems",
      "description": "Can convert between fathoms, cubits, and hand-spans, but nobody uses these anymore"
    },
    {
      "useless_bit_id": "useless_bridge_names",
      "name": "Knows Every Bridge by Name",
      "description": "Can name any bridge in the city, but not where it goes"
    }
  ],
  
  "reputation": {
    "score": -5,
    "notes": "Rumoured to be a distant cousin of a disgraced guild master; clerical records suggest she once failed a basic numeracy test; locals expect her to be unreliable"
  },
  
  "status": {
    "is_active": true,
    "created_date": "2025-12-21T14:32:18Z"
  }
}
```

---

## Part 3: Item Creation Flow (Python Pseudo Code)

### 3.1 Item Forging System

```python
"""
ITEM FORGING SYSTEM
===================
Items are frozen decisions of another goblin.
They carry maker's habits, shortcuts, grudges, cleverness, and mistakes.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List


class ItemForge:
    """
    Responsible for creating items with quirks and frozen decision-making.
    Items can be created by the system or by players.
    """
    
    def __init__(self, database_connection, content_library):
        self.db = database_connection
        self.library = content_library
    
    def create_item(
        self,
        item_type: str,
        creator_character_id: str,
        maker_notes: str = None,
        custom_quirks: List[str] = None
    ) -> Dict:
        """
        Create a new item.
        
        Args:
            item_type: Type of item (e.g., 'fishing_pole', 'ledger', 'quill')
            creator_character_id: Who made this item
            maker_notes: Notes about the maker's decisions
            custom_quirks: Optional list of quirk IDs to apply
        
        Returns:
            Dictionary containing the item's complete profile
        """
        
        # Step 1: Get Item Template
        template = self.library['item_templates'].get(item_type)
        if not template:
            raise ValueError(f"Unknown item type: {item_type}")
        
        # Step 2: Generate Item Identity
        item_id = str(uuid.uuid4())
        name = self._generate_item_name(template, creator_character_id)
        
        # Step 3: Assign Quirks (items have quirks like characters)
        if custom_quirks:
            quirks = custom_quirks
        else:
            quirks = self._assign_item_quirks(template)
        
        # Step 4: Record Maker's Decisions
        maker_profile = self._profile_maker(creator_character_id)
        
        # Step 5: Create Item Record
        item = {
            'item_id': item_id,
            'item_type': item_type,
            'creator_character_id': creator_character_id,
            'created_date': datetime.now().isoformat(),
            'name': name,
            'description': template['description'],
            'material': template.get('material'),
            'condition': 'serviceable',
            'quirks': quirks,
            'maker_notes': maker_notes or template.get('default_notes'),
            'maker_profile': maker_profile,
            'current_location': None,  # Not yet in the world
            'is_available': True
        }
        
        # Step 6: Persist to Database
        self._save_item_to_database(item)
        
        return item
    
    def _generate_item_name(self, template: Dict, creator_character_id: str) -> str:
        """
        Generate a name for the item based on template and maker.
        Names reflect the maker's identity and the item's quirks.
        """
        # Get maker's name
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT given_name, family_name FROM characters WHERE character_id = ?",
            (creator_character_id,)
        )
        result = cursor.fetchone()
        
        if result:
            maker_name = f"{result[0]}'s"
        else:
            maker_name = "Unknown Maker's"
        
        # Combine with template
        base_name = template['base_name']
        
        # 50% chance of maker's name in the item name
        if self.random.random() < 0.5:
            return f"{maker_name} {base_name}"
        else:
            return base_name
    
    def _assign_item_quirks(self, template: Dict) -> List[Dict]:
        """
        Assign quirks to the item.
        Items have quirks just like characters do.
        """
        base_quirks = template.get('base_quirks', [])
        
        # Add 0-2 additional quirks
        num_additional = self.random.randint(0, 2)
        available_quirks = self.library['item_quirks']
        
        additional_quirks = self.random.choices(
            available_quirks,
            k=num_additional
        )
        
        all_quirks = base_quirks + [q['id'] for q in additional_quirks]
        
        return [
            {
                'quirk_id': quirk_id,
                'name': self._get_quirk_name(quirk_id),
                'mechanical_effect': self._get_quirk_effect(quirk_id)
            }
            for quirk_id in all_quirks
        ]
    
    def _profile_maker(self, creator_character_id: str) -> Dict:
        """
        Profile the maker's attributes and quirks.
        This becomes part of the item's "frozen decisions."
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT cunning, grip_strength, patience, spatial_sense,
                   stamina, book_learning, luck_administrative, quirk_ids
            FROM characters WHERE character_id = ?
            """,
            (creator_character_id,)
        )
        result = cursor.fetchone()
        
        if result:
            return {
                'maker_attributes': {
                    'cunning': result[0],
                    'grip_strength': result[1],
                    'patience': result[2],
                    'spatial_sense': result[3],
                    'stamina': result[4],
                    'book_learning': result[5],
                    'luck_administrative': result[6]
                },
                'maker_quirks': json.loads(result[7])
            }
        
        return {}
    
    def _save_item_to_database(self, item: Dict) -> None:
        """Persist the item to the database."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO items (
                item_id, creator_character_id, item_type, name,
                description, created_date, quirk_ids, maker_notes,
                material, condition, current_location, is_available
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item['item_id'],
            item['creator_character_id'],
            item['item_type'],
            item['name'],
            item['description'],
            item['created_date'],
            json.dumps([q['quirk_id'] for q in item['quirks']]),
            item['maker_notes'],
            item['material'],
            item['condition'],
            item['current_location'],
            item['is_available']
        ))
        
        self.db.commit()
```

### 3.2 Item Creation JSON Example

```json
{
  "item_id": "item_f3a8c2b9",
  "item_type": "fishing_pole",
  "creator_character_id": "char_a7f2c9e1",
  "created_date": "2025-12-21T15:45:22Z",
  
  "name": "Grindlewick's Weathered Fishing Pole",
  "description": "A fishing pole made from willow wood with a gut line. The handle has been shortened, and the reel mechanism is slightly loose.",
  
  "material": "willow wood, gut line, brass reel",
  "condition": "worn",
  
  "quirks": [
    {
      "quirk_id": "item_quirk_delayed_feedback",
      "name": "Delayed Feedback",
      "description": "Bite detection is delayed by 0.5-1 second",
      "mechanical_effect": {
        "timing_modifier": 1,
        "trigger": "when_fishing",
        "interaction_note": "Interacts unpredictably with low patience"
      }
    },
    {
      "quirk_id": "item_quirk_loose_reel",
      "name": "Loose Reel",
      "description": "Reel mechanism slips occasionally",
      "mechanical_effect": {
        "precision_modifier": -1,
        "stability_modifier": -1,
        "trigger": "when_reeling_in"
      }
    }
  ],
  
  "maker_profile": {
    "maker_character_id": "char_a7f2c9e1",
    "maker_name": "Grindlewick Thrum-of-Three-Keys (Acting)",
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
    ],
    "maker_notes": "Shortened the handle to save weight—my grip strength isn't great. Reel mechanism is loose because I was in a hurry. The delayed feedback is intentional; I wanted to slow down the bite detection so I'd have time to react."
  },
  
  "history": {
    "created_date": "2025-12-21T15:45:22Z",
    "creation_context": "Made in the riverside workshop after a failed fishing attempt",
    "previous_owners": []
  },
  
  "status": {
    "current_location": "room_riverside_workshop",
    "is_available": true
  }
}
```

---

## Part 4: Room Creation Flow (Python Pseudo Code)

### 4.1 Room Builder System

```python
"""
ROOM BUILDER SYSTEM
===================
Rooms are locations where actions happen.
Players can create new rooms and link them to the existing world.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional


class RoomBuilder:
    """
    Responsible for creating rooms and managing world connectivity.
    Rooms can be created by the system or by players.
    """
    
    def __init__(self, database_connection, content_library):
        self.db = database_connection
        self.library = content_library
    
    def create_room(
        self,
        room_type: str,
        creator_character_id: str,
        name: str,
        description: str,
        connected_rooms: Dict[str, str] = None,
        environmental_quirks: List[str] = None,
        difficulty_level: int = 5
    ) -> Dict:
        """
        Create a new room.
        
        Args:
            room_type: Type of room (e.g., 'outdoor', 'indoor', 'bureaucratic')
            creator_character_id: Who built this room
            name: Name of the room
            description: Narrative description
            connected_rooms: Dict of connections (e.g., {"north": "room_002"})
            environmental_quirks: List of environmental quirk IDs
            difficulty_level: 1-10 scale for action difficulty
        
        Returns:
            Dictionary containing the room's complete profile
        """
        
        # Step 1: Generate Room Identity
        room_id = str(uuid.uuid4())
        
        # Step 2: Validate Connections
        if connected_rooms is None:
            connected_rooms = {}
        
        # Step 3: Assign Environmental Quirks
        if environmental_quirks is None:
            environmental_quirks = self._assign_environmental_quirks(room_type)
        
        # Step 4: Create Room Record
        room = {
            'room_id': room_id,
            'room_type': room_type,
            'creator_character_id': creator_character_id,
            'created_date': datetime.now().isoformat(),
            'name': name,
            'description': description,
            'connected_rooms': connected_rooms,
            'environmental_quirks': environmental_quirks,
            'difficulty_level': difficulty_level,
            'is_active': True
        }
        
        # Step 5: Persist to Database
        self._save_room_to_database(room)
        
        # Step 6: Update Connections (bidirectional)
        self._update_room_connections(room_id, connected_rooms)
        
        return room
    
    def _assign_environmental_quirks(self, room_type: str) -> List[str]:
        """
        Assign environmental quirks based on room type.
        Environmental quirks affect how actions resolve in this room.
        """
        template = self.library['room_templates'].get(room_type, {})
        base_quirks = template.get('base_quirks', [])
        
        # Add 0-2 additional quirks
        num_additional = self.random.randint(0, 2)
        available_quirks = self.library['environmental_quirks']
        
        additional_quirks = self.random.choices(
            available_quirks,
            k=num_additional
        )
        
        return base_quirks + [q['id'] for q in additional_quirks]
    
    def _save_room_to_database(self, room: Dict) -> None:
        """Persist the room to the database."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO rooms (
                room_id, creator_character_id, name, description,
                created_date, room_type, difficulty_level,
                connected_rooms, environmental_quirks, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            room['room_id'],
            room['creator_character_id'],
            room['name'],
            room['description'],
            room['created_date'],
            room['room_type'],
            room['difficulty_level'],
            json.dumps(room['connected_rooms']),
            json.dumps(room['environmental_quirks']),
            room['is_active']
        ))
        
        self.db.commit()
    
    def _update_room_connections(
        self,
        room_id: str,
        connected_rooms: Dict[str, str]
    ) -> None:
        """
        Update room connections bidirectionally.
        If Room A connects north to Room B, Room B should connect south to Room A.
        """
        opposite_directions = {
            'north': 'south',
            'south': 'north',
            'east': 'west',
            'west': 'east',
            'up': 'down',
            'down': 'up'
        }
        
        cursor = self.db.cursor()
        
        for direction, target_room_id in connected_rooms.items():
            # Get the target room's current connections
            cursor.execute(
                "SELECT connected_rooms FROM rooms WHERE room_id = ?",
                (target_room_id,)
            )
            result = cursor.fetchone()
            
            if result:
                target_connections = json.loads(result[0])
                opposite_direction = opposite_directions.get(direction)
                
                # Add the reverse connection
                if opposite_direction:
                    target_connections[opposite_direction] = room_id
                    
                    cursor.execute(
                        "UPDATE rooms SET connected_rooms = ? WHERE room_id = ?",
                        (json.dumps(target_connections), target_room_id)
                    )
        
        self.db.commit()
```

### 4.2 Room Creation JSON Example

```json
{
  "room_id": "room_riverside_bend",
  "room_type": "outdoor",
  "creator_character_id": "char_a7f2c9e1",
  "created_date": "2025-12-21T16:12:45Z",
  
  "name": "The Riverside Bend",
  "description": "A gentle curve in the river where the water slows and deepens. Willows line the bank, their branches trailing in the water. The ground is muddy and slippery. You can hear the sound of the river, and occasionally the splash of fish.",
  
  "room_type": "outdoor",
  "difficulty_level": 5,
  
  "environmental_quirks": [
    {
      "quirk_id": "env_fast_flowing_water",
      "name": "Fast Flowing Water",
      "description": "Water moves quickly; affects timing and stability",
      "mechanical_effect": {
        "timing_modifier": 1,
        "stability_modifier": -1,
        "applies_to_actions": ["fishing", "wading", "swimming"]
      }
    },
    {
      "quirk_id": "env_slippery_ground",
      "name": "Slippery Ground",
      "description": "Muddy banks reduce grip and stability",
      "mechanical_effect": {
        "stability_modifier": -1,
        "applies_to_actions": ["walking", "standing", "climbing"]
      }
    }
  ],
  
  "connections": {
    "north": "room_forest_path",
    "south": "room_riverside_workshop",
    "east": "room_rocky_outcrop",
    "west": "room_willow_grove"
  },
  
  "creator_notes": "Built this room as a fishing spot. The fast water and slippery ground make it challenging, but that's the point. Wanted a place where my low grip strength would really matter.",
  
  "status": {
    "is_active": true,
    "last_modified": "2025-12-21T16:12:45Z"
  }
}
```

---

## Part 5: Action Resolution and Ledger System

### 5.1 Resolution Engine (Pseudo Code)

```python
"""
RESOLUTION ENGINE
=================
Actions are resolved through multiple axes, not single dice rolls.
Attributes determine how you fail, not whether you succeed.
"""

import json
import hashlib
from typing import Dict, List, Tuple


class ResolutionEngine:
    """
    Responsible for resolving actions through axis-based resolution.
    Produces both ledger entries (hard truth) and narrative interpretation (soft truth).
    """
    
    def __init__(self, database_connection):
        self.db = database_connection
    
    def resolve_action(
        self,
        character_id: str,
        action_type: str,
        room_id: str,
        items_used: List[str] = None,
        seed: str = None
    ) -> Tuple[Dict, Dict]:
        """
        Resolve an action through the axis-based system.
        
        Returns:
            Tuple of (ledger_entry, newspaper_article)
        """
        
        # Step 1: Load Character, Room, and Items
        character = self._load_character(character_id)
        room = self._load_room(room_id)
        items = [self._load_item(item_id) for item_id in (items_used or [])]
        
        # Step 2: Initialize Axes
        axes = self._initialize_axes(action_type)
        
        # Step 3: Apply Character Modifiers
        axes = self._apply_character_modifiers(axes, character, action_type)
        
        # Step 4: Apply Item Modifiers
        axes = self._apply_item_modifiers(axes, items, action_type)
        
        # Step 5: Apply Environmental Modifiers
        axes = self._apply_environmental_modifiers(axes, room, action_type)
        
        # Step 6: Resolve Action
        outcome, deviations = self._resolve_axes(axes, seed)
        
        # Step 7: Create Ledger Entry (hard truth)
        ledger_entry = self._create_ledger_entry(
            character_id, action_type, room_id, outcome, deviations, items
        )
        
        # Step 8: Create Narrative Interpretation (soft truth)
        newspaper_article = self._create_newspaper_article(
            ledger_entry, character, room
        )
        
        # Step 9: Persist
        self._save_ledger_entry(ledger_entry)
        self._save_newspaper_article(newspaper_article)
        
        return ledger_entry, newspaper_article
    
    def _initialize_axes(self, action_type: str) -> Dict:
        """Initialize the six resolution axes."""
        return {
            'timing': {'base': 0, 'deviation': 0},
            'precision': {'base': 0, 'deviation': 0},
            'stability': {'base': 0, 'deviation': 0},
            'visibility': {'base': 0, 'deviation': 0},
            'interpretability': {'base': 0, 'deviation': 0},
            'recovery_cost': {'base': 0, 'deviation': 0}
        }
    
    def _apply_character_modifiers(
        self,
        axes: Dict,
        character: Dict,
        action_type: str
    ) -> Dict:
        """
        Apply character attributes and quirks to the axes.
        
        Attributes determine magnitude of deviation.
        Quirks bias the axes before the action starts.
        """
        
        # Apply attribute modifiers
        for attr_name, attr_value in character['attributes'].items():
            # Low attributes increase deviation
            if attr_value <= 3:
                axes['precision']['base'] -= 2
                axes['stability']['base'] -= 1
            elif attr_value <= 5:
                axes['precision']['base'] -= 1
        
        # Apply quirk modifiers
        for quirk in character['quirks']:
            quirk_effects = self._get_quirk_effects(quirk['quirk_id'])
            for axis_name, modifier in quirk_effects.items():
                if axis_name in axes:
                    axes[axis_name]['base'] += modifier
        
        return axes
    
    def _apply_item_modifiers(
        self,
        axes: Dict,
        items: List[Dict],
        action_type: str
    ) -> Dict:
        """
        Apply item quirks to the axes.
        Items reorder which axis matters first.
        """
        
        for item in items:
            for quirk in item.get('quirks', []):
                quirk_effects = self._get_item_quirk_effects(quirk['quirk_id'])
                for axis_name, modifier in quirk_effects.items():
                    if axis_name in axes:
                        axes[axis_name]['base'] += modifier
        
        return axes
    
    def _apply_environmental_modifiers(
        self,
        axes: Dict,
        room: Dict,
        action_type: str
    ) -> Dict:
        """
        Apply environmental quirks to the axes.
        Rooms have quirks that affect action resolution.
        """
        
        for quirk_id in room.get('environmental_quirks', []):
            quirk_effects = self._get_environmental_quirk_effects(quirk_id)
            for axis_name, modifier in quirk_effects.items():
                if axis_name in axes:
                    axes[axis_name]['base'] += modifier
        
        return axes
    
    def _resolve_axes(
        self,
        axes: Dict,
        seed: str = None
    ) -> Tuple[str, Dict]:
        """
        Resolve the action by checking each axis for deviation.
        
        Returns:
            Tuple of (outcome, deviations)
        """
        
        # Generate deterministic random deviations
        if seed is None:
            seed = hashlib.sha256(str(axes).encode()).hexdigest()
        
        deviations = {}
        cascading_failure = False
        
        # Check each axis in order
        for axis_name, axis_data in axes.items():
            # Roll deviation (deterministic based on seed)
            deviation = self._roll_deviation(seed, axis_name)
            
            # Apply base modifier
            modified_deviation = deviation + axis_data['base']
            deviations[axis_name] = modified_deviation
            
            # Check if this axis causes failure
            if modified_deviation > 5:  # Threshold for failure
                # Check stability to see if it cascades
                if axes['stability']['base'] < 0:
                    cascading_failure = True
        
        # Determine outcome
        if cascading_failure:
            outcome = 'failure'
        elif sum(d for d in deviations.values() if d > 5) > 2:
            outcome = 'partial_success'
        else:
            outcome = 'success'
        
        return outcome, deviations
    
    def _roll_deviation(self, seed: str, axis_name: str) -> int:
        """Generate a deterministic deviation for an axis."""
        combined = f"{seed}:{axis_name}"
        hash_value = int(hashlib.sha256(combined.encode()).hexdigest(), 16)
        return (hash_value % 11) - 5  # Range: -5 to +5
    
    def _create_ledger_entry(
        self,
        character_id: str,
        action_type: str,
        room_id: str,
        outcome: str,
        deviations: Dict,
        items: List[Dict]
    ) -> Dict:
        """
        Create a ledger entry (hard truth).
        Deterministic, replayable from seed, never calls an LLM.
        """
        
        return {
            'ledger_id': str(uuid.uuid4()),
            'character_id': character_id,
            'action_type': action_type,
            'room_id': room_id,
            'action_timestamp': datetime.now().isoformat(),
            'outcome': outcome,
            'deviations': deviations,
            'items_used': [item['item_id'] for item in items],
            'interpretation': self._determine_interpretation(outcome, deviations),
            'blame_weight': self._calculate_blame_weight(outcome, deviations),
            'is_public': False
        }
    
    def _determine_interpretation(self, outcome: str, deviations: Dict) -> str:
        """Determine how the outcome is interpreted."""
        if outcome == 'success':
            return 'fortunate'
        elif outcome == 'partial_success':
            return 'avoidable'
        else:
            # Check if failure was inevitable
            if all(d > 5 for d in deviations.values()):
                return 'inevitable'
            else:
                return 'avoidable'
    
    def _calculate_blame_weight(self, outcome: str, deviations: Dict) -> float:
        """Calculate how much blame falls on the character (0.0 to 1.0)."""
        if outcome == 'success':
            return 0.0
        
        # More deviations = more blame
        num_bad_deviations = sum(1 for d in deviations.values() if d > 5)
        return min(1.0, num_bad_deviations / 6.0)
    
    def _create_newspaper_article(
        self,
        ledger_entry: Dict,
        character: Dict,
        room: Dict
    ) -> Dict:
        """
        Create a newspaper article (soft truth).
        Consumes ledger facts and produces language.
        May vary per context, may contradict itself narratively.
        """
        
        return {
            'article_id': str(uuid.uuid4()),
            'ledger_id': ledger_entry['ledger_id'],
            'headline': self._generate_headline(ledger_entry, character),
            'body_text': self._generate_body_text(ledger_entry, character, room),
            'tone': self._determine_tone(character),
            'bias_toward_character': self._calculate_bias(character),
            'published_date': datetime.now().isoformat(),
            'blamed_party': self._determine_blamed_party(ledger_entry, character),
            'praised_party': self._determine_praised_party(ledger_entry, character)
        }
    
    def _generate_headline(self, ledger_entry: Dict, character: Dict) -> str:
        """Generate a newspaper headline."""
        action = ledger_entry['action_type']
        outcome = ledger_entry['outcome']
        name = f"{character['given_name']} {character['family_name']}"
        
        if outcome == 'success':
            return f"{name} Succeeds at {action.title()}"
        elif outcome == 'partial_success':
            return f"{name}'s {action.title()} Partially Succeeds"
        else:
            return f"Another Failure for {name}"
    
    def _generate_body_text(
        self,
        ledger_entry: Dict,
        character: Dict,
        room: Dict
    ) -> str:
        """Generate newspaper body text."""
        # This would call an LLM in production
        # For now, return a template
        return f"In {room['name']}, {character['given_name']} attempted {ledger_entry['action_type']} with {ledger_entry['outcome']} result."
    
    def _determine_tone(self, character: Dict) -> str:
        """Determine the tone of the newspaper article."""
        if character['reputation']['score'] > 10:
            return 'sympathetic'
        elif character['reputation']['score'] < -10:
            return 'gossipy'
        else:
            return 'formal'
    
    def _calculate_bias(self, character: Dict) -> float:
        """Calculate bias toward the character (-1.0 to +1.0)."""
        return character['reputation']['score'] / 100.0
    
    def _determine_blamed_party(self, ledger_entry: Dict, character: Dict) -> str:
        """Determine who the newspaper blames."""
        if ledger_entry['blame_weight'] > 0.7:
            return character['given_name']
        elif ledger_entry['blame_weight'] > 0.3:
            return "circumstances"
        else:
            return "bad luck"
    
    def _determine_praised_party(self, ledger_entry: Dict, character: Dict) -> str:
        """Determine who the newspaper praises."""
        if ledger_entry['outcome'] == 'success':
            return character['given_name']
        else:
            return None
```

### 5.2 Ledger Entry JSON Example

```json
{
  "ledger_id": "ledger_f7a9e2c1",
  "character_id": "char_a7f2c9e1",
  "action_type": "fish",
  "room_id": "room_riverside_bend",
  "action_timestamp": "2025-12-21T17:30:15Z",
  
  "outcome": "failure",
  
  "axes": {
    "timing": {
      "base_modifier": 1,
      "deviation": 3,
      "final_value": 4,
      "notes": "Delayed feedback from item quirk"
    },
    "precision": {
      "base_modifier": -1,
      "deviation": 2,
      "final_value": 1,
      "notes": "Trembling hands quirk"
    },
    "stability": {
      "base_modifier": -3,
      "deviation": 4,
      "final_value": 1,
      "notes": "Low patience + slippery ground"
    },
    "visibility": {
      "base_modifier": 0,
      "deviation": 1,
      "final_value": 1,
      "notes": "Action clearly observable"
    },
    "interpretability": {
      "base_modifier": 2,
      "deviation": -1,
      "final_value": 1,
      "notes": "High cunning helps reinterpret"
    },
    "recovery_cost": {
      "base_modifier": 0,
      "deviation": 2,
      "final_value": 2,
      "notes": "Easy to try again"
    }
  },
  
  "contributing_factors": [
    "character_quirk_trembling_hands",
    "character_failing_impulse_control",
    "item_quirk_delayed_feedback",
    "environmental_quirk_fast_flowing_water",
    "character_attribute_patience_low"
  ],
  
  "items_used": ["item_f3a8c2b9"],
  
  "interpretation": "avoidable",
  "blame_weight": 0.8,
  
  "resolution_seed": "a7f2c9e1_fish_17301500_xyz",
  "is_public": false
}
```

### 5.3 Newspaper Article JSON Example

```json
{
  "article_id": "article_b2d4f8a3",
  "ledger_id": "ledger_f7a9e2c1",
  
  "headline": "Third Time This Week: Grindlewick's Fishing Troubles Continue",
  
  "body_text": "At the Riverside Bend this afternoon, Grindlewick Thrum-of-Three-Keys (Acting) made another attempt at fishing. Sources say the catch slipped from her pole before she could reel it in. Locals blame her impatience. Experts disagree, pointing to the condition of her equipment. Either way, the fish got away.",
  
  "tone": "gossipy",
  "bias_toward_character": -0.05,
  
  "published_date": "2025-12-21T18:00:00Z",
  "publication_source": "The Daily Ledger",
  
  "blamed_party": "Grindlewick's impatience",
  "praised_party": null,
  
  "narrative_notes": "The newspaper focuses on the repeated failure rather than the specific circumstances. This reinforces Grindlewick's emerging reputation as someone who struggles with fishing."
}
```

---

## Part 6: In-Game Output Examples

### 6.1 Character Issuance Output

```
═══════════════════════════════════════════════════════════════════════════════
                        PERSONNEL FILE ISSUANCE NOTICE
═══════════════════════════════════════════════════════════════════════════════

TO: New Functionary
FROM: Bureau of Goblin Allocation
DATE: 21 December, 2025
RE: Your Assigned Identity (Final)

Dear Functionary,

Your application for employment has been processed. Congratulations. You have been
issued the following identity, effective immediately. This assignment is permanent
and cannot be modified.

───────────────────────────────────────────────────────────────────────────────
NAME:                   Grindlewick Thrum-of-Three-Keys (Acting)
SEX:                    Female
ISSUED DATE:            21 December, 2025
───────────────────────────────────────────────────────────────────────────────

ATTRIBUTE ASSESSMENT:

  Cunning:              ████████░░ (8/10)    [Above Average]
  Grip Strength:        ███░░░░░░░ (3/10)    [Below Average]
  Patience:             ██░░░░░░░░ (2/10)    [Poor]
  Spatial Sense:        ███████░░░ (7/10)    [Above Average]
  Stamina:              █████░░░░░ (5/10)    [Average]
  Book Learning:        ████░░░░░░ (4/10)    [Below Average]
  Luck (Administrative):██████░░░░ (6/10)    [Average]

───────────────────────────────────────────────────────────────────────────────

MANDATORY QUIRKS:

1. Panics When Watched
   You become flustered when observed by others. Stability reduced by 2 when
   an NPC is watching.

2. Trembling Hands
   Your hands shake slightly. Precision reduced by 1 in fine motor tasks.

3. Lucky Mishaps (HIDDEN)
   [This quirk will be discovered through gameplay]

───────────────────────────────────────────────────────────────────────────────

PERSISTENT FAILINGS:

1. Poor Numeracy
   You struggle with calculations. You will miscalculate resources by 10-20%
   even when tasks succeed.

2. Poor Impulse Control
   You act too quickly in time-sensitive situations.

───────────────────────────────────────────────────────────────────────────────

SPECIALIZATIONS (USELESS):

1. Expert in Obsolete Measurement Systems
   You can convert between fathoms, cubits, and hand-spans. Nobody uses these
   anymore.

2. Knows Every Bridge by Name
   You can name any bridge in the city, but not where it goes.

───────────────────────────────────────────────────────────────────────────────

INHERITED REPUTATION:

  Current Score: -5 (Slightly Negative)

  Rumours:
  • Rumoured to be a distant cousin of a disgraced guild master
  • Clerical records suggest you once failed a basic numeracy test
  • Locals expect you to be unreliable

───────────────────────────────────────────────────────────────────────────────

WELCOME TO THE UNDERTAKING.

You are now a functionary in the bureaucratic machine. Your job is to survive.
Your failures will be recorded. Your successes will be questioned. Your quirks
will define you.

The system does not care about you. But the system is all you have.

Begin your assignment.

═══════════════════════════════════════════════════════════════════════════════
```

### 6.2 Item Creation Output

```
═══════════════════════════════════════════════════════════════════════════════
                            ITEM CREATION LOG
═══════════════════════════════════════════════════════════════════════════════

ITEM CREATED: Grindlewick's Weathered Fishing Pole
ITEM ID: item_f3a8c2b9
CREATED BY: Grindlewick Thrum-of-Three-Keys (Acting)
DATE: 21 December, 2025, 15:45

───────────────────────────────────────────────────────────────────────────────

DESCRIPTION:
A fishing pole made from willow wood with a gut line. The handle has been
shortened, and the reel mechanism is slightly loose.

MATERIAL: Willow wood, gut line, brass reel
CONDITION: Worn

───────────────────────────────────────────────────────────────────────────────

ITEM QUIRKS:

1. Delayed Feedback
   Bite detection is delayed by 0.5-1 second. When fishing, the timing axis
   is modified by +1. This quirk interacts unpredictably with low patience.

2. Loose Reel
   The reel mechanism slips occasionally. Precision reduced by 1, stability
   reduced by 1 when reeling in.

───────────────────────────────────────────────────────────────────────────────

MAKER'S PROFILE:

Creator: Grindlewick Thrum-of-Three-Keys (Acting)

Maker's Attributes:
  Cunning: 8        Grip Strength: 3     Patience: 2
  Spatial Sense: 7  Stamina: 5           Book Learning: 4
  Luck (Admin): 6

Maker's Quirks:
  • Panics When Watched
  • Trembling Hands
  • Lucky Mishaps (Hidden)

Maker's Notes:
"Shortened the handle to save weight—my grip strength isn't great. Reel
mechanism is loose because I was in a hurry. The delayed feedback is
intentional; I wanted to slow down the bite detection so I'd have time to
react."

───────────────────────────────────────────────────────────────────────────────

FROZEN DECISIONS:
This item carries the frozen decision-making of its maker. The shortened handle
reflects Grindlewick's weak grip. The loose reel reflects her impatience. The
delayed feedback reflects her attempt to compensate for her low patience.

When you use this pole, you are using Grindlewick's solutions to her problems.
Whether they solve YOUR problems is another matter entirely.

═══════════════════════════════════════════════════════════════════════════════
```

### 6.3 Room Creation Output

```
═══════════════════════════════════════════════════════════════════════════════
                            ROOM CREATION LOG
═══════════════════════════════════════════════════════════════════════════════

ROOM CREATED: The Riverside Bend
ROOM ID: room_riverside_bend
CREATED BY: Grindlewick Thrum-of-Three-Keys (Acting)
DATE: 21 December, 2025, 16:12

───────────────────────────────────────────────────────────────────────────────

DESCRIPTION:
A gentle curve in the river where the water slows and deepens. Willows line
the bank, their branches trailing in the water. The ground is muddy and
slippery. You can hear the sound of the river, and occasionally the splash
of fish.

ROOM TYPE: Outdoor
DIFFICULTY LEVEL: 5/10

───────────────────────────────────────────────────────────────────────────────

ENVIRONMENTAL QUIRKS:

1. Fast Flowing Water
   The water moves quickly. Timing axis modified by +1, stability axis
   modified by -1. Affects: fishing, wading, swimming.

2. Slippery Ground
   Muddy banks reduce grip and stability. Stability axis modified by -1.
   Affects: walking, standing, climbing.

───────────────────────────────────────────────────────────────────────────────

CONNECTIONS:

  North: Forest Path (room_forest_path)
  South: Riverside Workshop (room_riverside_workshop)
  East: Rocky Outcrop (room_rocky_outcrop)
  West: Willow Grove (room_willow_grove)

───────────────────────────────────────────────────────────────────────────────

CREATOR'S NOTES:

"Built this room as a fishing spot. The fast water and slippery ground make
it challenging, but that's the point. Wanted a place where my low grip
strength would really matter."

───────────────────────────────────────────────────────────────────────────────

WORLD INTEGRATION:
This room has been added to the world. Other players can now visit it, and
their actions will be resolved using the environmental quirks you've defined.

═══════════════════════════════════════════════════════════════════════════════
```

### 6.4 Action Resolution Output

```
═══════════════════════════════════════════════════════════════════════════════
                        ACTION RESOLUTION LOG
═══════════════════════════════════════════════════════════════════════════════

ACTION: Fishing
CHARACTER: Grindlewick Thrum-of-Three-Keys (Acting)
LOCATION: The Riverside Bend
TIME: 21 December, 2025, 17:30
ITEM USED: Grindlewick's Weathered Fishing Pole

───────────────────────────────────────────────────────────────────────────────

RESOLUTION AXES:

  TIMING:
    Base Modifier: +1 (Delayed Feedback from pole)
    Deviation: +3
    Final Value: +4 (LATE)
    Notes: Bite detected late due to pole quirk

  PRECISION:
    Base Modifier: -1 (Trembling Hands)
    Deviation: +2
    Final Value: +1 (ACCEPTABLE)
    Notes: Hands steady enough for this task

  STABILITY:
    Base Modifier: -3 (Low Patience + Slippery Ground)
    Deviation: +4
    Final Value: +1 (MARGINAL)
    Notes: Barely holding it together

  VISIBILITY:
    Base Modifier: 0
    Deviation: +1
    Final Value: +1 (VISIBLE)
    Notes: Everyone can see this happening

  INTERPRETABILITY:
    Base Modifier: +2 (High Cunning)
    Deviation: -1
    Final Value: +1 (FAVORABLE)
    Notes: Can blame circumstances

  RECOVERY COST:
    Base Modifier: 0
    Deviation: +2
    Final Value: +2 (EASY)
    Notes: Can try again immediately

───────────────────────────────────────────────────────────────────────────────

CONTRIBUTING FACTORS:
  • Character Quirk: Trembling Hands
  • Character Failing: Poor Impulse Control
  • Item Quirk: Delayed Feedback
  • Environmental Quirk: Fast Flowing Water
  • Character Attribute: Low Patience (2/10)

───────────────────────────────────────────────────────────────────────────────

OUTCOME: FAILURE

The fish bit, but the delayed feedback from your pole meant you didn't feel it
until too late. By the time you reeled in, the fish had already escaped. Your
impatience didn't help—you jerked the pole too quickly, and the loose reel
slipped.

INTERPRETATION: Avoidable
BLAME WEIGHT: 0.8 (Mostly your fault)

───────────────────────────────────────────────────────────────────────────────

LEDGER ENTRY CREATED: ledger_f7a9e2c1

This action has been recorded in the ledger. It is now permanent data that
will affect future actions and reputation.

═══════════════════════════════════════════════════════════════════════════════
```

### 6.5 Newspaper Article Output

```
═══════════════════════════════════════════════════════════════════════════════
                          THE DAILY LEDGER
                    21 December, 2025 - Evening Edition
═══════════════════════════════════════════════════════════════════════════════

HEADLINE: Third Time This Week: Grindlewick's Fishing Troubles Continue

───────────────────────────────────────────────────────────────────────────────

At the Riverside Bend this afternoon, Grindlewick Thrum-of-Three-Keys (Acting)
made another attempt at fishing. Sources say the catch slipped from her pole
before she could reel it in.

Locals blame her impatience. "She never waits for the right moment," said one
witness who requested anonymity. "Always rushing."

Experts disagree. A master craftsman examined her pole and noted that the reel
mechanism is loose. "The tool is as much to blame as the user," he said.

Either way, the fish got away. This is the third failed fishing attempt this
week for the Acting functionary. Her reputation in the fishing community
continues to decline.

When asked for comment, Grindlewick said only: "The river was too fast. My
pole isn't suited for these conditions."

The ledger records the facts. The river was indeed fast. The pole did have
issues. But the ledger also notes that Grindlewick's patience is notably low,
and that she acted too quickly when she felt the bite.

Who is to blame? The river? The pole? The functionary? The ledger knows.
The newspaper tells a story.

═══════════════════════════════════════════════════════════════════════════════
```

---

## Part 7: Complete Code Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PLAYER INITIATES ACTION                              │
│                    (e.g., "I want to go fishing")                            │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LOAD CHARACTER, ROOM, ITEMS                               │
│                                                                               │
│  • Fetch character from database (attributes, quirks, failings)             │
│  • Fetch room from database (environmental quirks, difficulty)              │
│  • Fetch items from database (item quirks, maker profile)                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INITIALIZE RESOLUTION AXES                              │
│                                                                               │
│  • Timing       (when something happens)                                    │
│  • Precision    (how exact an action must be)                               │
│  • Stability    (how tolerant the system is to deviation)                   │
│  • Visibility   (how observable an error is)                                │
│  • Interpretability (how outcomes are judged)                               │
│  • Recovery Cost (effort to correct or undo)                                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  APPLY CHARACTER MODIFIERS TO AXES                           │
│                                                                               │
│  • Low attributes increase deviation                                        │
│  • Quirks bias the axes before the action starts                            │
│  • Failings apply even on "success"                                         │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    APPLY ITEM MODIFIERS TO AXES                              │
│                                                                               │
│  • Item quirks reorder which axis matters first                             │
│  • Maker's decisions become frozen in the item                              │
│  • Item interacts unpredictably with character quirks                       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 APPLY ENVIRONMENTAL MODIFIERS TO AXES                        │
│                                                                               │
│  • Room environmental quirks affect action resolution                       │
│  • Difficulty level affects baseline deviation                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESOLVE AXES                                         │
│                                                                               │
│  • Generate deterministic deviations (seeded for replay)                    │
│  • Check each axis against thresholds                                       │
│  • Determine if deviations cascade into failure                             │
│  • Calculate outcome (success, partial success, failure)                    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CREATE LEDGER ENTRY (HARD TRUTH)                          │
│                                                                               │
│  • Record character, action, room, outcome                                  │
│  • Record all axis deviations                                               │
│  • Record contributing factors                                              │
│  • Record interpretation (avoidable, inevitable, fortunate)                 │
│  • Record blame weight (0.0 to 1.0)                                         │
│  • Store resolution seed for deterministic replay                           │
│  • Persist to database                                                      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               CREATE NEWSPAPER ARTICLE (SOFT TRUTH)                          │
│                                                                               │
│  • Consume ledger facts                                                     │
│  • Generate headline (may call LLM for flavor)                              │
│  • Generate body text (narrative interpretation)                            │
│  • Determine tone based on character reputation                             │
│  • Determine who to blame and praise                                        │
│  • Persist to database                                                      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISPLAY RESULTS TO PLAYER                                 │
│                                                                               │
│  • Show action resolution (all axis deviations)                             │
│  • Show outcome and interpretation                                          │
│  • Show contributing factors                                                │
│  • Show newspaper article (if published)                                    │
│  • Update character reputation based on outcome                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Conclusion

This pseudo code demonstrates The Undertaking's core systems:

1. **Character Issuance**: Players receive immutable goblins with uneven attributes, mandatory quirks, persistent failings, and inherited reputation.

2. **Item Creation**: Items are frozen decisions that carry the maker's attributes, quirks, and choices. They interact unpredictably with character quirks.

3. **Room Creation**: Rooms have environmental quirks that affect action resolution. Players can create and link new rooms to the world.

4. **Action Resolution**: Actions are resolved through six axes (Timing, Precision, Stability, Visibility, Interpretability, Recovery Cost). Attributes and quirks determine how you fail, not whether you succeed.

5. **Ledger and Narrative**: The ledger records hard truth (deterministic, replayable, authoritative). The newspaper provides soft truth (narrative interpretation, bias, storytelling).

6. **Emergence**: Without optimization, specialization emerges from failure history. A goblin who fails repeatedly at fishing but succeeds at salvage becomes the salvage goblin.

The system resists optimization at every level while providing rich, emergent gameplay where failure is data and identity is imposed, not chosen.
