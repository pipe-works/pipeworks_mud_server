Security
========

This document describes the security features and best practices implemented
in the PipeWorks MUD Server.

.. contents:: Table of Contents
   :local:
   :depth: 2

Password Security
-----------------

Password Policy
~~~~~~~~~~~~~~~

The MUD Server implements a comprehensive password policy based on NIST SP 800-63B
guidelines and industry best practices. The policy emphasizes length over complexity
and blocks common/compromised passwords.

**Policy Levels**

Three predefined policy levels are available:

.. list-table:: Password Policy Levels
   :header-rows: 1
   :widths: 15 15 70

   * - Level
     - Min Length
     - Features
   * - BASIC
     - 8 chars
     - Common password check only
   * - STANDARD
     - 12 chars
     - Common passwords, sequential/repeated char detection
   * - STRICT
     - 16 chars
     - All checks + uppercase, lowercase, digit, special required

The **STANDARD** policy is used by default for all user registration and password
changes.

**STANDARD Policy Requirements**

- Minimum 12 characters (NIST recommended)
- Cannot be a commonly used password (checked against 150+ known weak passwords)
- Cannot contain sequential characters (abc, 123, xyz)
- Cannot repeat the same character more than 3 times (aaa, 1111)

**Password Strength Feedback**

Users receive detailed feedback when their password doesn't meet requirements:

.. code-block:: text

   Password does not meet requirements:
     - Password must be at least 12 characters long (currently 8)
     - This password is too common and easily guessed.
     - Password contains sequential characters (abc).

Password Hashing
~~~~~~~~~~~~~~~~

All passwords are hashed using **bcrypt** via the passlib library before storage.
Bcrypt provides several security features:

- **Automatic salting**: Each password gets a unique random salt, preventing
  rainbow table attacks.

- **Adaptive cost factor**: Hashing is intentionally slow (~100ms) to make
  brute force attacks computationally expensive.

- **One-way function**: Password hashes cannot be reversed to obtain the
  original password.

- **Constant-time comparison**: Password verification uses constant-time
  comparison to prevent timing attacks.

**Hash Format**

Passwords are stored in bcrypt format::

   $2b$12$xKzN8o5qCqKqV8xKzN8o5.U9vKzN8o5qCqKqV8xKzN8o5qCqKq

Where:
- ``$2b$`` - bcrypt algorithm identifier
- ``12`` - cost factor (2^12 = 4,096 iterations)
- First 22 characters after cost - salt
- Remaining characters - hash

Common Password Detection
~~~~~~~~~~~~~~~~~~~~~~~~~

The password policy checks against a list of 150+ commonly used passwords,
including:

- Top 100 most common passwords from breach analysis
- Common keyboard patterns (qwerty, 123456, etc.)
- Common names with numbers (john123, admin123)
- Leet-speak variants (p@ssw0rd, @dm1n)

**Leet-speak Detection**

The system also detects common character substitutions:

.. list-table:: Character Substitutions Detected
   :header-rows: 1

   * - Original
     - Substitutions
   * - a
     - @, 4
   * - e
     - 3
   * - i
     - 1, !
   * - o
     - 0
   * - s
     - 5, $

For example, ``p@ssw0rd`` is detected as a variant of ``password``.

Authentication
--------------

Session Management
~~~~~~~~~~~~~~~~~~

The server uses UUID-based session tokens for authentication:

1. **Login**: User provides username/password, receives UUID session_id
2. **Requests**: All authenticated endpoints require session_id
3. **Validation**: Server verifies session exists and extracts (username, role)
4. **Logout**: Session is removed from the database

**Session Storage**

Sessions are stored in the database (source of truth). Session expiration
is enforced using a TTL and can be configured for sliding expiration.

**Session Expiration**

- **TTL**: Sessions expire after a configurable period of inactivity.
- **Sliding expiration**: When enabled, each authenticated request extends
  the expiry time by the TTL.

Role-Based Access Control
~~~~~~~~~~~~~~~~~~~~~~~~~

Four user roles with hierarchical permissions:

.. list-table:: User Roles and Permissions
   :header-rows: 1
   :widths: 15 85

   * - Role
     - Permissions
   * - Player
     - Basic gameplay (move, chat, inventory, explore)
   * - WorldBuilder
     - Player permissions + create/edit rooms and items (future)
   * - Admin
     - Player permissions + create users, kick/ban users, view logs, stop server
   * - Superuser
     - All permissions including role management

