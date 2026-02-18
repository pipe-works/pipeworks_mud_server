Database
========

Current Database Schema
-----------------------

The ASCII diagram below reflects the current SQLite schema in ``data/mud.db``.

::

    +----------------------------------+
    | users                            |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  username           TEXT      | UNIQUE
    | NN  password_hash      TEXT      |
    |     email_hash          TEXT     | UNIQUE
    | NN  role               TEXT      | DEFAULT 'player'
    | NN  is_active          INTEGER   | DEFAULT 1, CHECK IN (0, 1)
    | NN  is_guest           INTEGER   | DEFAULT 0, CHECK IN (0, 1)
    |     guest_expires_at   TIMESTAMP |
    | NN  account_origin     TEXT      | DEFAULT 'legacy'
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     last_login         TIMESTAMP |
    |     tombstoned_at      TIMESTAMP |
    +----------------------------------+


    +----------------------------------+
    | characters                       |
    +----------------------------------+
    | PK  id                 INTEGER   |
    |     user_id            INTEGER   | FK -> users.id (ON DELETE SET NULL)
    | NN  name               TEXT      |
    | NN  world_id           TEXT      | PART OF UNIQUE(world_id, name)
    | NN  inventory          TEXT      | DEFAULT '[]'
    | NN  is_guest_created   INTEGER   | DEFAULT 0, CHECK IN (0, 1)
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     updated_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     base_state_json    TEXT      |
    |     current_state_json TEXT      |
    |     state_seed         INTEGER   | DEFAULT 0, CHECK >= 0
    |     state_version      TEXT      |
    |     state_updated_at   TIMESTAMP |
    +----------------------------------+


    +----------------------------------+
    | character_locations              |
    +----------------------------------+
    | PK  character_id      INTEGER    | FK -> characters.id (ON DELETE CASCADE)
    | NN  world_id           TEXT      |
    | NN  room_id            TEXT      |
    |     updated_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | sessions                         |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  user_id            INTEGER   | FK -> users.id (ON DELETE CASCADE)
    |     character_id       INTEGER   | FK -> characters.id (ON DELETE SET NULL)
    |     world_id           TEXT      |
    | NN  session_id         TEXT      | UNIQUE
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     last_activity      TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     expires_at         TIMESTAMP |
    |     client_type        TEXT      | DEFAULT 'unknown'
    +----------------------------------+


    +----------------------------------+
    | chat_messages                    |
    +----------------------------------+
    | PK  id                 INTEGER   |
    |     character_id       INTEGER   | FK -> characters.id (ON DELETE SET NULL)
    |     user_id            INTEGER   | FK -> users.id (ON DELETE SET NULL)
    | NN  message            TEXT      |
    | NN  world_id           TEXT      |
    | NN  room               TEXT      |
    |     recipient_character_id INTEGER | FK -> characters.id (ON DELETE SET NULL)
    |     timestamp          TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | worlds                           |
    +----------------------------------+
    | PK  id                 TEXT      |
    | NN  name               TEXT      |
    |     description        TEXT      |
    | NN  is_active          INTEGER   | DEFAULT 1, CHECK IN (0, 1)
    | NN  config_json        TEXT      | DEFAULT '{}'
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | world_permissions                |
    +----------------------------------+
    | PK  user_id            INTEGER   | FK -> users.id (ON DELETE CASCADE)
    | PK  world_id           TEXT      | FK -> worlds.id (ON DELETE CASCADE)
    | NN  can_access         INTEGER   | DEFAULT 1, CHECK IN (0, 1)
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | axis                             |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  world_id           TEXT      |
    | NN  name               TEXT      |
    |     description        TEXT      |
    |     ordering_json      TEXT      |
    +----------------------------------+


    +----------------------------------+
    | axis_value                       |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  axis_id            INTEGER   | FK -> axis.id (ON DELETE CASCADE)
    | NN  value              TEXT      |
    |     min_score          REAL      |
    |     max_score          REAL      |
    |     ordinal            INTEGER   |
    +----------------------------------+


    +----------------------------------+
    | event_type                       |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  world_id           TEXT      |
    | NN  name               TEXT      |
    |     description        TEXT      |
    +----------------------------------+


    +----------------------------------+
    | character_axis_score             |
    +----------------------------------+
    | PK  character_id      INTEGER    | FK -> characters.id (ON DELETE CASCADE)
    | PK  axis_id           INTEGER    | FK -> axis.id (ON DELETE CASCADE)
    | NN  world_id           TEXT      |
    | NN  axis_score         REAL      |
    |     updated_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | event                            |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  world_id           TEXT      |
    | NN  event_type_id      INTEGER   | FK -> event_type.id
    |     timestamp          TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | event_entity_axis_delta          |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  event_id           INTEGER   | FK -> event.id (ON DELETE CASCADE)
    | NN  character_id       INTEGER   | FK -> characters.id (ON DELETE CASCADE)
    | NN  axis_id            INTEGER   | FK -> axis.id (ON DELETE CASCADE)
    | NN  old_score          REAL      |
    | NN  new_score          REAL      |
    | NN  delta              REAL      |
    +----------------------------------+


    +----------------------------------+
    | event_metadata                   |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  event_id           INTEGER   | FK -> event.id (ON DELETE CASCADE)
    | NN  key                TEXT      |
    | NN  value              TEXT      |
    +----------------------------------+

Notes
-----

- ``users.email_hash`` stores a hashed email address (no plaintext email). The column
  is nullable during development but intended to be required later; the unique index
  keeps that migration path open.
- ``users.is_guest`` + ``users.guest_expires_at`` model temporary accounts that are
  auto-purged; the user row is deleted and related characters are unlinked
  (``user_id`` set to NULL) rather than deleted.
- ``characters.name`` is a plain TEXT field, so names with spaces (e.g., first + last)
  are supported; uniqueness is enforced per world by ``UNIQUE(world_id, name)``.
- Session integrity is enforced by SQLite triggers:
  account-only sessions must keep both ``character_id`` and ``world_id`` NULL;
  in-world sessions must set both and match character ownership/world.
- Axis state is tracked in **normalized tables** (``axis``, ``axis_value``,
  ``character_axis_score``) with an **event ledger** (``event*`` tables).
- ``world_permissions`` stores invite-style access grants. Open-world access is
  policy-driven from config and may not require a row in this table.
- Hot-path indexes are intentionally maintained for world-scoped session activity,
  character ownership queries, and room chat history lookups.
- Runtime code should import DB operations from ``mud_server.db.facade``;
  ``mud_server.db.database`` is a compatibility re-export surface.
