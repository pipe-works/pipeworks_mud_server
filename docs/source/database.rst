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
    | NN  is_active          INTEGER   | DEFAULT 1
    | NN  is_guest           INTEGER   | DEFAULT 0
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
    | NN  name               TEXT      | UNIQUE
    | NN  inventory          TEXT      | DEFAULT '[]'
    | NN  is_guest_created   INTEGER   | DEFAULT 0
    |     created_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    |     updated_at         TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | character_locations              |
    +----------------------------------+
    | PK  character_id      INTEGER    | FK -> characters.id (ON DELETE CASCADE)
    | NN  room_id           TEXT       |
    |     updated_at        TIMESTAMP  | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+


    +----------------------------------+
    | sessions                         |
    +----------------------------------+
    | PK  id                 INTEGER   |
    | NN  user_id            INTEGER   | FK -> users.id (ON DELETE CASCADE)
    |     character_id       INTEGER   | FK -> characters.id (ON DELETE SET NULL)
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
    | NN  room               TEXT      |
    |     recipient_character_id INTEGER | FK -> characters.id (ON DELETE SET NULL)
    |     timestamp          TIMESTAMP | DEFAULT CURRENT_TIMESTAMP
    +----------------------------------+
