"""Regression tests for the API model import surface."""

from mud_server.api.models import (
    CommandRequest,
    DatabaseWorldStatusResponse,
    LabPolicyBundleDraftPayload,
    LabPromptDraftCreateRequest,
    LabTranslateResponse,
    LabWorldConfig,
    LoginResponse,
    RegisterRequest,
    UserManagementRequest,
)
from mud_server.api.models_admin import (
    DatabaseWorldStatusResponse as DatabaseWorldStatusResponseModule,
)
from mud_server.api.models_admin import UserManagementRequest as UserManagementRequestModule
from mud_server.api.models_auth_game import CommandRequest as CommandRequestModule
from mud_server.api.models_auth_game import LoginResponse as LoginResponseModule
from mud_server.api.models_auth_game import RegisterRequest as RegisterRequestModule
from mud_server.api.models_lab import (
    LabPolicyBundleDraftPayload as LabPolicyBundleDraftPayloadModule,
)
from mud_server.api.models_lab import (
    LabPromptDraftCreateRequest as LabPromptDraftCreateRequestModule,
)
from mud_server.api.models_lab import LabTranslateResponse as LabTranslateResponseModule
from mud_server.api.models_lab import LabWorldConfig as LabWorldConfigModule


def test_lab_models_remain_importable_from_api_models():
    """Compatibility re-exports should preserve the old import surface."""

    assert LabWorldConfig is LabWorldConfigModule
    assert LabPromptDraftCreateRequest is LabPromptDraftCreateRequestModule
    assert LabPolicyBundleDraftPayload is LabPolicyBundleDraftPayloadModule
    assert LabTranslateResponse is LabTranslateResponseModule
    assert UserManagementRequest is UserManagementRequestModule
    assert DatabaseWorldStatusResponse is DatabaseWorldStatusResponseModule
    assert RegisterRequest is RegisterRequestModule
    assert CommandRequest is CommandRequestModule
    assert LoginResponse is LoginResponseModule


def test_login_response_list_defaults_are_not_shared():
    """List defaults should be created per instance, not shared globally."""

    first = LoginResponse(success=True, message="ok")
    second = LoginResponse(success=True, message="ok")

    first.characters.append({"id": 1})
    first.available_worlds.append({"world_id": "pipeworks_web"})

    assert second.characters == []
    assert second.available_worlds == []
