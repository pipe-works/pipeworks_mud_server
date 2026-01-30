"""
Shared test constants.

This module provides constants that are used across multiple test files.
It ensures consistency in test data and makes it easy to update values
that must meet policy requirements (like password complexity).
"""

# Standard test password that meets the STANDARD password policy requirements:
# - At least 12 characters (STANDARD requires 12)
# - Not a common password
# - No sequential characters (abc, 123, xyz)
# - No repeated characters (aaa)
# - Mix of character types for good entropy
TEST_PASSWORD = "SecureTest#9x7"
