# Lokality

A Python-based GUI chat assistant powered by Ollama and real-time DuckDuckGo search results, featuring persistent long-term memory and a modern Markdown-capable interface.

## Project Overview

`Lokality` is a desktop AI assistant designed to be helpful, context-aware, and connected. It accesses the internet to provide real-time information while maintaining a structured "long-term memory" using SQLite. It uses a local LLM via Ollama for conversation, decision-making, and memory management.

### Main Technologies
- **Python 3.12**: Core programming language.
- **Ollama**: Local LLM orchestration.
- **Tkinter**: GUI framework for the desktop interface.
- **SQLite3**: High-performance structured storage for long-term memory.
- **Mistune**: Markdown parsing for rich text rendering.
- **DuckDuckGo Search (ddgs)**: Real-time internet search context.

## Architecture & Features

### 1. Modern GUI
- **Dynamic Interface**: Automatically resizing input box and Send button.
- **Rich Text Rendering**: Full Markdown support including bold, italics, headers, lists, and links.
- **Graphical Tables**: Markdown tables are rendered as clean, bordered visual grids.
- **Custom Styling**: Modern rounded corners and a bespoke rounded scrollbar.

### 2. Intelligent Memory
- **SQLite Powered**: Facts are stored in a structured database (`res/memory.db`) with O(log N) retrieval speed.
- **Contextual Retrieval**: Instead of loading all facts, the assistant uses keyword matching to fetch only the most relevant memories for the current query.
- **Delta-based Updates**: Memory is updated non-blockingly in the background using specific ADD/REMOVE/UPDATE operations suggested by the LLM.
- **Source of Truth**: The model is strictly instructed to treat the memory as the definitive source for personal details, reducing hallucinations.

### 3. Real-Time Search
- Uses a two-step process:
  1. **Decision**: Prompts the LLM to decide if real-time data is needed.
  2. **Execution**: Fetches top search results and injects them into the conversation context.

## Project Structure

- `src/`: Contains all source code.
  - `gui_assistant.py`: The main GUI application and rendering logic.
  - `local_assistant.py`: The core `LocalChatAssistant` and `MemoryStore` classes.
- `res/`: Contains project resources and persistent data.
  - `memory.db`: The SQLite database for long-term memory.
- `run_gui.sh`: Shell script to activate the virtual environment and launch Lokality.

## Getting Started

### Prerequisites
- [Ollama](https://ollama.com/) must be installed and running.
- Pull a supported model (e.g., Gemma, Llama):
  ```bash
  ollama pull <model_name>
  ```

Update `MODEL_NAME` in `src/local_assistant.py` to match your pulled model.

### Running the Assistant
Execute the following command in your terminal:
```bash
./run_gui.sh
```

### Available Commands
Inside the chat, you can use:
- `/help`: Show available commands.
- `/clear`: Clear the current conversation history and the visible chat window.
- `/clear-long-term`: Reset the entire long-term memory database.
- `/exit` or `quit`: Terminate the session.

## Development Conventions

- **Non-Blocking**: Heavy operations like LLM memory updates run in background threads to keep the UI responsive.
- **Selective Learning**: The assistant is extractive, focusing on permanent user attributes and identity facts.
- **Security**: No sensitive data or API keys are stored; everything runs locally via Ollama and SQLite.