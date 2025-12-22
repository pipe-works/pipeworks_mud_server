# Installation Guide

Detailed instructions for installing and configuring The Undertaking.

## System Requirements

### Minimum Requirements

- **Operating System**: Linux, macOS, or Windows
- **Python**: 3.12 or higher
- **RAM**: 512 MB (1 GB recommended)
- **Disk Space**: 100 MB for installation, 500 MB recommended
- **Network**: Internet connection for pip dependencies

### Recommended

- **RAM**: 2 GB
- **Disk Space**: 1 GB
- **Network**: Stable internet connection
- **Browser**: Modern browser (Chrome, Firefox, Safari, Edge)

## Step-by-Step Installation

### 1. Install Python 3.12+

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

#### macOS

```bash
# Using Homebrew
brew install python@3.12

# Or download from python.org
# https://www.python.org/downloads/
```

#### Windows

Download and install from [python.org](https://www.python.org/downloads/)

Make sure to check "Add Python to PATH" during installation.

### 2. Install Git

#### Linux (Ubuntu/Debian)

```bash
sudo apt install git
```

#### macOS

```bash
brew install git
# Or use Xcode Command Line Tools
xcode-select --install
```

#### Windows

Download from [git-scm.com](https://git-scm.com/downloads)

### 3. Clone the Repository

```bash
git clone https://github.com/yourusername/pipeworks_mud_server.git
cd pipeworks_mud_server
```

Or download the ZIP from GitHub and extract it.

### 4. Create Virtual Environment

```bash
python3 -m venv venv
```

Activate the virtual environment:

```bash
# Linux/macOS
source venv/bin/activate

# Windows (Command Prompt)
venv\Scripts\activate.bat

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

You should see `(venv)` in your terminal prompt.

### 5. Install Dependencies

#### Production Dependencies

```bash
pip install -r requirements.txt
```

This installs:

- FastAPI - REST API framework
- Gradio - Web interface
- uvicorn - ASGI server
- SQLite support (aiosqlite)
- Authentication libraries (passlib, bcrypt)
- HTTP client (requests)

#### Development Dependencies (Optional)

```bash
pip install -r requirements-dev.txt
```

This adds:

- pytest - Testing framework
- ruff - Linting
- black - Code formatting
- mypy - Type checking
- Coverage tools

#### Documentation Dependencies (Optional)

```bash
pip install -r requirements-docs.txt
```

This adds:

- MkDocs - Documentation generator
- Material theme
- API documentation tools

### 6. Initialize the Database

```bash
PYTHONPATH=src python3 -m mud_server.db.database
```

This creates:

- `data/mud.db` - SQLite database file
- Default tables (players, sessions, chat_messages)
- Default superuser account (admin/admin123)

!!! danger "Security Warning"
    **Change the default admin password immediately!**

    The default credentials are:
    - Username: `admin`
    - Password: `admin123`

    Anyone who knows these can access your server with full privileges.

### 7. Verify Installation

Check that everything is installed correctly:

```bash
# Check Python version
python3 --version

# Check pip packages
pip list

# Check database exists
ls -lh data/mud.db

# Run tests (if dev dependencies installed)
PYTHONPATH=src pytest
```

### 8. Configure Environment Variables (Optional)

Create a `.env` file in the project root:

```bash
# Server configuration
MUD_HOST=0.0.0.0
MUD_PORT=8000
MUD_SERVER_URL=http://localhost:8000

# Database path (relative to project root)
DB_PATH=data/mud.db

# World data path
WORLD_DATA_PATH=data/world_data.json

# Log directory
LOG_DIR=logs
```

These values are optional; defaults will be used if not specified.

### 9. Run the Server

```bash
./run.sh
```

On Windows:

```bash
# Run server
PYTHONPATH=src python src/mud_server/api/server.py

# In another terminal, run client
PYTHONPATH=src python src/mud_server/client/app.py
```

### 10. Verify Server is Running

Open your browser:

- **Client**: http://localhost:7860
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

You should see the Gradio interface and be able to log in.

## Configuration

### Project Structure

```
pipeworks_mud_server/
├── src/mud_server/     # Main Python package
├── data/               # Database and world data
├── logs/               # Server logs
├── documentation/      # This documentation
├── tests/              # Test suite
├── requirements.txt    # Production dependencies
├── run.sh              # Startup script
└── mkdocs.yml          # Documentation config
```

### Server Configuration

Edit environment variables or modify `src/mud_server/api/server.py`:

```python
# Server binding
HOST = os.getenv("MUD_HOST", "0.0.0.0")
PORT = int(os.getenv("MUD_PORT", 8000))

# CORS settings
CORS_ORIGINS = ["*"]  # Adjust for production
```

### Database Configuration

The database path can be changed in `src/mud_server/db/database.py`:

```python
DB_PATH = os.getenv("DB_PATH", "data/mud.db")
```

### World Data

Edit `data/world_data.json` to customize rooms and items.

## Upgrading

### Update from Git

```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

### Backup Database

Before upgrading:

```bash
cp data/mud.db data/mud.db.backup
```

### Reset Database

To start fresh (deletes all data):

```bash
rm data/mud.db
PYTHONPATH=src python3 -m mud_server.db.database
```

## Uninstallation

### Remove Virtual Environment

```bash
deactivate
rm -rf venv
```

### Remove Data

```bash
rm -rf data/mud.db logs/*.log
```

### Remove Everything

```bash
cd ..
rm -rf pipeworks_mud_server
```

## Next Steps

- [Quick Start Guide](quick-start.md) - Get running in 30 seconds
- [First Steps](first-steps.md) - Your first actions in the game
- [User Guide](../guide/playing.md) - Learn how to play
- [Developer Guide](../developer/setup.md) - Set up for development
