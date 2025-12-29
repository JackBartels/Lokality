# Lokality (v0.1.0)

## Description
Lokality is a local-first, privacy-focused desktop AI assistant wrapper. Powered by Ollama and built with Python, it provides a modern chat interface with real-time internet access, long-term memory capabilities, and many other useful features.

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
   pip install ollama ddgs mistune psutil
   ```

4. **Model Setup**:
   Lokality will automatically detect your system resources (VRAM) and pull a suitable `gemma3` model on first launch if no models are found. You can also manually pull your preferred model:
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
- **Hardware-Aware Auto-Initialization**: On first run, if no models are detected, Lokality automatically scans your system VRAM (supporting NVIDIA, AMD, and Intel) and pulls the most optimal Gemma 3 model for your hardware with real-time progress feedback.
- **Intelligent Long-Term Memory**: Automatically extracts and stores facts about the user in a local SQLite database for future reference.
- **Robust Fact Extraction**: Uses LLM-driven delta management to ADD, REMOVE, or UPDATE memories. It features a strict "Golden Rule" to ensure only permanent facts are stored, while transient actions, present-tense wants, and inferred preferences are strictly ignored.
- **Real-Time Web Search**: Dynamically decides when to search the internet using DuckDuckGo to provide up-to-date information.
- **Model & System Info**: Use `/info` to toggle a live info bar showing Model, Remaining Context, Long-term Memory size, and RAM/VRAM usage.
- **Advanced Markdown Support**: 
    - Full support for **Headings**, **Bold**, **Italics**, **Strikethrough**, **Subscript**, and **Superscript**.
    - Nested styling (e.g., ***Bold Italic***) support.
    - **Ordered & Unordered Lists** with correct nesting and indentation.
    - **Blockquotes** with a visual vertical sidebar indicator.
    - **Tables** with bordered graphical rendering.
    - **Horizontal Rules** for thematic separation.
    - Clickable links with tooltips.
- **Modern GUI**: A sleek, blue-toned desaturated purple interface featuring 6px thick rounded borders, dynamic message separators, and a responsive flow layout.
- **Smart Input**: A dynamic input box that expands vertically as you type (including automatic expansion for word-wrapped lines) and features tab-completion for slash commands.
- **Persistent Logging**: Centralized logging system that records session details to the `logs/` directory with automatic cleanup of files older than 30 days.
- **Optimized Architecture**: Refactored with a dispatcher-based rendering engine and consolidated background process management for improved performance and maintainability.
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
- **GPU Support**: NVIDIA, AMD (Discrete/Integrated), and Intel (Discrete/Integrated).
- **Other Platforms**: Windows and macOS are **not officially supported**, though Lokality may work if Python, Tkinter, and Ollama are correctly installed.