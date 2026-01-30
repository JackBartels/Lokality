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
- **Trafilatura**: Advanced web scraping and text extraction.
- **Specialized APIs**: Wikipedia (encyclopedia), Python-weather, GNews, and YFinance (finance).

## Architecture & Features

### 1. Modern GUI
- **Custom Theming**: Centralized in `src/theme.py`. A desaturated blue-purple palette with rounded borders.
- **Smart Input**: A minimalist input box that expands vertically up to 8 lines with visual line detection.
- **Responsive Layout**: Modular components using `grid` and `pack` with automatic resizing and rounded containers.
- **Jump to Latest**: A floating button appears when scrolling away from the bottom to allow quick navigation back to the latest messages.
- **UI Scaling**: Automatic DPI-aware scaling ensures the interface remains sharp and appropriately sized on all monitors.
- **Interruptible Generation**: Dedicated Esc-key handling allows users to immediately halt LLM responses or active search operations.
- **Rich Text Rendering**: `MarkdownEngine` handles headings, nested lists, blockquotes, tables, and links.
- **Interactive Code Blocks**: Code blocks include a header with the language name and a "Copy" button for easy interaction.

### 2. Intelligent Memory
- **SQLite Powered**: Facts are stored in `res/memory.db`.
- **Contextual Retrieval**: Uses FTS5-powered keyword matching to fetch only relevant memories.
- **Strict Extraction**: `MemoryManager` uses LLM-driven delta management with the "Golden Rule" (1-month relevance) and transient filtering.
- **Parallel Processing**: Memory retrieval runs in parallel with search gatekeeping during the turn preparation phase to minimize latency.

### 3. Multi-Stage Search & Specialized Tools
- **Pipeline Architecture**:
  1. **Gatekeeper**: A fast, single-token check to decide if search is even necessary.
  2. **Planner**: A JSON-based planner that formulates queries and identifies specialized intents (Weather, News, Finance).
  3. **Wikipedia Pass**: Checks Wikipedia for general knowledge before hitting the live web.
  4. **Live Search**: Uses DuckDuckGo for real-time results.
  5. **Analytical Scraping**: Uses `trafilatura` for high-quality content extraction from selected URLs.
- **Specialized Search**: Dedicated modules for weather, global news, and financial data (tickers/stock prices).

### 4. Performance Profiling
- **Real-Time Tracking**: The `Profiler` module tracks timing for critical operations (Search, Scraping, Memory, LLM Generation).
- **Visual Dashboard**: A dedicated `ProfilerPanel` (toggled via `/profiler`) displays a vertical bar chart of task durations for the current turn.

### 5. System Monitoring & Settings
- **Hardware-Aware Initialization**: Auto-pulls the largest suitable Gemma 3 model based on available VRAM (supporting NVIDIA, AMD, and Intel).
- **Live Stats**: `StatsCollector` tracks real-time RAM/VRAM usage and context consumption.
- **State Preservation**: Persistent settings (`res/settings.json`) store UI toggles and selected models across sessions.

### 6. Safety & Crisis Response
- **Mandatory Protocol**: A specialized safety layer detects crisis situations and prioritizes professional resources over general conversation.
- **Search Gatekeeping**: Automatically skips external web searches when safety disclaimers and emergency contacts are required.
- **Integrated Disclaimers**: Professional advice disclaimers are contextually injected to ensure user safety.

## Project Structure

- `src/`: Refactored into specialized modules.
  - `app.py`: Main entry point and GUI orchestration.
  - `app_state.py`: Centralized state management using dataclasses.
  - `complexity_scorer.py`: Analyzes input to dynamically adjust model parameters.
  - `config.py`: Global constants and UI configuration.
  - `local_assistant.py`: Core logic for conversation, search orchestration, and memory.
  - `markdown_engine.py`: Dispatcher-based Markdown rendering with code interaction.
  - `memory.py`: Low-level SQLite database interface with FTS5.
  - `memory_manager.py`: LLM-driven fact extraction and filtering.
  - `profiler.py`: Performance measurement and task tracking.
  - `search_engine.py`: Wikipedia and DuckDuckGo integration with scraping.
  - `specialized_search.py`: Handlers for weather, news, and financial data.
  - `stats_collector.py`: Resource monitoring and context estimation.
  - `ui_components.py`: Custom widgets (Scrollbars, InfoPanel, ProfilerPanel).
  - `ui_dialogs.py`: Modular dialog windows (Confirmation, Alerts).
  - `ui_helpers.py`: Shared GUI utilities (Jump button, Chat tags).
  - `utils.py`: Shared utilities (Rounded rectangles, Resource detection).
- `res/`: Persistent data (Memory DB, Settings, Assets).
- `tests/`: Comprehensive test suite covering all modules.

## Development Conventions

- **Modular Design**: UI, Search, Stats, and Memory logic are strictly separated.
- **File Integrity**: ALWAYS read the full content of a file before attempting to edit it. This ensures accurate targeting and prevents truncation or logic errors.
- **Non-Blocking**: Heavy operations run in background threads with status updates via a message queue.
- **Selective Learning**: Focus on permanent user attributes and identity facts; ignore transients.
- **Code Quality**: Strict adherence to Pylint standards (10.00/10 score). No `# pylint: disable` comments allowed.
- **Testing**: All changes must be verified with: `PYTHONPATH=src .venv/bin/python -m unittest discover tests`.
- **Git & Version Control**: Preliminary staging (`git add`) is acceptable, but final commits are user-gated.