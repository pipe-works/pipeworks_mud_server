Play Web UI
===========

Overview
--------

The play experience is served by a **single HTML shell** at ``/play`` and
``/play/<world_id>``. That shell contains three UI states:

* **Login (logged out)**
* **World select (user portal)**
* **In-world UI**

Client-side code in ``play.js`` toggles those states by setting the ``hidden``
attribute on each section. World-specific CSS and JS are optionally loaded
when ``/play/<world_id>`` is used.

Routing model
-------------

The following routes all return the same shell:

* ``/play``
* ``/play/<world_id>``
* ``/play/<world_id>/<any-subpath>``

This keeps routing simple and lets the client manage navigation inside the
world UI. World selection updates the location to ``/play/<world_id>``.

Files and structure
-------------------

The play UI is split into shared assets and per-world assets:

.. code-block:: text

   src/mud_server/web/templates/play_shell.html
   src/mud_server/web/static/play/css/
   ├── fonts.css
   ├── shared-base.css
   ├── shell.css
   └── worlds/
       └── <world_id>.css
   src/mud_server/web/static/play/js/
   ├── play.js
   └── worlds/
       └── <world_id>.js

CSS layering order
------------------

The shell loads styles in this order:

1. ``fonts.css`` (font-face declarations)
2. ``shared-base.css`` (tokens, resets, shared utilities)
3. ``shell.css`` (layout for login + world select states)
4. ``worlds/<world_id>.css`` (world-specific layout and overrides)

World styles should override shared defaults and may add layout rules for
``.main-layout`` and its child elements.

Play shell sections
-------------------

All three UI states live in ``play_shell.html`` and are shown/hidden by
``play.js``. The states are identified by ``data-play-state`` attributes.

.. code-block:: html

   <!-- LOGIN STATE (LOGGED OUT) -->
   <section class="play-state play-state--logged-out" data-play-state="logged-out">
     ...
   </section>

   <!-- WORLD SELECT STATE (USER PORTAL) -->
   <section class="play-state play-state--select" data-play-state="select-world" hidden>
     ...
   </section>

   <!-- GAME UI (IN WORLD) -->
   <div class="main-layout" data-play-state="in-world" hidden>
     ...
   </div>

``play.js`` sets ``hidden`` on these sections to switch the visible state.
If you add new rules that change display for these sections, keep the global
``[hidden] { display: none !important; }`` rule so the toggling remains
reliable.

Account Dashboard Layout (Select-World State)
----------------------------------------------

The select-world state now renders as a centered 3-column dashboard:

* Left column: 25% (world navigation and policy hints)
* Center column: 50% (character selector, feedback, actions)
* Right column: 25% (account/policy summary)

On mobile (``max-width: 900px``), columns collapse to a single stacked layout.

Character creation and world-entry behavior:

* ``Enter world`` remains disabled until a concrete character is selected.
* ``Generate character`` calls ``POST /characters/create`` for the selected world.
* Invite-only worlds can appear in the selector with locked labels for visibility.
* Locked worlds do not fetch characters and block create/select actions.

World UI scaffold
-----------------

The game UI skeleton lives in the ``in-world`` section of ``play_shell.html``.
It mirrors the Daily Undertaking layout and provides these main blocks:

* ``.character-panel`` (left column)
* ``.content-area`` (center output + command input)
* ``.right-panel`` (inventory, quests, notes)

You can keep the structure and replace the placeholder text as you wire in
real data.

Creating a new world UI
-----------------------

1. **Pick a world id**

   The world id is the slug used by the server (for example ``pipeworks_web``).
   This must match the world registry entry that the API returns in
   ``available_worlds``.

2. **Add world CSS**

   Create ``src/mud_server/web/static/play/css/worlds/<world_id>.css``. Use
   shared tokens from ``shared-base.css`` and override layout rules as needed.

   Example:

   .. code-block:: css

      /* worlds/ledgerfall.css */
      body {
        background: var(--paper);
        color: var(--ink-newsprint-black);
        font-family: var(--font-body);
      }

      .main-layout {
        grid-template-columns: 260px 1fr 260px;
      }

3. **Add world JS**

   Create ``src/mud_server/web/static/play/js/worlds/<world_id>.js``. The
   module runs only when ``/play/<world_id>`` is loaded.

   Example:

   .. code-block:: javascript

      // worlds/ledgerfall.js
      (() => {
        const worldId = document.body?.dataset?.worldId;
        if (worldId !== 'ledgerfall') {
          return;
        }

        const output = document.getElementById('gameOutput');
        if (output) {
          output.insertAdjacentHTML(
            'beforeend',
            '<div class="output-text">Ledgerfall UI ready.</div>'
          );
        }
      })();

4. **Navigate to the world**

   Visit ``/play/<world_id>`` or use the world selector after login.

Security note
-------------

The play shell is intentionally public HTML. It does **not** include live game
state. All real data and actions must go through authenticated API endpoints.
If you need to restrict the shell itself, you can add session checks to the
``/play`` routes, but most deployments rely on API auth.

Testing and docs build
----------------------

Quick checks for play-shell changes:

.. code-block:: bash

   pytest tests/test_web/test_web_routes.py -v

Build the documentation locally:

.. code-block:: bash

   cd docs
   make html

Local dev + CORS sanity checklist
---------------------------------

* **Same-origin local dev (no CORS needed)**:
  Run the MUD server locally and load the UI from the same host/port.
  Example: ``mud-server run --host 127.0.0.1 --port 7860`` then visit
  ``http://localhost:7860/play``.

* **Different-origin local dev (CORS required)**:
  If the UI is served from a separate dev server (for example Nova Panic at
  ``http://localhost:9000``) and you point it at the **remote** API, the
  **remote** nginx CORS map must allow that origin.
