# Lokality (v0.1.3)

## Description
Lokality is a privacy-focused desktop AI assistant powered by local models, via Ollama, and built with Python. It provides a modern chat interface for use with local models, equipping them with real-time internet access, long-term memory capabilities, and many other useful features.

## Prerequisites
- **Python 3.12+**
- **Ollama**: Must be installed and running on your system.
- **Local LLM**: A model compatible with Ollama (e.g., `gemma3:4b-it-qat`).
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
   pip install -r requirements.txt
   ```

4. **Model Setup**:
   Lokality automatically detects your system resources (VRAM) and pulls a suitable `gemma3` model on first launch if no models are found. You can also manually pull your preferred model:
   ```bash
   ollama pull gemma3:4b-it-qat
   ```

5. **Launch the assistant**:
   ```bash
   ./launch.sh
   ```

## Features
- **Hardware-Aware Auto-Initialization**: On first run, Lokality scans your system VRAM and pulls the most optimal model for your hardware with real-time progress feedback.
- **Intelligent Long-Term Memory**: Automatically remembers facts about you to provide personalized assistance in future conversations.
- **Data Privacy**: All memories are stored locally in a private database that you control.
- **Real-Time Web Search**: The assistant can browse the internet to answer questions about current events.
- **Smart Memory Management**: A user-friendly confirmation dialog prevents accidental memory erasure and includes a "Don't ask again" option for power users.
- **Dynamic Performance Tuning**: Automatically adjusts model parameters based on the complexity of your request to ensure fast and accurate responses.
- **Model & System Stats**: A live info bar displays the current model, memory usage, and system resource consumption (RAM/VRAM).
- **Modern GUI**: A sleek interface with smooth animations, distinct message styling, and a responsive layout.
- **Advanced Markdown**: Full support for rich text including headings, nested lists, blockquotes, tables, and interactive links.
- **Persistent Settings**: Your preferences (like debug mode and info panel visibility) are saved automatically between sessions.

## Available Commands
- `/bypass <prompt>`: Send a raw prompt directly to the Ollama CLI (bypass assistant logic).
- `/clear`: Reset current conversation history.
- `/debug`: Toggle debug mode to show internal logs and process information in the console.
- `/forget`: Permanently erase the long-term memory database.
- `/help`: View all available commands with descriptions.
- `/info`: Toggle the model and system statistics panel.
- `/model`: Open a sidebar to switch between your installed Ollama models.
- `/exit`: Terminate the application.

## Compatibility
- **Primary Support**: Linux (Ubuntu/Debian tested).
- **GPU Support**: Any hardware supported by Ollama.
- **Other Platforms**: Windows and macOS are not officially supported, but may work if Python, Tkinter, and Ollama are correctly configured.
