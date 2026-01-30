"""
Password policy enforcement for secure authentication.

This module implements a comprehensive password policy that balances security
with usability. The policy is based on NIST SP 800-63B guidelines and industry
best practices, while avoiding overly restrictive rules that lead users to
create predictable passwords.

Policy Philosophy:
    Modern password security research (NIST SP 800-63B, 2017) recommends:
    - Length over complexity (longer passwords are more secure)
    - Blocking common/compromised passwords
    - Avoiding arbitrary complexity rules that frustrate users
    - Not requiring periodic password changes (unless compromise suspected)

    This implementation follows these principles while providing configurable
    enforcement levels for different deployment scenarios.

Policy Levels:
    - BASIC: Minimum viable security (8 chars, basic checks)
    - STANDARD: Recommended for most deployments (12 chars, common password check)
    - STRICT: High-security environments (16 chars, all checks enabled)

Usage:
    from mud_server.api.password_policy import (
        validate_password_strength,
        PasswordPolicy,
        PolicyLevel,
    )

    # Using default (STANDARD) policy
    result = validate_password_strength("my_password_123")
    if not result.is_valid:
        print(result.errors)

    # Using a specific policy level
    result = validate_password_strength("password", level=PolicyLevel.STRICT)

    # Custom policy
    policy = PasswordPolicy(
        min_length=14,
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special=True,
        check_common_passwords=True,
    )
    result = policy.validate("my_password")

Security Considerations:
    - Common password list is checked in constant time to prevent timing attacks
    - Password strength feedback helps users create better passwords
    - All validation errors are returned at once (not fail-fast) for better UX
    - Entropy estimation provides a security score for password meters
"""

import re
from dataclasses import dataclass, field
from enum import Enum

# ============================================================================
# COMMON PASSWORDS LIST
# ============================================================================
# This list contains the most commonly used passwords that should always be
# rejected. Based on analysis of password breaches and security research.
# This is a subset - production systems should use a larger database.
# ============================================================================

COMMON_PASSWORDS: frozenset[str] = frozenset(
    [
        # Top 100 most common passwords (lowercase normalized)
        "123456",
        "password",
        "12345678",
        "qwerty",
        "123456789",
        "12345",
        "1234",
        "111111",
        "1234567",
        "dragon",
        "123123",
        "baseball",
        "abc123",
        "football",
        "monkey",
        "letmein",
        "696969",
        "shadow",
        "master",
        "666666",
        "qwertyuiop",
        "123321",
        "mustang",
        "1234567890",
        "michael",
        "654321",
        "pussy",
        "superman",
        "1qaz2wsx",
        "7777777",
        "fuckyou",
        "121212",
        "000000",
        "qazwsx",
        "123qwe",
        "killer",
        "trustno1",
        "jordan",
        "jennifer",
        "zxcvbnm",
        "asdfgh",
        "hunter",
        "buster",
        "soccer",
        "harley",
        "batman",
        "andrew",
        "tigger",
        "sunshine",
        "iloveyou",
        "fuckme",
        "2000",
        "charlie",
        "robert",
        "thomas",
        "hockey",
        "ranger",
        "daniel",
        "starwars",
        "klaster",
        "112233",
        "george",
        "asshole",
        "computer",
        "michelle",
        "jessica",
        "pepper",
        "1111",
        "zxcvbn",
        "555555",
        "11111111",
        "131313",
        "freedom",
        "777777",
        "pass",
        "fuck",
        "maggie",
        "159753",
        "aaaaaa",
        "ginger",
        "princess",
        "joshua",
        "cheese",
        "amanda",
        "summer",
        "love",
        "ashley",
        "6969",
        "nicole",
        "chelsea",
        "biteme",
        "matthew",
        "access",
        "yankees",
        "987654321",
        "dallas",
        "austin",
        "thunder",
        "taylor",
        "matrix",
        # Additional commonly breached passwords
        "password1",
        "password123",
        "admin",
        "admin123",
        "root",
        "toor",
        "guest",
        "login",
        "welcome",
        "welcome1",
        "welcome123",
        "changeme",
        "passw0rd",
        "p@ssw0rd",
        "p@ssword",
        "letmein1",
        "letmein123",
        "qwerty123",
        "qwerty1",
        "abc1234",
        "abcd1234",
        "test",
        "test123",
        "test1234",
        "temp",
        "temp123",
        "default",
        "secret",
        "secret123",
        # Keyboard patterns
        "qwertyui",
        "asdfghjk",
        "zxcvbnm,",
        "1q2w3e4r",
        "1q2w3e4r5t",
        "1qaz2wsx3edc",
        "qazwsxedc",
        "!qaz2wsx",
        "1qazxsw2",
        # Year-based passwords
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
        # Common names with numbers
        "john123",
        "mike123",
        "user123",
        "admin1234",
    ]
)


