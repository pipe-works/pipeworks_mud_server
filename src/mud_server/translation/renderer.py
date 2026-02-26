"""Ollama HTTP renderer for the OOC→IC translation layer.

``OllamaRenderer`` is a thin, synchronous wrapper around the Ollama
``/api/chat`` endpoint.  It is the only place in the translation layer
that makes a network call.

Sync vs async
-------------
The renderer uses the synchronous ``requests`` library (already a pinned
dependency at ``requests==2.32.5``).  The ``GameEngine`` is fully
synchronous, and FastAPI runs sync endpoint handlers inside a thread-pool
executor, so a blocking HTTP call here does not stall the event loop.

When the engine is eventually asyncified the upgrade path is:
1. Replace ``requests.post`` with ``await httpx.AsyncClient().post``.
2. Mark ``render`` as ``async def``.
3. Mark ``OOCToICTranslationService.translate`` as ``async def``.
4. Propagate ``await`` up through ``engine.chat/yell/whisper``.
``httpx`` is already in the project dependencies (``>=0.28.1``) so no
new dep is required at that point.

Deterministic mode
------------------
When ``set_deterministic(seed_int)`` is called (by the service, after
deriving a seed from the IPC hash), temperature is clamped to 0.0 and
the seed is forwarded to Ollama's ``options.seed`` field.

IPC hash sourcing (FUTURE — axis engine integration)
----------------------------------------------------
``set_deterministic`` will be called from ``OOCToICTranslationService``
once the axis engine passes a concrete ``ipc_hash`` through
``service.translate(..., ipc_hash=ipc_hash)``.  The service converts the
first 16 hex characters of the hash to an integer::

    seed_int = int(ipc_hash[:16], 16)

Until then ``set_deterministic`` is never called and the renderer uses
the configured temperature from ``TranslationLayerConfig``.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

# Temperature used when deterministic mode is not active.
_DEFAULT_TEMPERATURE = 0.7

# Conservative token ceiling for a single line of dialogue.
_DEFAULT_NUM_PREDICT = 128


class OllamaRenderer:
    """Synchronous renderer that calls the Ollama ``/api/chat`` endpoint.

    One ``OllamaRenderer`` instance is created per ``OOCToICTranslationService``
    and reused across all translation calls.  The renderer is *stateful* in
    one way only: deterministic mode can be armed via ``set_deterministic``,
    which persists for the lifetime of the object.  This is by design — the
    axis engine arms it at the start of a deterministic turn and the service
    then calls ``render`` for each character in that turn.

    Attributes:
        _api_endpoint:  Full ``/api/chat`` URL.
        _model:         Ollama model tag (e.g. ``"gemma2:2b"``).
        _timeout:       HTTP request timeout in seconds.
        _temperature:   Sampling temperature; clamped to 0.0 in deterministic
                        mode.
        _seed:          Integer seed forwarded to Ollama when deterministic;
                        ``None`` when non-deterministic.
    """

    def __init__(
        self,
        *,
        api_endpoint: str,
        model: str,
        timeout_seconds: float,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> None:
        """Initialise the renderer.

        Args:
            api_endpoint:    Full Ollama ``/api/chat`` URL.
            model:           Ollama model tag.
            timeout_seconds: HTTP request timeout.
            temperature:     Default sampling temperature.
        """
        self._api_endpoint = api_endpoint
        self._model = model
        self._timeout = timeout_seconds
        self._temperature: float = temperature
        self._seed: int | None = None

    # ── Deterministic mode ────────────────────────────────────────────────────

    def set_deterministic(self, seed_int: int) -> None:
        """Arm deterministic mode for subsequent ``render`` calls.

        Clamps temperature to 0.0 and stores the seed so that identical
        inputs produce identical outputs across runs.  This is called by
        ``OOCToICTranslationService`` when a non-``None`` ``ipc_hash`` is
        provided and ``config.deterministic`` is ``True``.

        The seed is derived from the IPC hash *by the service*, not here,
        to keep hashing logic out of the renderer.

        Args:
            seed_int: Integer seed forwarded to Ollama's ``options.seed``.
        """
        self._temperature = 0.0
        self._seed = seed_int
        logger.debug("OllamaRenderer: deterministic mode armed (seed=%d)", seed_int)

    # ── Primary render method ─────────────────────────────────────────────────

    def render(self, system_prompt: str, user_message: str) -> str | None:
        """Call Ollama and return the raw response content.

        Builds the Ollama request payload, executes a synchronous POST, and
        returns the ``message.content`` string from the JSON response.

        Returns ``None`` on any network-level failure (timeout, connection
        error, non-2xx status).  Content-level validation (PASSTHROUGH
        sentinel, multi-line output, etc.) is handled by ``OutputValidator``.

        Args:
            system_prompt: The fully-rendered system prompt (with character
                           profile injected).
            user_message:  The original OOC message (used as the ``user``
                           turn so the model sees both context and input).

        Returns:
            Raw LLM output string on success, ``None`` on failure.
        """
        payload = self._build_payload(system_prompt, user_message)

        try:
            response = requests.post(
                self._api_endpoint,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip() or None

        except requests.exceptions.Timeout:
            logger.warning(
                "OllamaRenderer: request timed out after %.1fs (endpoint=%s)",
                self._timeout,
                self._api_endpoint,
            )
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(
                "OllamaRenderer: cannot connect to Ollama at %s",
                self._api_endpoint,
            )
            return None
        except requests.exceptions.RequestException as exc:
            logger.error("OllamaRenderer: request failed: %s", exc)
            return None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_payload(self, system_prompt: str, user_message: str) -> dict:
        """Construct the Ollama ``/api/chat`` request payload.

        ``stream`` is always ``False`` — we want the full response in a
        single JSON object rather than a server-sent-event stream.

        Args:
            system_prompt: Rendered system prompt text.
            user_message:  OOC message text.

        Returns:
            Dict ready to be serialised as the POST body.
        """
        options: dict = {
            "temperature": self._temperature,
            "num_predict": _DEFAULT_NUM_PREDICT,
        }
        if self._seed is not None:
            options["seed"] = self._seed

        return {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "options": options,
        }
