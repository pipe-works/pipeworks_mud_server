"""
Ollama Tab for MUD Client.

This module provides the Ollama management interface for controlling AI models.
Visible only for admin and superuser roles.
"""

import gradio as gr
from mud_server.client.api_client import execute_ollama_command


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
            gr.Markdown(
                """
Control and interact with your Ollama server. This tab allows you to manage AI models,
run inference, and monitor running models.

**Supported Commands:**
- `list` or `ls` - List all available models
- `ps` - Show currently running models
- `pull <model>` - Download a new model (e.g., `pull llama2`)
- `run <model> [prompt]` - Run a model with optional prompt (e.g., `run llama2 Write a haiku`)
- `show <model>` - Show detailed model information
                """
            )

            # Server URL Input
            gr.Markdown("#### Server Configuration")
            ollama_url_input = gr.Textbox(
                label="Ollama Server URL",
                placeholder="http://localhost:11434",
                value="http://localhost:11434",
                max_lines=1,
            )

            # Command Input
            gr.Markdown("#### Command")
            with gr.Row():
                ollama_command_input = gr.Textbox(
                    label="Command",
                    placeholder="Enter Ollama command (e.g., 'list', 'run llama2 Hello')",
                    max_lines=1,
                    scale=4,
                )
                execute_ollama_btn = gr.Button("Execute", variant="primary", scale=1)

            # Quick action buttons
            gr.Markdown("#### Quick Actions")
            with gr.Row():
                list_models_btn = gr.Button("List Models", scale=1)
                show_running_btn = gr.Button("Show Running", scale=1)

            # Output Console
            gr.Markdown("#### Console Output")
            ollama_output = gr.Textbox(
                label="Output",
                interactive=False,
                lines=20,
                max_lines=30,
                placeholder="Command output will appear here...",
            )

            # Event handlers for Ollama tab
            def handle_execute_ollama(url, cmd, session_st):
                """Execute Ollama command and return output."""
                return execute_ollama_command(url, cmd, session_st)

            def handle_list_models(url, session_st):
                """Quick action: List models."""
                return execute_ollama_command(url, "list", session_st)

            def handle_show_running(url, session_st):
                """Quick action: Show running models."""
                return execute_ollama_command(url, "ps", session_st)

            execute_ollama_btn.click(
                handle_execute_ollama,
                inputs=[ollama_url_input, ollama_command_input, session_state],
                outputs=[ollama_output],
            )

            # Also submit on Enter key in command input
            ollama_command_input.submit(
                handle_execute_ollama,
                inputs=[ollama_url_input, ollama_command_input, session_state],
                outputs=[ollama_output],
            )

            list_models_btn.click(
                handle_list_models,
                inputs=[ollama_url_input, session_state],
                outputs=[ollama_output],
            )

            show_running_btn.click(
                handle_show_running,
                inputs=[ollama_url_input, session_state],
                outputs=[ollama_output],
            )

    return ollama_tab
