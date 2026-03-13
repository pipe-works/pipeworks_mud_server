"""Error contracts for canonical policy services.

This module defines the typed service-layer exception used across policy
subsystems. API route adapters rely on this error shape to preserve stable
status codes and machine-readable contract codes.
"""

from __future__ import annotations


class PolicyServiceError(RuntimeError):
    """Typed policy-service error carrying stable HTTP and contract metadata.

    Attributes:
        status_code: HTTP status code expected by API adapters.
        code: Stable machine-readable error code used by clients/tests.
        detail: Human-readable description for logs, operators, and UI surfaces.
    """

    def __init__(self, *, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail

    def to_response_payload(self) -> dict[str, str]:
        """Return canonical API payload shape for policy errors."""
        return {"detail": self.detail, "code": self.code, "stage": "policy"}
