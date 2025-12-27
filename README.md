# Lokality (v0.0.3)

## Description
Lokality is a local-first, privacy-focused desktop AI assistant wrapper. Powered by Ollama and built with Python, it provides a modern chat interface with long-term memory capabilities, real-time internet access, and many other useful features.

## Prerequisites
- **Python 3.12+**
- **Ollama**: Must be installed and running on your system.
- **Local LLM**: A model compatible with Ollama (e.g., `gemma3:4b-it-qat` or `llama3`).
- **Tkinter**: Usually included with Python, but may require separate installation on some Linux distributions (e.g., `python3-tk`).

## Installation
1. **Clone the repository**:
   ```bash
   git clone https://github.com/JackBartels/Lokality.git
   cd Lokality
   ```

2. **Set up a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install ollama ddgs mistune
   ```

4. **Pull the default model** (or your preferred model):
   ```bash
   ollama pull gemma3:4b-it-qat
   ```

5. **Launch the assistant**:
   ```bash
   ./launch.sh
   ```

## Testing
The project includes a comprehensive suite of unit tests. To run them, execute:
```bash
./.venv/bin/python3 -m unittest discover tests
```
Alternatively, if your virtual environment is active:
```bash
python3 -m unittest discover tests
```

## Features
- **Intelligent Long-Term Memory**: Automatically extracts and stores facts about the user in a local SQLite database for future reference.
- **Robust Fact Extraction**: Uses LLM-driven delta management to ADD, REMOVE, or UPDATE memories while filtering out transient information.
- **Real-Time Web Search**: Dynamically decides when to search the internet using DuckDuckGo to provide up-to-date information.
- **Model & System Info**: Use `/info` to toggle a live dashboard showing Model, Remaining Context, Long-term Memory size, and RAM/VRAM usage.
- **Rich Text Rendering**: Full Markdown support including headers, bold/italic text, lists, clickable links, and bordered graphical tables.
- **Modern GUI**: A sleek, blue-toned desaturated purple interface featuring 6px thick rounded borders, dynamic message separators, and a responsive flow layout.
- **Smart Input**: A dynamic input box that expands vertically as you type (including automatic expansion for word-wrapped lines) and features tab-completion for slash commands.
- **Model Agnostic**: Can be configured to work with any local model available via Ollama using the `LOKALITY_MODEL` environment variable.

## Available Commands
- `/bypass <prompt>`: Send a raw prompt directly to the Ollama CLI (bypass assistant logic).
- `/clear`: Reset current conversation history.
- `/debug`: Toggle debug mode to show internal logs and process information in the console.
- `/forget`: Permanently erase the long-term memory database.
- `/help`: View all available commands with descriptions.
- `/info`: Toggle the model and system statistics panel.
- `/exit`: Terminate the application.

## Compatibility
- **Primary Support**: Linux (Ubuntu/Debian tested).
- **Other Platforms**: Compatible with Windows and macOS provided Python, Tkinter, and Ollama are correctly installed.
