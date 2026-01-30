"""
Ollama Tab for MUD Client.

This module provides the Ollama management interface for controlling AI models.
Visible only for admin and superuser roles.

Migration Notes:
    - Migrated from old api_client.py to new modular structure
    - Uses OllamaAPIClient for Ollama command execution and context management
    - Wrapper functions extract session_id and role from session_state
    - Returns message string for Gradio display
    - Parameter order changed: session_id and role now come first
"""

import gradio as gr

from mud_server.admin_gradio.api.ollama import OllamaAPIClient

# Create module-level API client instance for reuse
_ollama_client = OllamaAPIClient()


def execute_ollama_command(server_url: str, command: str, session_state: dict) -> str:
    """
    Execute an Ollama command on the specified server (Admin/Superuser only).

    Sends request to backend via OllamaAPIClient and returns command output.

    This function wraps the new OllamaAPIClient.execute_command() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Note: Parameter order is maintained from old API (server_url, command, session_state)
    for compatibility with existing Gradio event handlers.

    Args:
        server_url: URL of the Ollama server
        command: Ollama command to execute
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Command output string or error message

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = execute_ollama_command("http://localhost:11434", "list", session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    # Note: New API has different parameter order (session_id, role, server_url, command)
    api_result = _ollama_client.execute_command(
        session_id=session_id,
        role=role,
        server_url=server_url,
        command=command,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def clear_ollama_context(session_state: dict) -> str:
    """
    Clear Ollama conversation context for the current session (Admin/Superuser only).

    Sends request to backend via OllamaAPIClient and returns confirmation message.

    This function wraps the new OllamaAPIClient.clear_context() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Confirmation message string or error message

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = clear_ollama_context(session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    api_result = _ollama_client.clear_context(
        session_id=session_id,
        role=role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def create(session_state):
    """
    Create the Ollama tab with model management interface.

    Args:
        session_state: Gradio State component for session tracking

    Returns:
        gr.Tab: Configured Ollama tab component
    """
    with gr.Tab("Ollama", visible=False) as ollama_tab:
        with gr.Column():
            gr.Markdown("### Ollama Management")
            gr.Markdown("*Admin and Superuser only*")

            # Collapsible documentation section
            with gr.Accordion("Documentation & Commands", open=False):
                gr.Markdown("""
Control and interact with your Ollama server. This tab allows you to manage AI models,
run inference, and monitor running models.

**Supported Commands:**
- `/list` or `/ls` - List all available models
- `/ps` - Show currently running models
- `/pull <model>` - Download a new model (e.g., `/pull llama2`)
- `/run <model> [prompt]` - Run a model with optional prompt (e.g., `/run llama2 Write a haiku`)
- `/show <model>` - Show detailed model information

**Conversational Mode:**
After running a model with `/run`, you can continue chatting naturally without the `/run` prefix.
The system will remember your active model until you start a new `/run` command.
                    """)

            # Server URL Input
            gr.Markdown("#### Server Configuration")
            ollama_url_input = gr.Textbox(
                label="Ollama Server URL",
                placeholder="http://localhost:11434",
                value="http://localhost:11434",
                max_lines=1,
            )

            # Output Console (moved above command input)
            gr.Markdown("#### Console Output")
            ollama_output = gr.Textbox(
                label="Output",
                interactive=False,
                lines=20,
                max_lines=30,
                placeholder="Command output will appear here...",
            )

            # Command Input (moved below console output)
            gr.Markdown("#### Command")
            with gr.Row():
                ollama_command_input = gr.Textbox(
                    label="Command",
                    placeholder="Enter Ollama command (e.g., '/list', '/run llama2 Hello') or continue conversation",
                    max_lines=1,
                    scale=4,
                )
                execute_ollama_btn = gr.Button("Execute", variant="primary", scale=1)

            # Hidden state to track active model for conversational mode
            active_model = gr.State(None)

            # Add a Clear Context button
            clear_context_btn = gr.Button("Clear Conversation Context", variant="secondary")

            # Event handlers for Ollama tab
            def handle_execute_ollama(url, cmd, current_model, session_st):
                """
                Execute Ollama command with slash command support and conversational mode.

                Handles:
                - Slash commands (/list, /ps, /pull, /run, /show)
                - Conversational continuation (auto-uses active model)
                - Model tracking for conversation mode
                """
                # Strip leading/trailing whitespace
                cmd = cmd.strip() if cmd else ""

                if not cmd:
                    return "Please enter a command.", current_model

                # Check if it's a slash command
                if cmd.startswith("/"):
                    # Remove the slash
                    cmd = cmd[1:]

                    # Check if it's a run command to track the model
                    if cmd.startswith("run "):
                        parts = cmd.split(maxsplit=2)
                        if len(parts) >= 2:
                            new_model = parts[1]  # Extract model name
                            output = execute_ollama_command(url, cmd, session_st)
                            return output, new_model  # Update active model

                    # Execute the command
                    output = execute_ollama_command(url, cmd, session_st)
                    return output, current_model

                # If no slash and we have an active model, continue conversation
                elif current_model:
                    # Continue conversation with active model
                    continuation_cmd = f"run {current_model} {cmd}"
                    output = execute_ollama_command(url, continuation_cmd, session_st)
                    return output, current_model

                # No slash, no active model - inform user
                else:
                    return (
                        "Please use a slash command (e.g., /list, /run llama2 Hello) or start a conversation with /run first.",
                        current_model,
                    )

            def handle_clear_context(session_st):
                """
                Clear conversation context for the current session.

                Returns:
                    Tuple of (output_message, cleared_model)
                """
                # Call the module-level wrapper function (no import needed)
                result = clear_ollama_context(session_st)
                return result, None  # Also clear the active model

            execute_ollama_btn.click(
                handle_execute_ollama,
                inputs=[ollama_url_input, ollama_command_input, active_model, session_state],
                outputs=[ollama_output, active_model],
            )

            # Also submit on Enter key in command input
            ollama_command_input.submit(
                handle_execute_ollama,
                inputs=[ollama_url_input, ollama_command_input, active_model, session_state],
                outputs=[ollama_output, active_model],
            )

            # Wire up clear context button
            clear_context_btn.click(
                handle_clear_context,
                inputs=[session_state],
                outputs=[ollama_output, active_model],
            )

    return ollama_tab
