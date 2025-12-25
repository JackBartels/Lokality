# Lokality

## Description
Lokality is a local-first, privacy-focused desktop AI assistant. Powered by Ollama and built with Python, it provides a modern chat interface with long-term memory capabilities, real-time internet access, and deep system integration. The assistant uses a structured SQLite database to remember personal facts and preferences, ensuring a personalized experience without relying on cloud-based memory.

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
   pip install ollama duckduckgo_search mistune
   ```

4. **Pull the default model** (or your preferred model):
   ```bash
   ollama pull gemma3:4b-it-qat
   ```

5. **Launch the assistant**:
   ```bash
   ./launch.sh
   ```

## Features
- **Intelligent Long-Term Memory**: Automatically extracts and stores facts about the user in a local SQLite database for future reference.
- **Real-Time Web Search**: Dynamically decides when to search the internet using DuckDuckGo to provide up-to-date information.
- **Model & System Info**: Use `/info` to toggle a live dashboard showing current model stats, context usage, RAM/VRAM consumption, and memory size.
- **Rich Text Rendering**: Full Markdown support including headers, bold/italic text, lists, and bordered graphical tables.
- **Modern GUI**: A sleek, blue-toned desaturated purple interface featuring 6px thick rounded borders, dynamic message separators, and a responsive flow layout.
- **Smart Input**: A single-line dynamic input box that expands as you type and features intelligent tab-completion for slash commands.
- **Model Agnostic**: Can be configured to work with any local model available via Ollama using the `LOKALITY_MODEL` environment variable.

## Available Commands
- `/clear`: Reset current conversation history.
- `/clear-long-term`: Permanently erase the long-term memory database.
- `/help`: View all available commands with descriptions.
- `/info`: Toggle the model and system statistics panel.
- `/exit`: Terminate the application.

## Compatibility
- **Primary Support**: Linux (Ubuntu/Debian tested).
- **Other Platforms**: Compatible with Windows and macOS provided Python, Tkinter, and Ollama are correctly installed.