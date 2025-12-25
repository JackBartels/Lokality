# Lokality

## Description
Lokality is a local-first, privacy-focused desktop AI assistant. Powered by Ollama and built with Python, it provides a modern chat interface with long-term memory capabilities and real-time internet access. The assistant uses a structured SQLite database to remember personal facts and preferences, ensuring a personalized experience without relying on cloud-based memory.

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
- **Rich Text Rendering**: Full Markdown support including headers, bold/italic text, lists, and code blocks.
- **Modern GUI**: A clean, responsive interface built with Tkinter, featuring rounded corners, custom scrollbars, and a dark theme.
- **Model Agnostic**: Can be configured to work with any local model available via Ollama using the `LOKALITY_MODEL` environment variable.

## Compatibility
- **Primary Support**: Linux (Ubuntu/Debian tested).
- **Other Platforms**: Compatible with Windows and macOS provided Python, Tkinter, and Ollama are correctly installed.