**Checking Permissions**

.. code-block:: python

   from mud_server.api.permissions import has_permission, Permission

   if has_permission(role, Permission.MANAGE_USERS):
       # Allow user management
       pass

API Security
------------

Request Validation
~~~~~~~~~~~~~~~~~~

All API requests are validated using Pydantic models:

- Type checking and coercion
- Required field validation
- Length constraints
- Format validation

**Example Request Validation**

.. code-block:: python

   class RegisterRequest(BaseModel):
       username: str
       password: str
       password_confirm: str

   # Automatic validation on request

CORS Configuration
~~~~~~~~~~~~~~~~~~

CORS origins are configured via ``config/server.ini`` or environment variables:

**Config file** (config/server.ini):

.. code-block:: ini

   [security]
   # Production mode disables /docs endpoints
   production = true

   # Comma-separated list of allowed origins
   cors_origins = https://yourdomain.com, https://api.yourdomain.com

   # Allow credentials (cookies, auth headers)
   cors_allow_credentials = true

**Environment variable** (overrides config file):

.. code-block:: bash

   export MUD_CORS_ORIGINS=https://yourdomain.com
   export MUD_PRODUCTION=true

.. warning::

   Never use wildcard origins (``*``) in production with ``allow_credentials=true``.
   See ``config/server.example.ini`` for all security configuration options.

Error Handling
~~~~~~~~~~~~~~

Security-sensitive errors return generic messages to prevent information leakage:

- Invalid credentials: "Invalid username or password" (doesn't reveal which)
- Session errors: "Invalid or expired session"
- Permission errors: "Access denied"

Database Security
-----------------

SQLite Security
~~~~~~~~~~~~~~~

The SQLite database (``data/mud.db``) stores sensitive data:

- Password hashes (never plaintext passwords)
- Session tokens
- User roles and permissions

**Best Practices**

1. Set appropriate file permissions (600 or 640)
2. Don't expose the database file via web server
3. Back up regularly but secure backup files
4. Consider encryption at rest for sensitive deployments

Input Sanitization
~~~~~~~~~~~~~~~~~~

All user input is sanitized before database operations:

- Parameterized queries prevent SQL injection
- Input validation before any database operation
- Username/password length limits enforced

Security Checklist
------------------

Development
~~~~~~~~~~~

.. code-block:: text

   [ ] Change default superuser credentials immediately
   [ ] Use HTTPS for all connections (when exposing to network)
   [ ] Review CORS settings for your deployment
   [ ] Keep dependencies updated (pip install -U -r requirements.txt)
   [ ] Run security scans (bandit, safety)

Production
~~~~~~~~~~

.. code-block:: text

   [ ] Use strong, unique passwords for all accounts
   [ ] Set up proper firewall rules
   [ ] Enable HTTPS with valid certificates
   [ ] Restrict CORS to specific origins
   [ ] Configure rate limiting (not yet implemented)
   [ ] Set up log monitoring
   [ ] Regular security audits
   [ ] Database backups with encryption

Known Limitations
-----------------

The current implementation has some security limitations that are documented
for transparency:

1. **No session expiration**: Sessions don't expire automatically. Implement
   timeout logic for production.

2. **No rate limiting**: Login endpoints don't rate limit requests. This makes
   brute force attacks possible.

3. **Memory session storage**: Sessions are lost on server restart. Consider
   Redis or database-only sessions for production.

4. **No email verification**: User registration doesn't require email
   verification.

5. **No two-factor authentication**: 2FA is not implemented.

6. **No password recovery**: No password reset functionality via email.

These limitations are acceptable for a proof-of-concept but should be
addressed before production deployment.

Security Contact
----------------

If you discover a security vulnerability, please report it responsibly:

1. **Do not** create a public GitHub issue
2. Contact the maintainers privately
3. Provide detailed reproduction steps
4. Allow time for a fix before public disclosure

See Also
--------

- :doc:`architecture` - System architecture and components
- :doc:`api_reference` - API endpoint documentation
- :mod:`mud_server.api.password_policy` - Password policy module documentation
- :mod:`mud_server.api.password` - Password hashing module documentation
