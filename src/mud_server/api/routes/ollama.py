"""Ollama admin endpoints."""

from fastapi import APIRouter

from mud_server.api.auth import validate_session_with_permission
from mud_server.api.models import (
    ClearOllamaContextRequest,
    ClearOllamaContextResponse,
    OllamaCommandRequest,
    OllamaCommandResponse,
)
from mud_server.api.permissions import Permission
from mud_server.core.engine import GameEngine


def router(_engine: GameEngine) -> APIRouter:
    """Build the Ollama router (engine unused, kept for signature symmetry)."""
    api = APIRouter()

    ollama_conversation_history: dict[str, list[dict[str, str]]] = {}

    @api.post("/admin/ollama/command", response_model=OllamaCommandResponse)
    async def execute_ollama_command(request: OllamaCommandRequest):
        """Execute an Ollama command (Admin and Superuser only)."""
        _, _username, _role = validate_session_with_permission(
            request.session_id, Permission.VIEW_LOGS
        )

        import json

        try:
            server_url = request.server_url.strip()
            command = request.command.strip()

            if not server_url or not command:
                return OllamaCommandResponse(
                    success=False, output="Server URL and command are required"
                )

            import requests as req

            cmd_parts = command.split()
            cmd_verb = cmd_parts[0].lower()

            if cmd_verb == "list" or cmd_verb == "ls":
                response = req.get(f"{server_url}/api/tags", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if models:
                        output = "Available models:\n"
                        for model in models:
                            name = model.get("name", "unknown")
                            size = model.get("size", 0)
                            modified = model.get("modified_at", "")
                            output += f"  - {name} (size: {size}, modified: {modified})\n"
                    else:
                        output = "No models found."
                    return OllamaCommandResponse(success=True, output=output)
                return OllamaCommandResponse(
                    success=False,
                    output=f"Failed to list models: HTTP {response.status_code}",
                )

            if cmd_verb == "ps":
                response = req.get(f"{server_url}/api/ps", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if models:
                        output = "Running models:\n"
                        for model in models:
                            name = model.get("name", "unknown")
                            output += f"  - {name}\n"
                    else:
                        output = "No models currently running."
                    return OllamaCommandResponse(success=True, output=output)
                return OllamaCommandResponse(
                    success=False,
                    output=f"Failed to show running models: HTTP {response.status_code}",
                )

            if cmd_verb == "pull":
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(success=False, output="Usage: pull <model_name>")
                model_name = cmd_parts[1]

                response = req.post(
                    f"{server_url}/api/pull",
                    json={"name": model_name},
                    stream=True,
                    timeout=300,
                )

                if response.status_code == 200:
                    output = f"Pulling model '{model_name}'...\n"
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            status = data.get("status", "")
                            output += f"{status}\n"
                            if data.get("error"):
                                return OllamaCommandResponse(
                                    success=False, output=f"Error: {data.get('error')}"
                                )
                    return OllamaCommandResponse(success=True, output=output)
                return OllamaCommandResponse(
                    success=False, output=f"Failed to pull model: HTTP {response.status_code}"
                )

            if cmd_verb == "run":
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(
                        success=False, output="Usage: run <model_name> [prompt]"
                    )

                model_name = cmd_parts[1]
                prompt = " ".join(cmd_parts[2:]) if len(cmd_parts) > 2 else "Hello"

                session_id = request.session_id
                if session_id not in ollama_conversation_history:
                    ollama_conversation_history[session_id] = []

                ollama_conversation_history[session_id].append({"role": "user", "content": prompt})

                response = req.post(
                    f"{server_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": ollama_conversation_history[session_id],
                        "stream": False,
                    },
                    timeout=120,
                )

                if response.status_code == 200:
                    data = response.json()
                    assistant_message = data.get("message", {})
                    generated_text = assistant_message.get("content", "")

                    ollama_conversation_history[session_id].append(
                        {"role": "assistant", "content": generated_text}
                    )

                    msg_count = len(ollama_conversation_history[session_id])
                    output = f"Model: {model_name} (Context: {msg_count} messages)\n"
                    output += f"You: {prompt}\n\nResponse:\n{generated_text}"
                    return OllamaCommandResponse(success=True, output=output)

                ollama_conversation_history[session_id].pop()
                error_detail = response.text
                return OllamaCommandResponse(
                    success=False,
                    output=f"Failed to run model: HTTP {response.status_code}\n{error_detail}",
                )

            if cmd_verb == "show":
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(success=False, output="Usage: show <model_name>")
                model_name = cmd_parts[1]

                response = req.post(
                    f"{server_url}/api/show",
                    json={"name": model_name},
                    timeout=10,
                )

                if response.status_code == 200:
                    data = response.json()
                    output = f"Model: {model_name}\n"
                    output += f"Modelfile:\n{data.get('modelfile', 'N/A')}\n"
                    output += f"Parameters:\n{data.get('parameters', 'N/A')}\n"
                    return OllamaCommandResponse(success=True, output=output)
                return OllamaCommandResponse(
                    success=False,
                    output=f"Failed to show model info: HTTP {response.status_code}",
                )

            return OllamaCommandResponse(
                success=False,
                output=(
                    f"Unknown command: {cmd_verb}\nSupported commands: list, ps, pull, run, show"
                ),
            )

        except req.exceptions.ConnectionError:
            return OllamaCommandResponse(
                success=False, output=f"Cannot connect to Ollama server at {server_url}"
            )
        except req.exceptions.Timeout:
            return OllamaCommandResponse(
                success=False,
                output="Request timed out. The operation may still be in progress.",
            )
        except Exception as e:
            return OllamaCommandResponse(success=False, output=f"Error: {str(e)}")

    @api.post("/admin/ollama/clear-context", response_model=ClearOllamaContextResponse)
    async def clear_ollama_context(request: ClearOllamaContextRequest):
        """
        Clear Ollama conversation context for the current session.
        """
        _, _username, _role = validate_session_with_permission(
            request.session_id, Permission.VIEW_LOGS
        )

        session_id = request.session_id

        if session_id in ollama_conversation_history:
            msg_count = len(ollama_conversation_history[session_id])
            ollama_conversation_history[session_id] = []
            return ClearOllamaContextResponse(
                success=True,
                message=f"Conversation context cleared ({msg_count} messages removed).",
            )
        return ClearOllamaContextResponse(success=True, message="No conversation context to clear.")

    return api
