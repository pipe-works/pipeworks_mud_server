"""
Gradio-based web client for the MUD server.

This is the main entry point for the MUD client interface. It creates a
multi-tab Gradio interface by composing individual tab modules.

The application has been refactored into a modular structure:
    - api_client.py: All backend API communication
    - utils.py: Shared utility functions
    - static/styles.css: Centralized CSS styling
    - tabs/: Individual tab modules (login, game, settings, etc.)

Interface Structure:
    Tab 1: Login - User authentication
    Tab 2: Register - New account creation
    Tab 3: Game - Main gameplay interface with auto-refresh
    Tab 4: Settings - Password change and server control (admin only)
    Tab 5: Database - Admin database viewer (admin/superuser only)
    Tab 6: Ollama - Ollama server management and AI model control (admin/superuser only)
    Tab 7: Help - Game instructions and command reference

Key Features:
    - Per-user session state using gr.State (prevents cross-user contamination)
    - Auto-refresh timer (3 seconds) for real-time game updates
    - Role-based UI elements (admin features hidden for regular players)
    - Chat system with support for say, yell, and whisper commands
    - Modular architecture for easy maintenance and extensibility

State Management:
    Each user has their own gr.State dictionary containing:
    - session_id: UUID from successful login
    - username: Player's username
    - role: User role (player, worldbuilder, admin, superuser)
    - logged_in: Boolean login status

API Communication:
    All game operations communicate with the FastAPI backend via HTTP requests
    through the api_client module.
"""

import gradio as gr

# Import utility functions
from mud_server.client.utils import load_css, create_session_state

# Import API client for login function (needed for top-level event wiring)
from mud_server.client.api_client import login, logout

# Import tab modules
from mud_server.client.tabs import (
    login_tab,
    register_tab,
    game_tab,
    settings_tab,
    database_tab,
    ollama_tab,
    help_tab,
)


def create_interface():
    """
    Create and configure the complete Gradio web interface.

    Builds the entire multi-tab UI by composing individual tab modules.
    Each tab module is responsible for its own layout, components, and
    event handlers. This function handles only top-level integration and
    tab visibility control based on authentication state.

    Returns:
        gr.Blocks: Configured Gradio interface ready to launch
    """
    # Load CSS from external file
    custom_css = load_css("styles.css")

    with gr.Blocks(title="MUD Client", theme=gr.themes.Soft(), css=custom_css) as interface:
        gr.Markdown("# MUD Client")
        gr.Markdown("A simple Multi-User Dungeon client")

        # Session state (per-user)
        session_state = gr.State(create_session_state())

        with gr.Tabs():
            # Create all tabs
            (
                login_tab_component,
                login_btn,
                login_username_input,
                login_password_input,
                login_output,
            ) = login_tab.create()

            register_tab_component = register_tab.create()
            game_tab_component, game_logout_btn = game_tab.create(session_state)
            settings_tab_component = settings_tab.create(session_state)
            database_tab_component = database_tab.create(session_state)
            ollama_tab_component = ollama_tab.create(session_state)
            help_tab_component = help_tab.create()

        # Wire up login event handler
        login_btn.click(
            login,
            inputs=[login_username_input, login_password_input, session_state],
            outputs=[
                session_state,
                login_output,
                login_username_input,
                login_password_input,
                login_tab_component,
                register_tab_component,
                game_tab_component,
                settings_tab_component,
                database_tab_component,
                ollama_tab_component,
                help_tab_component,
            ],
        )

        # Wire up logout button to update tab visibility
        # This needs to be separate from the Game tab handler because tabs aren't defined yet there
        def logout_and_hide_tabs(session_st):
            """
            Handle logout button click and update tab visibility.

            This is a separate handler from the one in the Game tab because
            tab visibility components need to be wired at the top level after
            all tabs are defined. Calls logout() and extracts the relevant
            outputs for session state, message, and tab visibility updates.

            Returns:
                Tuple for Gradio outputs: (session_state, message, login_tab,
                register_tab, game_tab, settings_tab, database_tab, ollama_tab, help_tab)
            """
            result = logout(session_st)
            return (
                result[0],
                result[1],
                result[3],
                result[4],
                result[5],
                result[6],
                result[7],
                result[8],
                result[9],
            )

        game_logout_btn.click(
            logout_and_hide_tabs,
            inputs=[session_state],
            outputs=[
                session_state,
                login_output,
                login_tab_component,
                register_tab_component,
                game_tab_component,
                settings_tab_component,
                database_tab_component,
                ollama_tab_component,
                help_tab_component,
            ],
        )

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
