"""Unit tests for OutputValidator."""

import pytest

from mud_server.translation.validator import OutputValidator


@pytest.fixture
def strict_validator():
    return OutputValidator(strict_mode=True, max_output_chars=280)


@pytest.fixture
def lenient_validator():
    return OutputValidator(strict_mode=False, max_output_chars=280)


class TestEmptyInput:
    def test_empty_string_returns_none(self, strict_validator):
        assert strict_validator.validate("") is None

    def test_whitespace_only_returns_none(self, strict_validator):
        assert strict_validator.validate("   \n  ") is None


class TestPassthroughSentinel:
    def test_passthrough_exact_returns_none(self, strict_validator):
        assert strict_validator.validate("PASSTHROUGH") is None

    def test_passthrough_lowercase_returns_none(self, strict_validator):
        # Sentinel check is case-insensitive via .upper()
        assert strict_validator.validate("passthrough") is None

    def test_passthrough_with_trailing_text_returns_none(self, strict_validator):
        # "PASSTHROUGH: ..." should still match (startswith check)
        assert strict_validator.validate("PASSTHROUGH: cannot translate") is None

    def test_non_passthrough_clean_line_passes(self, strict_validator):
        result = strict_validator.validate("Hand over the ledger now.")
        assert result == "Hand over the ledger now."


class TestMultilineHandling:
    def test_strict_rejects_multiline(self, strict_validator):
        assert strict_validator.validate("First line.\nSecond line.") is None

    def test_lenient_takes_first_line(self, lenient_validator):
        result = lenient_validator.validate("First line.\nSecond line.")
        assert result == "First line."

    def test_lenient_skips_empty_leading_lines(self, lenient_validator):
        result = lenient_validator.validate("\n\nActual dialogue here.")
        assert result == "Actual dialogue here."

    def test_lenient_all_empty_lines_returns_none(self, lenient_validator):
        assert lenient_validator.validate("\n\n\n") is None


class TestForbiddenPatterns:
    """Forbidden patterns are only enforced in strict mode."""

    def test_strict_rejects_emote_asterisks(self, strict_validator):
        assert strict_validator.validate("*waves hand dismissively*") is None

    def test_strict_rejects_stage_direction_brackets(self, strict_validator):
        assert strict_validator.validate("Give me the coin. [She holds out her hand]") is None

    def test_strict_rejects_parenthetical_narration(self, strict_validator):
        assert strict_validator.validate("(Mira looks uncomfortable)") is None

    def test_strict_accepts_fully_double_quoted_line_after_stripping(self, strict_validator):
        # Quote stripping runs before forbidden-pattern check, so a model
        # output like `"Give me the ledger."` is stripped to the bare
        # dialogue and accepted rather than rejected.
        assert strict_validator.validate('"Give me the ledger."') == "Give me the ledger."

    def test_strict_passes_normal_dialogue(self, strict_validator):
        result = strict_validator.validate("Give me the ledger.")
        assert result == "Give me the ledger."

    def test_lenient_passes_forbidden_patterns(self, lenient_validator):
        # Non-strict mode does not check forbidden patterns
        result = lenient_validator.validate("*waves*")
        # After stripping asterisks aren't removed by this validator — patterns
        # are checked, not stripped.  In lenient mode it passes through.
        assert result is not None


class TestQuoteStripping:
    def test_strips_surrounding_double_quotes(self, strict_validator):
        # Quote stripping runs before forbidden-pattern check, so strict mode
        # also strips surrounding double quotes successfully.
        assert strict_validator.validate('"some dialogue"') == "some dialogue"

    def test_strips_surrounding_single_quotes(self, strict_validator):
        # Single quotes are not in the forbidden-pattern list so strict also
        # strips them.
        result = strict_validator.validate("'Got any bread?'")
        assert result == "Got any bread?"

    def test_preserves_internal_quotes(self, strict_validator):
        result = strict_validator.validate("You said 'hello' to me once.")
        assert result == "You said 'hello' to me once."


class TestMaxLengthEnforcement:
    def test_strict_rejects_overlong_output(self):
        validator = OutputValidator(strict_mode=True, max_output_chars=10)
        assert validator.validate("This is definitely longer than ten chars") is None

    def test_lenient_truncates_overlong_output(self):
        validator = OutputValidator(strict_mode=False, max_output_chars=10)
        result = validator.validate("This is definitely longer than ten chars")
        assert result is not None
        assert len(result) <= 10

    def test_exact_length_passes(self):
        validator = OutputValidator(strict_mode=True, max_output_chars=5)
        assert validator.validate("Hello") == "Hello"

    def test_one_over_limit_fails_in_strict(self):
        validator = OutputValidator(strict_mode=True, max_output_chars=5)
        assert validator.validate("Hello!") is None


class TestFinalEmptyCheck:
    def test_quote_stripping_leaving_empty_returns_none(self, strict_validator):
        # A string that is only quotes becomes empty after stripping.
        result = strict_validator.validate("''")
        assert result is None
