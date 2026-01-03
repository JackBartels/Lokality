"""
Data structures and state management for the Lokality application.
"""
import queue
import tkinter as tk
from dataclasses import dataclass, field
from typing import Optional, Any
import config
from ui_components import CustomScrollbar, InfoPanel

@dataclass
class IndicatorState:
    """Holds the thinking indicator state."""
    active: bool = False
    char: str = config.INDICATOR_CHARS[0]

@dataclass
class ResponseState:
    """Holds the current response state."""
    full_text: str = ""
    last_rendered_len: int = 0

@dataclass
class ProcessState:
    """Holds the model process state."""
    active: Optional[Any] = None
    is_busy: bool = False
    stop_generation: bool = False

@dataclass
class UIState:
    """Holds UI visibility state."""
    show_info: bool = False
    sidebar_visible: bool = False

@dataclass
class AppState:
    """Holds the application state."""
    assistant: Optional[Any] = None
    process: ProcessState = field(default_factory=ProcessState)
    auto_scroll: bool = True
    response: ResponseState = field(default_factory=ResponseState)
    ui_state: UIState = field(default_factory=UIState)
    msg_queue: queue.Queue = field(default_factory=queue.Queue)
    indicator: IndicatorState = field(default_factory=IndicatorState)

@dataclass
class ChatUI:
    """Holds chat display UI component references."""
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    inner: Optional[tk.Frame] = None
    window_id: Optional[int] = None
    display: Optional[tk.Text] = None
    scrollbar: Optional[CustomScrollbar] = None
    jump_btn_canvas: Optional[tk.Canvas] = None

@dataclass
class InputUI:
    """Holds input area UI component references."""
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    inner: Optional[tk.Frame] = None
    window_id: Optional[int] = None
    field: Optional[tk.Text] = None

@dataclass
class SidebarUI:
    """Holds sidebar UI component references."""
    frame: Optional[tk.Frame] = None
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    window_id: Optional[int] = None

@dataclass
class AppUI:
    """Holds UI component references."""
    chat: ChatUI = field(default_factory=ChatUI)
    input: InputUI = field(default_factory=InputUI)
    info_panel: Optional[InfoPanel] = None
    sidebar: SidebarUI = field(default_factory=SidebarUI)
    tooltip_window: Optional[tk.Toplevel] = None

@dataclass
class CanvasConfig:
    """Configuration for canvas region updates."""
    canvas: tk.Canvas
    bg_id: int
    size: tuple[int, int]
    radius: int
    style: tuple[str, int, str]
    win_id: int
    pad: tuple[int, float]

SLASH_COMMANDS = [
    ["/bypass", "Send raw prompt directly to model"],
    ["/clear", "Clear conversation history"],
    ["/debug", "Toggle debug mode"],
    ["/forget", "Reset long-term memory"],
    ["/help", "Show this help message"],
    ["/info", "Toggle model & system information"],
    ["/model", "Switch the current Ollama model"],
    ["/exit", "Exit the application"]
]