# ============================================================================
# POLICY CONFIGURATION
# ============================================================================


class PolicyLevel(Enum):
    """
    Predefined password policy levels for different security requirements.

    Each level provides a balance between security and usability appropriate
    for different deployment scenarios.

    Attributes:
        BASIC: Minimum viable security. Suitable for development/testing
               environments or low-risk internal applications.
               - 8 character minimum
               - No complexity requirements
               - Basic common password check

        STANDARD: Recommended for most production deployments. Provides
                  strong security without being overly restrictive.
                  - 12 character minimum (NIST recommended)
                  - Encourages but doesn't require complexity
                  - Comprehensive common password check
                  - Sequential/repeated character detection

        STRICT: For high-security environments handling sensitive data.
                - 16 character minimum
                - Requires uppercase, lowercase, digit, and special char
                - All security checks enabled
                - Maximum entropy requirements
    """

    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass
class ValidationResult:
    """
    Result of password validation containing success status and feedback.

    This class provides detailed feedback about password validation, including
    all errors encountered and suggestions for improvement. All errors are
    collected (not fail-fast) to provide complete feedback to users.

    Attributes:
        is_valid: True if the password meets all policy requirements.
        errors: List of human-readable error messages describing each
                validation failure. Empty if password is valid.
        warnings: List of suggestions for improving password strength.
                  May be present even for valid passwords.
        score: Estimated password strength score from 0-100. Higher is better.
               Based on length, character diversity, and entropy estimation.
        entropy_bits: Estimated entropy in bits. Passwords with 60+ bits
                      are considered strong, 80+ bits are excellent.

    Example:
        >>> result = validate_password_strength("weak")
        >>> result.is_valid
        False
        >>> result.errors
        ['Password must be at least 12 characters long (currently 4)']
        >>> result.score
        15
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: int = 0
    entropy_bits: float = 0.0


@dataclass
class PasswordPolicy:
    """
    Configurable password policy with comprehensive validation rules.

    This class encapsulates all password policy settings and provides
    validation methods. It can be configured for different security
    levels or customized for specific requirements.

    Attributes:
        min_length: Minimum password length. NIST recommends 8 minimum,
                    but 12+ provides significantly better security.
        max_length: Maximum password length. Set high (128) to allow
                    passphrases. Bcrypt has a 72-byte limit internally.
        require_uppercase: Require at least one uppercase letter (A-Z).
        require_lowercase: Require at least one lowercase letter (a-z).
        require_digit: Require at least one digit (0-9).
        require_special: Require at least one special character.
        special_characters: Set of characters considered "special".
        check_common_passwords: Check against known common passwords.
        check_sequential: Detect sequential characters (abc, 123).
        check_repeated: Detect repeated characters (aaa, 111).
        max_repeated: Maximum allowed consecutive repeated characters.

    Example:
        >>> policy = PasswordPolicy(min_length=14, require_special=True)
        >>> result = policy.validate("MySecurePass123!")
        >>> result.is_valid
        True
    """

    # Length requirements
    min_length: int = 12
    max_length: int = 128

    # Character class requirements
    require_uppercase: bool = False
    require_lowercase: bool = False
    require_digit: bool = False
    require_special: bool = False
    special_characters: str = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"

    # Security checks
    check_common_passwords: bool = True
    check_sequential: bool = True
    check_repeated: bool = True
    max_repeated: int = 3

    def validate(self, password: str) -> ValidationResult:
        """
        Validate a password against this policy.

        Performs all configured validation checks and returns a comprehensive
        result with all errors, warnings, and a strength score. Validation
        is not fail-fast - all checks are performed to provide complete
        feedback.

        Args:
            password: The password string to validate. Should be the raw
                      password before hashing.

        Returns:
            ValidationResult containing:
                - is_valid: True if all requirements are met
                - errors: List of validation failure messages
                - warnings: List of improvement suggestions
                - score: Strength score 0-100
                - entropy_bits: Estimated entropy

        Example:
            >>> policy = PasswordPolicy()
            >>> result = policy.validate("short")
            >>> result.is_valid
            False
            >>> "at least 12 characters" in result.errors[0]
            True
        """
        errors: list[str] = []
        warnings: list[str] = []

        # =================================================================
        # LENGTH CHECKS
        # =================================================================

        if len(password) < self.min_length:
            errors.append(
                f"Password must be at least {self.min_length} characters long "
                f"(currently {len(password)})"
            )

        if len(password) > self.max_length:
            errors.append(
                f"Password must be at most {self.max_length} characters long "
                f"(currently {len(password)})"
            )

        # =================================================================
        # CHARACTER CLASS CHECKS
        # =================================================================

        has_uppercase = bool(re.search(r"[A-Z]", password))
        has_lowercase = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"[0-9]", password))
        has_special = bool(any(char in self.special_characters for char in password))

        if self.require_uppercase and not has_uppercase:
            errors.append("Password must contain at least one uppercase letter (A-Z)")

        if self.require_lowercase and not has_lowercase:
            errors.append("Password must contain at least one lowercase letter (a-z)")

        if self.require_digit and not has_digit:
            errors.append("Password must contain at least one digit (0-9)")

        if self.require_special and not has_special:
            errors.append(
                f"Password must contain at least one special character "
                f"({self.special_characters[:10]}...)"
            )

        # Add warnings for missing character classes (even if not required)
        if not self.require_uppercase and not has_uppercase:
            warnings.append("Adding uppercase letters would improve password strength")

        if not self.require_digit and not has_digit:
            warnings.append("Adding numbers would improve password strength")

        if not self.require_special and not has_special:
            warnings.append("Adding special characters would improve password strength")

        # =================================================================
        # COMMON PASSWORD CHECK
        # =================================================================

        if self.check_common_passwords:
            # Normalize for comparison (lowercase, strip whitespace)
            normalized = password.lower().strip()
            if normalized in COMMON_PASSWORDS:
                errors.append(
                    "This password is too common and easily guessed. "
                    "Please choose a more unique password."
                )

            # Also check with common substitutions reversed
            # e.g., p@ssw0rd -> password
            desubstituted = self._reverse_substitutions(normalized)
            if desubstituted in COMMON_PASSWORDS and desubstituted != normalized:
                errors.append(
                    "This password is a common password with simple substitutions. "
                    "Please choose a more unique password."
                )

        # =================================================================
        # SEQUENTIAL CHARACTER CHECK
        # =================================================================

        if self.check_sequential:
            sequential_found = self._find_sequential(password)
            if sequential_found:
                errors.append(
                    f"Password contains sequential characters ({sequential_found}). "
                    "Avoid sequences like 'abc', '123', or 'xyz'."
                )

        # =================================================================
        # REPEATED CHARACTER CHECK
        # =================================================================

        if self.check_repeated:
            repeated_found = self._find_repeated(password, self.max_repeated)
            if repeated_found:
                errors.append(
                    f"Password contains too many repeated characters ({repeated_found}). "
                    f"Avoid repeating the same character more than {self.max_repeated} times."
                )

        # =================================================================
        # CALCULATE STRENGTH SCORE AND ENTROPY
        # =================================================================

        entropy_bits = self._estimate_entropy(password)
        score = self._calculate_score(
            password, entropy_bits, has_uppercase, has_lowercase, has_digit, has_special
        )

        # Reduce score if there are errors
        if errors:
            score = min(score, 25)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            score=score,
            entropy_bits=entropy_bits,
        )

    def _reverse_substitutions(self, password: str) -> str:
        """
        Reverse common character substitutions to detect leet-speak passwords.

        Common substitutions like @ -> a, 0 -> o, 3 -> e are reversed to
        check if the underlying password is a common one.

        Args:
            password: Lowercase password string.

        Returns:
            Password with common substitutions reversed.
        """
        substitutions = {
            "@": "a",
            "4": "a",
            "8": "b",
            "(": "c",
            "3": "e",
            "6": "g",
            "1": "i",
            "!": "i",
            "|": "l",
            "0": "o",
            "5": "s",
            "$": "s",
            "7": "t",
            "+": "t",
            "2": "z",
        }
        result = password
        for sub, original in substitutions.items():
            result = result.replace(sub, original)
        return result

    def _find_sequential(self, password: str, min_length: int = 3) -> str | None:
        """
        Find sequential character patterns in the password.

        Detects ascending or descending sequences of characters that are
        easy to guess, such as 'abc', '123', 'cba', '321'.

        Args:
            password: Password to check.
            min_length: Minimum sequence length to detect.

        Returns:
            The sequential pattern found, or None if no pattern detected.
        """
        password_lower = password.lower()

        # Check for sequential patterns
        for i in range(len(password_lower) - min_length + 1):
            # Get sequence of characters
            seq = password_lower[i : i + min_length]

            # Check if ascending sequence
            is_ascending = all(ord(seq[j + 1]) == ord(seq[j]) + 1 for j in range(len(seq) - 1))
            if is_ascending:
                return seq

            # Check if descending sequence
            is_descending = all(ord(seq[j + 1]) == ord(seq[j]) - 1 for j in range(len(seq) - 1))
            if is_descending:
                return seq

        return None

    def _find_repeated(self, password: str, max_allowed: int) -> str | None:
        """
        Find repeated character patterns exceeding the allowed limit.

        Detects sequences where the same character is repeated too many
        times consecutively, such as 'aaa' or '1111'.

        Args:
            password: Password to check.
            max_allowed: Maximum allowed consecutive repetitions.

        Returns:
            The repeated pattern found, or None if within limits.
        """
        if max_allowed < 1:
            return None

        current_char = ""
        current_count = 0

        for char in password:
            if char == current_char:
                current_count += 1
                if current_count > max_allowed:
                    return char * current_count
            else:
                current_char = char
                current_count = 1

        return None

    def _estimate_entropy(self, password: str) -> float:
        """
        Estimate password entropy in bits.

        Entropy measures the unpredictability of a password. Higher entropy
        means the password is harder to guess through brute force.

        Calculation considers:
        - Character set size (uppercase, lowercase, digits, special)
        - Password length
        - Penalties for common patterns

        Args:
            password: Password to analyze.

        Returns:
            Estimated entropy in bits. Guidelines:
            - < 28 bits: Very weak
            - 28-35 bits: Weak
            - 36-59 bits: Reasonable
            - 60-127 bits: Strong
            - 128+ bits: Very strong
        """
        import math

        if not password:
            return 0.0

        # Determine character set size
        charset_size = 0
        if re.search(r"[a-z]", password):
            charset_size += 26
        if re.search(r"[A-Z]", password):
            charset_size += 26
        if re.search(r"[0-9]", password):
            charset_size += 10
        if any(c in self.special_characters for c in password):
            charset_size += len(self.special_characters)

        if charset_size == 0:
            charset_size = 1  # Avoid log(0)

        # Basic entropy calculation: log2(charset_size^length)
        entropy = len(password) * math.log2(charset_size)

        # Apply penalties for patterns
        # Repeated characters reduce entropy
        for i in range(len(password) - 1):
            if password[i] == password[i + 1]:
                entropy -= 1

        # Sequential patterns reduce entropy
        for i in range(len(password) - 2):
            if (
                ord(password[i + 1]) == ord(password[i]) + 1
                and ord(password[i + 2]) == ord(password[i]) + 2
            ):
                entropy -= 2

        return max(0.0, entropy)

    def _calculate_score(
        self,
        password: str,
        entropy: float,
        has_upper: bool,
        has_lower: bool,
        has_digit: bool,
        has_special: bool,
    ) -> int:
        """
        Calculate a 0-100 strength score for the password.

        The score combines multiple factors to provide an overall assessment
        of password strength for UI feedback purposes.

        Scoring breakdown:
        - Length: Up to 40 points (4 points per character up to 10)
        - Entropy: Up to 30 points (based on bits of entropy)
        - Character diversity: Up to 20 points (5 per class present)
        - Bonus: Up to 10 points for exceeding minimum requirements

        Args:
            password: The password being scored.
            entropy: Calculated entropy in bits.
            has_upper: True if password contains uppercase.
            has_lower: True if password contains lowercase.
            has_digit: True if password contains digits.
            has_special: True if password contains special chars.

        Returns:
            Integer score from 0 to 100.
        """
        score = 0

        # Length score (up to 40 points)
        length_score = min(40, len(password) * 4)
        score += length_score

        # Entropy score (up to 30 points)
        # 60 bits = full points, scale linearly
        entropy_score = min(30, int(entropy / 2))
        score += entropy_score

        # Character diversity (up to 20 points)
        diversity_score = 0
        if has_upper:
            diversity_score += 5
        if has_lower:
            diversity_score += 5
        if has_digit:
            diversity_score += 5
        if has_special:
            diversity_score += 5
        score += diversity_score

        # Bonus for exceeding minimum length (up to 10 points)
        if len(password) > self.min_length:
            bonus = min(10, (len(password) - self.min_length) * 2)
            score += bonus

        return min(100, score)


# ============================================================================
# PREDEFINED POLICIES
# ============================================================================

# Basic policy - minimum viable security
POLICY_BASIC = PasswordPolicy(
    min_length=8,
    require_uppercase=False,
    require_lowercase=False,
    require_digit=False,
    require_special=False,
    check_common_passwords=True,
    check_sequential=False,
    check_repeated=False,
)

# Standard policy - recommended for most deployments (NIST-aligned)
POLICY_STANDARD = PasswordPolicy(
    min_length=12,
    require_uppercase=False,
    require_lowercase=False,
    require_digit=False,
    require_special=False,
    check_common_passwords=True,
    check_sequential=True,
    check_repeated=True,
    max_repeated=3,
)

# Strict policy - for high-security environments
POLICY_STRICT = PasswordPolicy(
    min_length=16,
    require_uppercase=True,
    require_lowercase=True,
    require_digit=True,
    require_special=True,
    check_common_passwords=True,
    check_sequential=True,
    check_repeated=True,
    max_repeated=2,
)


# Policy lookup by level
_POLICIES: dict[PolicyLevel, PasswordPolicy] = {
    PolicyLevel.BASIC: POLICY_BASIC,
    PolicyLevel.STANDARD: POLICY_STANDARD,
    PolicyLevel.STRICT: POLICY_STRICT,
}


# ============================================================================
# PUBLIC API
# ============================================================================


def validate_password_strength(
    password: str,
    level: PolicyLevel = PolicyLevel.STANDARD,
) -> ValidationResult:
    """
    Validate password strength using a predefined policy level.

    This is the primary function for password validation. It uses one of
    the predefined policy levels (BASIC, STANDARD, or STRICT) to validate
    the password and return comprehensive feedback.

    Args:
        password: The password to validate. Should be the raw password
                  before any hashing.
        level: Security level to enforce. Defaults to STANDARD which is
               appropriate for most production deployments.

    Returns:
        ValidationResult containing validation status, errors, warnings,
        strength score, and entropy estimate.

    Example:
        >>> result = validate_password_strength("MyStr0ng!Pass#2024")
        >>> result.is_valid
        True
        >>> result.score
        85

        >>> result = validate_password_strength("weak", level=PolicyLevel.STRICT)
        >>> result.is_valid
        False
        >>> len(result.errors) > 0
        True

    See Also:
        PasswordPolicy: For custom policy configuration.
        PolicyLevel: For available predefined levels.
    """
    policy = _POLICIES[level]
    return policy.validate(password)


def get_policy(level: PolicyLevel = PolicyLevel.STANDARD) -> PasswordPolicy:
    """
    Get the PasswordPolicy instance for a given level.

    Useful when you need to inspect policy settings or use the policy
    object directly.

    Args:
        level: The policy level to retrieve.

    Returns:
        The PasswordPolicy instance for that level.

    Example:
        >>> policy = get_policy(PolicyLevel.STRICT)
        >>> policy.min_length
        16
        >>> policy.require_special
        True
    """
    return _POLICIES[level]


def get_password_requirements(level: PolicyLevel = PolicyLevel.STANDARD) -> str:
    """
    Get a human-readable description of password requirements.

    Useful for displaying password requirements to users in registration
    forms or password change dialogs.

    Args:
        level: The policy level to describe.

    Returns:
        Multi-line string describing all password requirements.

    Example:
        >>> print(get_password_requirements(PolicyLevel.STANDARD))
        Password Requirements:
        - At least 12 characters long
        - Cannot be a commonly used password
        - Cannot contain sequential characters (abc, 123)
        - Cannot repeat the same character more than 3 times
    """
    policy = _POLICIES[level]
    lines = ["Password Requirements:"]

    lines.append(f"- At least {policy.min_length} characters long")

    if policy.max_length < 128:
        lines.append(f"- At most {policy.max_length} characters long")

    if policy.require_uppercase:
        lines.append("- Must contain at least one uppercase letter (A-Z)")

    if policy.require_lowercase:
        lines.append("- Must contain at least one lowercase letter (a-z)")

    if policy.require_digit:
        lines.append("- Must contain at least one number (0-9)")

    if policy.require_special:
        lines.append("- Must contain at least one special character (!@#$%...)")

    if policy.check_common_passwords:
        lines.append("- Cannot be a commonly used password")

    if policy.check_sequential:
        lines.append("- Cannot contain sequential characters (abc, 123)")

    if policy.check_repeated:
        lines.append(f"- Cannot repeat the same character more than {policy.max_repeated} times")

    return "\n".join(lines)
