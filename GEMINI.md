# Lokality

A Python-based GUI chat assistant powered by Ollama and real-time DuckDuckGo search results, featuring persistent long-term memory and a modern Markdown-capable interface.

## Project Overview

`Lokality` is a desktop AI assistant designed to be helpful, context-aware, and connected. It accesses the internet to provide real-time information while maintaining a structured "long-term memory" using SQLite. It uses a local LLM via Ollama for conversation, decision-making, and memory management.

### Main Technologies
- **Python 3.12**: Core programming language.
- **Ollama**: Local LLM orchestration.
- **Tkinter**: GUI framework for the desktop interface.
- **SQLite3**: High-performance structured storage for long-term memory.
- **psutil**: Cross-platform system monitoring for RAM/VRAM detection.
- **Mistune 3.x**: Markdown parsing for rich text rendering.
- **DuckDuckGo Search (ddgs)**: Real-time internet search context.

## Architecture & Features

### 1. Modern GUI
- **Custom Theming**: Centralized in `src/theme.py`. A desaturated blue-purple palette with 6px thick rounded borders for distinct UI containers.
- **Smart Input**: A minimalist input box that expands vertically up to 8 lines. It supports both manual newlines (Shift+Enter) and automatic expansion for word-wrapped text using visual line detection.
- **Message Separation**: Faint horizontal separators (`#2A2A2A`) automatically inserted between message turns for clear visual structure.
- **Rich Text Rendering**: Handled by a dedicated `MarkdownEngine` using a dispatcher-based token rendering system. Supports full Markdown including:
  - **Hierarchical Headings** (H1-H3).
  - **Nested Styling**: Bold, Italic, Strikethrough, Subscript, and Superscript (e.g., ***Bold Italic*** rendered correctly).
  - **Complex Lists**: Nested ordered and unordered lists with correct indentation.
  - **Blockquotes**: Distinct visual sidebar (`┃`) for quoted text.
  - **Thematic Breaks**: Thicker, more visible horizontal rules.
  - **Tables**: Bordered grids compatible with Mistune 3.x structures.
  - **Interactive Links**: Clickable links with tooltips.

### 2. Intelligent Memory
- **SQLite Powered**: Facts are stored in a structured database (`res/memory.db`).
- **Contextual Retrieval**: Instead of loading all facts, the assistant uses FTS5-powered keyword matching to fetch only the most relevant memories for the current query.
- **Strict Extraction Logic**: Handled by `MemoryManager`. It uses an LLM-driven delta management system with a "Golden Rule": only record facts that will be relevant in one month.
  - **No Inference**: Preferences (likes/dislikes) are ONLY recorded if explicitly stated by the user.
  - **No Transients**: Current actions, recent chat events, and present-tense "wants" (e.g., "wants to know the time") are strictly ignored.

### 3. Real-Time Search & Integration
- **Search Engine**: A decoupled module using DuckDuckGo to fetch real-time data when the LLM determines it is necessary.
- **Bypass Mode**: A raw shell integration using PTY (Pseudo-Terminal) allows users to bypass the assistant logic and speak directly to the Ollama CLI wrapper.

### 4. System Monitoring & Logging
- **Hardware-Aware Initialization**: On startup, if no models are detected, `LocalChatAssistant` uses `psutil` and `sysfs` (on Linux) to detect available VRAM (supporting NVIDIA, AMD, and Intel). It selects the largest suitable Gemma 3 model from a predefined list in `config.py` and pulls it using the Ollama API, providing in-place progress updates in the GUI via carriage return (`\r`) handling.
- **Live Stats**: Handled by `StatsCollector`. Real-time tracking of Ollama model resource usage, including RAM, VRAM, and estimated context window consumption.
- **Visual Refinement**: Units (MB, %) are rendered in a smaller `unit` font for better visual hierarchy. Stats refresh automatically after every response.
- **Persistent Logging**: A centralized `logger.py` module handles timestamped logs in the `logs/` directory. Features automatic log rotation/cleanup (keeps logs for 30 days) and simultaneous stream/file output.

## Project Structure

- `src/`: Refactored into specialized modules.
  - `app.py`: Main entry point and GUI orchestration. Consolidated process management and dispatcher-based queue polling.
  - `config.py`: Global constants.
  - `theme.py`: UI styling, colors, and font definitions.
  - `markdown_engine.py`: Dispatcher-based logic for rendering Markdown tokens into Tkinter widgets. Supports complex nesting and modern Mistune plugins.
  - `logger.py`: Centralized logging configuration with automatic file-based persistence and cleanup logic.
  - `shell_integration.py`: PTY-based logic for the direct Ollama bypass.
  - `local_assistant.py`: Core logic for conversation management and system prompt templating.
  - `memory.py`: Low-level SQLite database interface with FTS5 triggers.
  - `memory_manager.py`: LLM-driven fact extraction with strict transient filtering.
  - `search_engine.py`: DuckDuckGo search integration.
  - `stats_collector.py`: Resource monitoring and context estimation.
  - `ui_components.py`: Custom Tkinter widgets with optimized layout and coordinate calculations.
  - `utils.py`: Shared utilities (rounded rectangles, ANSI stripping, environment health checks).
- `res/`: Persistent data.
  - `memory.db`: The SQLite database for long-term memory.
- `launch.sh`: Main entry point for launching the application via `src/app.py`.

## Development Conventions

- **Modular Design**: UI, Search, Stats, and Memory logic are strictly separated.
- **Non-Blocking**: Heavy operations (LLM extraction, web search, stats gathering) run in background threads.
- **Selective Learning**: The assistant is extractive and strict, focusing on permanent user attributes and identity facts.