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
- **Custom Theming**: Centralized in `src/theme.py`. A desaturated blue-purple palette with 6px thick rounded borders for distinct UI containers.
- **Smart Input**: A minimalist input box that expands vertically up to 8 lines. It supports both manual newlines (Shift+Enter) and automatic expansion for word-wrapped text using visual line detection.
- **Message Separation**: Faint horizontal separators (`#2A2A2A`) automatically inserted between message turns for clear visual structure.
- **Rich Text Rendering**: Handled by a dedicated `MarkdownEngine`. Supports full Markdown including tables (rendered as bordered grids), syntax-highlighted code spans, and clickable links with tooltips.
- **Responsive Info Panel**: A toggleable `/info` dashboard that uses a custom flow layout to wrap or distribute statistics based on window width.

### 2. Intelligent Memory
- **SQLite Powered**: Facts are stored in a structured database (`res/memory.db`).
- **Contextual Retrieval**: Instead of loading all facts, the assistant uses keyword matching to fetch only the most relevant memories for the current query.
- **Delta-based Updates**: Memory is updated non-blockingly using `MemoryManager`. It uses an LLM-driven "extraction" phase to suggest ADD/REMOVE/UPDATE operations.

### 3. Real-Time Search & Integration
- **Search Engine**: A decoupled module using DuckDuckGo to fetch real-time data when the LLM determines it is necessary.
- **Bypass Mode**: A raw shell integration using PTY (Pseudo-Terminal) allows users to bypass the assistant logic and speak directly to the Ollama CLI wrapper.

### 4. System Monitoring
- **Live Stats**: Handled by `StatsCollector`. Real-time tracking of Ollama model resource usage, including RAM, VRAM, and estimated context window consumption.
- **Debug Mode**: A toggleable `/debug` state that redirects internal logs and LLM reasoning processes to the terminal for real-time inspection.
- **Visual Refinement**: Units (MB, %) are rendered in a smaller `unit` font for better visual hierarchy. Stats refresh automatically after every response.

## Project Structure

- `src/`: Refactored into specialized modules.
  - `app.py`: Main entry point and GUI orchestration.
  - `config.py`: Global constants (version, model names, debug flags).
  - `theme.py`: UI styling, colors, and font definitions.
  - `markdown_engine.py`: Logic for rendering Markdown tokens into Tkinter widgets.
  - `shell_integration.py`: PTY-based logic for the direct Ollama bypass.
  - `local_assistant.py`: Core logic for conversation management.
  - `memory.py`: Low-level SQLite database interface.
  - `memory_manager.py`: LLM-driven fact extraction and delta management.
  - `search_engine.py`: DuckDuckGo search integration.
  - `stats_collector.py`: Resource monitoring and context estimation.
  - `ui_components.py`: Custom Tkinter widgets like the rounded scrollbar.
  - `utils.py`: Shared utilities (rounded rectangles, ANSI stripping, stdout redirection).
- `res/`: Persistent data.
  - `memory.db`: The SQLite database for long-term memory.
- `launch.sh`: Main entry point for launching the application via `src/app.py`.

## Development Conventions



- **Modular Design**: UI, Search, Stats, and Memory logic are strictly separated.

- **Non-Blocking**: Heavy operations (LLM extraction, web search) run in background threads.

- **Selective Learning**: The assistant is extractive, focusing on permanent user attributes and identity facts.

- **Git Hygiene**: Do NOT perform git operations (commit, push, branch creation) unless explicitly requested by the user.
