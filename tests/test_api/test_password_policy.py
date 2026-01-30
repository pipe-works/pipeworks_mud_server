"""
Tests for password policy enforcement.

This module provides comprehensive tests for the password_policy module,
covering all validation rules, policy levels, and edge cases.

Test Categories:
    1. Basic Validation - Length requirements, None/empty handling
    2. Character Class Requirements - Uppercase, lowercase, digits, special
    3. Common Password Detection - Known weak passwords, leet-speak variants
    4. Sequential Character Detection - abc, 123, xyz patterns
    5. Repeated Character Detection - aaa, 111 patterns
    6. Policy Levels - BASIC, STANDARD, STRICT configurations
    7. Scoring and Entropy - Strength score calculation
    8. Integration Tests - Full validation flow
"""

from mud_server.api.password_policy import (
    COMMON_PASSWORDS,
    POLICY_BASIC,
    POLICY_STANDARD,
    POLICY_STRICT,
    PasswordPolicy,
    PolicyLevel,
    ValidationResult,
    get_password_requirements,
    get_policy,
    validate_password_strength,
)

# ============================================================================
# Basic Validation Tests
# ============================================================================


class TestBasicValidation:
    """Tests for basic password validation (length, None/empty)."""

    def test_empty_password_fails(self):
        """Empty string should fail validation."""
        result = validate_password_strength("")
        assert not result.is_valid
        assert any("12 characters" in e for e in result.errors)

    def test_none_like_empty_string(self):
        """Very short passwords should fail."""
        result = validate_password_strength("a")
        assert not result.is_valid

    def test_password_too_short_standard(self):
        """Password below STANDARD minimum (12) should fail."""
        result = validate_password_strength("short123!")
        assert not result.is_valid
        assert any("12 characters" in e for e in result.errors)

    def test_password_too_short_basic(self):
        """Password below BASIC minimum (8) should fail."""
        result = validate_password_strength("short", level=PolicyLevel.BASIC)
        assert not result.is_valid
        assert any("8 characters" in e for e in result.errors)

    def test_password_too_short_strict(self):
        """Password below STRICT minimum (16) should fail."""
        result = validate_password_strength("ShortPass123!", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("16 characters" in e for e in result.errors)

    def test_password_meets_minimum_length(self):
        """Password at exactly minimum length should pass (if not common)."""
        # 12 characters, not common, no sequences
        result = validate_password_strength("MyUnique#Pwd")
        assert result.is_valid

    def test_password_exceeds_maximum_length(self):
        """Password exceeding max length should fail."""
        policy = PasswordPolicy(max_length=20)
        result = policy.validate("a" * 25)
        assert not result.is_valid
        assert any("at most 20" in e for e in result.errors)


# ============================================================================
# Character Class Requirement Tests
# ============================================================================


class TestCharacterClassRequirements:
    """Tests for character class requirements (uppercase, lowercase, etc.)."""

    def test_strict_requires_uppercase(self):
        """STRICT policy requires uppercase letters."""
        # Has lowercase, digit, special but no uppercase
        result = validate_password_strength("nouppercase123!@#$", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("uppercase" in e.lower() for e in result.errors)

    def test_strict_requires_lowercase(self):
        """STRICT policy requires lowercase letters."""
        # Has uppercase, digit, special but no lowercase
        result = validate_password_strength("NOLOWERCASE123!@#$", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("lowercase" in e.lower() for e in result.errors)

    def test_strict_requires_digit(self):
        """STRICT policy requires digits."""
        # Has uppercase, lowercase, special but no digit
        result = validate_password_strength("NoDigitsHere!@#$%", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("digit" in e.lower() for e in result.errors)

    def test_strict_requires_special(self):
        """STRICT policy requires special characters."""
        # Has uppercase, lowercase, digit but no special
        result = validate_password_strength("NoSpecialChars123", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("special" in e.lower() for e in result.errors)

    def test_strict_all_requirements_met(self):
        """Password meeting all STRICT requirements should pass."""
        result = validate_password_strength("MyStr0ng!Pass#2024", level=PolicyLevel.STRICT)
        assert result.is_valid

    def test_standard_no_character_requirements(self):
        """STANDARD policy doesn't require specific character classes."""
        # All lowercase, no digits, no special - but long enough and not common
        result = validate_password_strength("uniquelongpassword")
        assert result.is_valid

    def test_warnings_for_missing_classes(self):
        """Should provide warnings for missing character classes."""
        result = validate_password_strength("alllowercase123")
        # Should have warnings about uppercase and special characters
        assert len(result.warnings) > 0


# ============================================================================
# Common Password Detection Tests
# ============================================================================


class TestCommonPasswordDetection:
    """Tests for common/compromised password detection."""

    def test_common_password_rejected(self):
        """Common passwords should be rejected."""
        result = validate_password_strength("password123456")
        # This is long enough but "password" is a common base
        # Actually "password123456" isn't in the list but let's test one that is
        policy = PasswordPolicy(min_length=6, check_common_passwords=True)
        result = policy.validate("password")
        assert not result.is_valid
        assert any("common" in e.lower() for e in result.errors)

    def test_password123_rejected(self):
        """password123 should be rejected as common."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=True)
        result = policy.validate("password123")  # Intentionally weak for testing
        assert not result.is_valid

    def test_admin123_rejected(self):
        """admin123 should be rejected as common."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=True)
        result = policy.validate("admin123")
        assert not result.is_valid

    def test_qwerty_rejected(self):
        """qwerty should be rejected as common."""
        policy = PasswordPolicy(min_length=6, check_common_passwords=True)
        result = policy.validate("qwerty")
        assert not result.is_valid

    def test_leetspeak_variant_rejected(self):
        """Leet-speak variants of common passwords should be rejected."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=True)
        # p@ssw0rd should be detected as "password" variant
        result = policy.validate("p@ssw0rd")
        assert not result.is_valid
        assert any("substitution" in e.lower() for e in result.errors)

    def test_unique_password_accepted(self):
        """Unique passwords not in common list should pass."""
        result = validate_password_strength("XyloPhone#Zebra42")
        assert result.is_valid

    def test_common_passwords_list_exists(self):
        """Common passwords list should contain expected entries."""
        assert "password" in COMMON_PASSWORDS
        assert "123456" in COMMON_PASSWORDS
        assert "qwerty" in COMMON_PASSWORDS
        assert "admin" in COMMON_PASSWORDS


# ============================================================================
# Sequential Character Detection Tests
# ============================================================================


class TestSequentialCharacterDetection:
    """Tests for sequential character pattern detection."""

    def test_ascending_letters_rejected(self):
        """Ascending letter sequences (abc) should be rejected."""
        result = validate_password_strength("mypasswordabcdef")
        assert not result.is_valid
        assert any("sequential" in e.lower() for e in result.errors)

    def test_descending_letters_rejected(self):
        """Descending letter sequences (cba) should be rejected."""
        result = validate_password_strength("mypasswordcba123")
        assert not result.is_valid
        assert any("sequential" in e.lower() for e in result.errors)

    def test_ascending_numbers_rejected(self):
        """Ascending number sequences (123) should be rejected."""
        result = validate_password_strength("mypassword123more")
        assert not result.is_valid
        assert any("sequential" in e.lower() for e in result.errors)

    def test_descending_numbers_rejected(self):
        """Descending number sequences (321) should be rejected."""
        result = validate_password_strength("mypassword321more")
        assert not result.is_valid
        assert any("sequential" in e.lower() for e in result.errors)

    def test_non_sequential_accepted(self):
        """Non-sequential patterns should be accepted."""
        result = validate_password_strength("MyUn1que#Pass!")
        assert result.is_valid

    def test_sequential_check_disabled(self):
        """Sequential check can be disabled."""
        policy = PasswordPolicy(
            min_length=12,
            check_common_passwords=False,
            check_sequential=False,
            check_repeated=False,
        )
        result = policy.validate("passwordabc123")
        assert result.is_valid


# ============================================================================
# Repeated Character Detection Tests
# ============================================================================


class TestRepeatedCharacterDetection:
    """Tests for repeated character pattern detection."""

    def test_repeated_letters_rejected(self):
        """Repeated letters (aaaa) should be rejected."""
        result = validate_password_strength("mypasswordaaaa")
        assert not result.is_valid
        assert any("repeated" in e.lower() for e in result.errors)

    def test_repeated_numbers_rejected(self):
        """Repeated numbers (1111) should be rejected."""
        result = validate_password_strength("mypassword1111")
        assert not result.is_valid
        assert any("repeated" in e.lower() for e in result.errors)

    def test_three_repeated_allowed_by_default(self):
        """Three repeated characters should be allowed (max_repeated=3)."""
        result = validate_password_strength("mypassword111ok")
        # 111 is exactly 3, which should be allowed
        # But wait, we need to check if the password passes other checks too
        policy = PasswordPolicy(
            min_length=12,
            check_common_passwords=False,
            check_sequential=False,
            check_repeated=True,
            max_repeated=3,
        )
        result = policy.validate("mypassword111")
        assert result.is_valid

    def test_four_repeated_rejected_by_default(self):
        """Four repeated characters should be rejected (max_repeated=3)."""
        policy = PasswordPolicy(
            min_length=12,
            check_common_passwords=False,
            check_sequential=False,
            check_repeated=True,
            max_repeated=3,
        )
        result = policy.validate("mypassword1111")
        assert not result.is_valid

    def test_strict_allows_only_two_repeated(self):
        """STRICT policy only allows 2 repeated characters."""
        result = validate_password_strength("MyStr0ng!Passs#", level=PolicyLevel.STRICT)
        assert not result.is_valid
        assert any("repeated" in e.lower() for e in result.errors)


# ============================================================================
# Policy Level Tests
# ============================================================================


class TestPolicyLevels:
    """Tests for predefined policy levels."""

    def test_basic_policy_settings(self):
        """BASIC policy should have minimal requirements."""
        assert POLICY_BASIC.min_length == 8
        assert not POLICY_BASIC.require_uppercase
        assert not POLICY_BASIC.require_lowercase
        assert not POLICY_BASIC.require_digit
        assert not POLICY_BASIC.require_special
        assert POLICY_BASIC.check_common_passwords
        assert not POLICY_BASIC.check_sequential
        assert not POLICY_BASIC.check_repeated

    def test_standard_policy_settings(self):
        """STANDARD policy should have balanced requirements."""
        assert POLICY_STANDARD.min_length == 12
        assert not POLICY_STANDARD.require_uppercase
        assert not POLICY_STANDARD.require_lowercase
        assert not POLICY_STANDARD.require_digit
        assert not POLICY_STANDARD.require_special
        assert POLICY_STANDARD.check_common_passwords
        assert POLICY_STANDARD.check_sequential
        assert POLICY_STANDARD.check_repeated
        assert POLICY_STANDARD.max_repeated == 3

    def test_strict_policy_settings(self):
        """STRICT policy should have maximum requirements."""
        assert POLICY_STRICT.min_length == 16
        assert POLICY_STRICT.require_uppercase
        assert POLICY_STRICT.require_lowercase
        assert POLICY_STRICT.require_digit
        assert POLICY_STRICT.require_special
        assert POLICY_STRICT.check_common_passwords
        assert POLICY_STRICT.check_sequential
        assert POLICY_STRICT.check_repeated
        assert POLICY_STRICT.max_repeated == 2

    def test_get_policy_returns_correct_instance(self):
        """get_policy() should return correct policy for each level."""
        assert get_policy(PolicyLevel.BASIC) is POLICY_BASIC
        assert get_policy(PolicyLevel.STANDARD) is POLICY_STANDARD
        assert get_policy(PolicyLevel.STRICT) is POLICY_STRICT


# ============================================================================
# Scoring and Entropy Tests
# ============================================================================


class TestScoringAndEntropy:
    """Tests for password strength scoring and entropy calculation."""

    def test_weak_password_low_score(self):
        """Weak passwords should have low scores."""
        policy = PasswordPolicy(min_length=4, check_common_passwords=False, check_sequential=False)
        result = policy.validate("weak")
        assert result.score <= 30

    def test_strong_password_high_score(self):
        """Strong passwords should have high scores."""
        result = validate_password_strength("MyStr0ng!Pass#2024")
        assert result.score >= 70

    def test_longer_passwords_higher_score(self):
        """Longer passwords should score higher than shorter ones."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False, check_sequential=False)
        short_result = policy.validate("Xyzq1234")
        long_result = policy.validate("Xyzq1234Mnop5678")
        assert long_result.score > short_result.score

    def test_diverse_characters_higher_score(self):
        """Passwords with diverse character classes should score higher."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False, check_sequential=False)
        simple_result = policy.validate("abcdefghij")
        diverse_result = policy.validate("Abcd1234!@")
        assert diverse_result.score > simple_result.score

    def test_entropy_calculated(self):
        """Entropy should be calculated for passwords."""
        result = validate_password_strength("MyStr0ng!Pass#2024")
        assert result.entropy_bits > 0

    def test_longer_passwords_higher_entropy(self):
        """Longer passwords should have higher entropy."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False)
        short_result = policy.validate("Abcd1234")
        long_result = policy.validate("Abcd1234Efgh5678")
        assert long_result.entropy_bits > short_result.entropy_bits

    def test_invalid_password_low_score(self):
        """Invalid passwords should have capped low scores."""
        result = validate_password_strength("password")
        assert not result.is_valid
        assert result.score <= 25


# ============================================================================
# Validation Result Tests
# ============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result_has_no_errors(self):
        """Valid results should have empty errors list."""
        result = validate_password_strength("MyUn1que#Password!")
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_result_has_errors(self):
        """Invalid results should have non-empty errors list."""
        result = validate_password_strength("weak")
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_warnings_present_for_improvements(self):
        """Warnings should suggest improvements."""
        # Password that's valid but could be improved
        policy = PasswordPolicy(
            min_length=8,
            require_uppercase=False,
            require_digit=False,
            require_special=False,
            check_common_passwords=False,
            check_sequential=False,
        )
        result = policy.validate("onlylowercase")
        # Should have warnings about adding uppercase, digits, special
        assert len(result.warnings) > 0


# ============================================================================
# Requirements Text Tests
# ============================================================================


class TestRequirementsText:
    """Tests for human-readable requirements text."""

    def test_standard_requirements_text(self):
        """STANDARD requirements should include key information."""
        text = get_password_requirements(PolicyLevel.STANDARD)
        assert "12 characters" in text
        assert "common" in text.lower()
        assert "sequential" in text.lower()
        assert "repeat" in text.lower()

    def test_strict_requirements_text(self):
        """STRICT requirements should include character class requirements."""
        text = get_password_requirements(PolicyLevel.STRICT)
        assert "16 characters" in text
        assert "uppercase" in text.lower()
        assert "lowercase" in text.lower()
        assert "number" in text.lower() or "digit" in text.lower()
        assert "special" in text.lower()

    def test_basic_requirements_text(self):
        """BASIC requirements should be minimal."""
        text = get_password_requirements(PolicyLevel.BASIC)
        assert "8 characters" in text


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unicode_characters_handled(self):
        """Unicode characters should not crash validation."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False)
        result = policy.validate("пароль123!")  # Russian "password"
        # Should not raise an exception
        assert isinstance(result, ValidationResult)

    def test_very_long_password(self):
        """Very long passwords should be handled correctly."""
        long_password = "A" * 100 + "1!"
        policy = PasswordPolicy(min_length=8, check_common_passwords=False)
        result = policy.validate(long_password)
        # Very long repeated chars would fail repeated check
        assert isinstance(result, ValidationResult)

    def test_whitespace_password(self):
        """Passwords with whitespace should be handled."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False)
        result = policy.validate("has space here")
        assert isinstance(result, ValidationResult)

    def test_special_characters_only(self):
        """Password with only special characters should be handled."""
        policy = PasswordPolicy(min_length=8, check_common_passwords=False, check_sequential=False)
        result = policy.validate("!@#$%^&*()")
        assert isinstance(result, ValidationResult)

    def test_numbers_only(self):
        """Password with only numbers should be handled."""
        policy = PasswordPolicy(
            min_length=8,
            check_common_passwords=False,
            check_sequential=False,
            check_repeated=False,
        )
        result = policy.validate("98765432")  # Not sequential (descending by 1)
        assert isinstance(result, ValidationResult)


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full validation flow."""

    def test_full_validation_flow_valid(self):
        """Complete validation flow for valid password."""
        password = "MySecure#Pass2024!"
        result = validate_password_strength(password, level=PolicyLevel.STANDARD)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.score >= 60
        assert result.entropy_bits > 50

    def test_full_validation_flow_invalid(self):
        """Complete validation flow for invalid password."""
        password = "password123"  # Intentionally weak for testing
        result = validate_password_strength(password, level=PolicyLevel.STANDARD)

        assert not result.is_valid
        assert len(result.errors) > 0
        assert result.score <= 25

    def test_multiple_errors_collected(self):
        """Multiple validation errors should all be collected."""
        # Short, common, has sequential
        password = "abc123"
        policy = PasswordPolicy(
            min_length=12,
            check_common_passwords=True,
            check_sequential=True,
        )
        result = policy.validate(password)

        assert not result.is_valid
        # Should have multiple errors
        assert len(result.errors) >= 2

    def test_custom_policy_configuration(self):
        """Custom policy should work correctly."""
        policy = PasswordPolicy(
            min_length=10,
            max_length=50,
            require_uppercase=True,
            require_digit=True,
            check_common_passwords=False,
            check_sequential=False,
            check_repeated=False,
        )

        # Valid password for this policy
        result = policy.validate("MyPass1234")
        assert result.is_valid

        # Missing uppercase
        result = policy.validate("mypass1234")
        assert not result.is_valid

        # Missing digit
        result = policy.validate("MyPassword")
        assert not result.is_valid
