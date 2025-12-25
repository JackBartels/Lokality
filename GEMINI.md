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
- **Custom Theming**: A desaturated blue-purple palette with 6px thick rounded borders for distinct UI containers.
- **Dynamic Interface**: A minimalist input box that starts as a single line and expands vertically up to 8 lines.
- **Message Separation**: Faint horizontal separators (`#2A2A2A`) automatically inserted between message turns for clear visual structure.
- **Rich Text Rendering**: Full Markdown support with specific handling for tables (rendered as bordered grids) and syntax-highlighted code spans.
- **Responsive Info Panel**: A toggleable `/info` dashboard that uses a custom flow layout to wrap or distribute statistics based on window width.

### 2. Intelligent Memory
- **SQLite Powered**: Facts are stored in a structured database (`res/memory.db`).
- **Contextual Retrieval**: Instead of loading all facts, the assistant uses keyword matching to fetch only the most relevant memories for the current query.
- **Delta-based Updates**: Memory is updated non-blockingly in the background using specific ADD/REMOVE/UPDATE operations suggested by the LLM.
- **Fact Counting**: Internal logic tracks the total number of recorded memory entries for system monitoring.

### 3. Real-Time Search
- Uses a two-step process:
  1. **Decision**: Prompts the LLM to decide if real-time data is needed.
  2. **Execution**: Fetches top search results and injects them into the conversation context.

### 4. System Monitoring
- **Live Stats**: Real-time tracking of Ollama model resource usage, including RAM, VRAM, and estimated context window consumption.
- **Automatic Updates**: Statistics are refreshed automatically every time the model finishes generating a response.

## Project Structure

- `src/`: Contains all source code.
  - `gui_assistant.py`: The main GUI application, layout management, and rendering logic.
  - `local_assistant.py`: The core logic for LLM interaction, search orchestration, and stat gathering.
  - `memory.py`: Database interface for fact storage and retrieval.
- `res/`: Contains project resources and persistent data.
  - `memory.db`: The SQLite database for long-term memory.
- `launch.sh`: Main entry point for launching the application within the virtual environment.

## Development Conventions

- **Git Commands**: Only perform git commands (commit, branch, checkout, etc.) when the user explicitly says to do so.
- **Non-Blocking**: Heavy operations like LLM memory updates run in background threads to keep the UI responsive.
- **Selective Learning**: The assistant is extractive, focusing on permanent user attributes and identity facts.
- **Security**: No sensitive data or API keys are stored; everything runs locally via Ollama and SQLite.
