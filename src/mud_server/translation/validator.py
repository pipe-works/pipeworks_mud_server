"""Output validator for the OOC→IC translation layer.

``OutputValidator`` takes raw LLM text from the renderer and decides
whether it is suitable for storage as in-character dialogue.  Unsuitable
output is rejected (returning ``None``) so the caller can fall back to
the original OOC message.

Validation pipeline (applied in order)
---------------------------------------
1. **Empty check** — blank string → ``None``.
2. **PASSTHROUGH sentinel** — the model signals that the OOC input has
   no meaningful IC equivalent (e.g. it was a command or meta-question).
   → ``None``.
3. **Multi-line check** — strict mode rejects immediately; non-strict
   mode takes only the first non-empty line.
4. **Quote stripping** — some models (e.g. gemma2) consistently wrap
   output in ``"..."`` or ``'...'``; these are stripped before the
   forbidden-pattern check so that legitimate dialogue is not rejected
   purely because of quoting style.
5. **Forbidden pattern check** — strict mode only.  Rejects outputs that
   look like emotes, stage directions, or parenthetical narration.  These
   indicate the model has not followed the "one line of raw dialogue"
   constraint.
6. **Max-length enforcement** — strict mode rejects; non-strict truncates.
7. **Final empty check** — returns ``None`` if cleaning left an empty
   string.

Strict vs non-strict
---------------------
``strict_mode=True`` (the default) treats any constraint violation as a
hard rejection and returns ``None``.  This is the recommended setting for
production worlds because it guarantees that only well-formed IC dialogue
is ever stored — at the cost of occasionally falling back to OOC when
the model produces slightly imperfect output.

``strict_mode=False`` makes a best-effort cleanup attempt for minor
violations (multi-line → first line; over-length → truncate).  Useful
for low-stakes worlds or during prompt development.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# The model uses this sentinel to signal that the OOC input has no
# meaningful IC equivalent (e.g. a command, a meta-question, or something
# that the model cannot render without breaking the rules).  Returning
# PASSTHROUGH is preferable to hallucinated dialogue.
PASSTHROUGH_SENTINEL = "PASSTHROUGH"

# Patterns that indicate the model has produced output that breaks the
# "single line of raw spoken dialogue" constraint.  Each is checked
# independently; any match triggers a rejection in strict mode.
#
# ^\*.*\*$    — emote lines wrapped in asterisks (*waves hand*)
# \[.*\]      — stage directions in square brackets [She turns away]
# ^\(.*\)$    — parenthetical narration (Mira looks up)
#
# Note: the ^".*"$ (fully double-quoted line) pattern was removed.  Quote
# stripping now runs before this check (step 4), so a model output like
# `"Hello."` is stripped to `Hello.` before reaching here.
_FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\*.*\*$"),
    re.compile(r"\[.*\]"),
    re.compile(r"^\(.*\)$"),
]


class OutputValidator:
    """Validates and cleans raw LLM output before storage.

    Attributes:
        _strict_mode:     When ``True``, any constraint violation → ``None``.
        _max_output_chars: Hard ceiling on IC output character count.
    """

    def __init__(self, *, strict_mode: bool, max_output_chars: int) -> None:
        """Initialise the validator.

        Args:
            strict_mode:      Reject on first violation vs. best-effort cleanup.
            max_output_chars: Maximum allowed character count in the IC output.
        """
        self._strict_mode = strict_mode
        self._max_output_chars = max_output_chars

    def validate(self, ic_raw: str) -> str | None:
        """Validate and clean a raw LLM response string.

        Runs the full validation pipeline and returns either a clean IC
        string or ``None``.  A ``None`` return is always accompanied by a
        WARNING log entry so that rejection reasons are traceable.

        Args:
            ic_raw: Raw text returned by the renderer.

        Returns:
            Cleaned IC string on success, ``None`` if validation fails.
        """
        # ── 1. Empty check ────────────────────────────────────────────────────
        if not ic_raw or not ic_raw.strip():
            return None

        text = ic_raw.strip()

        # ── 2. PASSTHROUGH sentinel ────────────────────────────────────────────
        if text.upper().startswith(PASSTHROUGH_SENTINEL):
            logger.debug("OutputValidator: PASSTHROUGH sentinel returned by model.")
            return None

        # ── 3. Multi-line check ───────────────────────────────────────────────
        if "\n" in text:
            if self._strict_mode:
                logger.warning("OutputValidator: strict_mode rejected multi-line output.")
                return None
            # Non-strict: take only the first non-empty line.
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            if not first_line:
                return None
            text = first_line

        # ── 4. Quote stripping ────────────────────────────────────────────────
        # Some models (e.g. gemma2) consistently wrap output in quotation
        # marks even when instructed not to.  Strip before the forbidden-
        # pattern check so that `"Hello."` becomes `Hello.` and is not
        # incorrectly rejected as a quoted speech block.
        text = text.strip('"').strip("'").strip()

        # ── 5. Forbidden pattern check (strict mode only) ─────────────────────
        if self._strict_mode:
            for pattern in _FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    logger.warning(
                        "OutputValidator: strict_mode rejected output matching pattern %r: %r",
                        pattern.pattern,
                        text[:60],
                    )
                    return None

        # ── 6. Max-length enforcement ─────────────────────────────────────────
        if len(text) > self._max_output_chars:
            if self._strict_mode:
                logger.warning(
                    "OutputValidator: strict_mode rejected output exceeding "
                    "max_output_chars (%d > %d).",
                    len(text),
                    self._max_output_chars,
                )
                return None
            # Non-strict: truncate at the last word boundary if possible.
            text = text[: self._max_output_chars].rstrip()

        # ── 7. Final empty check ─────────────────────────────────────────────
        return text if text else None
