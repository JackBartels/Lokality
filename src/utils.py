"""
Utility functions for Lokality.
Handles environment checks, resource detection, and GUI helpers.
"""
from dataclasses import dataclass
from typing import Optional, Any
import glob
import os
import re
import subprocess
import sys
import traceback
import math

import psutil
import ollama
from PIL import Image, ImageDraw, ImageTk

import config
from logger import logger

@dataclass
class CanvasConfig:
    """Configuration for canvas region updates."""
    canvas: Any
    bg_id: int
    size: tuple[int, int]
    radius: int
    style: tuple[str, int, str]
    win_id: Optional[int] = None
    pad: tuple[float, float] = (0, 0)

@dataclass
class SidebarCallbacks:
    """Callbacks for sidebar interactions."""
    on_switch: Any
    on_close: Any
    on_resize: Any

@dataclass
class SidebarConfig:
    """Configuration for model sidebar construction."""
    parent: Any
    theme: Any
    fonts: dict
    models: list
    current_model: str
    callbacks: SidebarCallbacks

def thread_excepthook(args):
    """Global hook for catching uncaught exceptions in threads."""
    err_msg = (
        f"Thread Error ({args.thread.name}): "
        f"{args.exc_type.__name__}: {args.exc_value}"
    )
    error_print(err_msg)
    if config.DEBUG:
        traceback.print_exception(
            args.exc_type, args.exc_value, args.exc_traceback
        )

# ANSI escape code stripper
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\-_]| \[0-?]*[ -/]*[@-~])')

class OllamaClientManager:
    """Manages a singleton Ollama client instance."""
    _instance = None

    @classmethod
    def get_client(cls):
        """Returns the shared Ollama client."""
        if cls._instance is None:
            cls._instance = ollama.Client()
        return cls._instance

    @classmethod
    def reset_client(cls):
        """Resets the shared Ollama client instance."""
        cls._instance = None

def get_ollama_client():
    """Returns a shared Ollama client instance, initializing it on first call."""
    return OllamaClientManager.get_client()

def reset_ollama_client():
    """Resets the shared Ollama client (primarily for testing)."""
    OllamaClientManager.reset_client()

def strip_ansi(text):
    """Removes ANSI escape sequences from text."""
    return ANSI_ESCAPE.sub('', text)

def format_error_msg(exc):
    """Converts technical exceptions into user-friendly strings."""
    err_str = str(exc)
    # Check for Ollama connection refusal
    if "Connection refused" in err_str or "[Errno 111]" in err_str:
        return "Unable to connect to Ollama. Ensure the service is running."
    return err_str

def debug_print(msg):
    """
    Logs to DEBUG level and prints to stdout if DEBUG is enabled.
    Truncates extremely long messages to prevent log/UI bloat.
    """
    msg_str = str(msg)
    if len(msg_str) > 2048:
        msg_str = msg_str[:2048] + "... [TRUNCATED]"

    logger.debug(msg_str)
    if config.DEBUG:
        print(f"DEBUG: {msg_str}")

def error_print(msg):
    """Logs to ERROR level and prints to stderr."""
    logger.error(msg)
    print(f"Error: {msg}", file=sys.stderr)

def info_print(msg):
    """Logs to INFO level and prints to stdout."""
    logger.info(msg)
    print(msg)

# Global cache for PIL images to speed up rendering during resize
_RECT_CACHE = {}

@dataclass
class PilRectConfig:
    """Configuration for PIL-based rounded rectangle drawing."""
    width: int
    height: int
    radius: int
    fill: Optional[str]
    outline: Optional[str]
    outline_width: int
    margin: int

def _draw_pil_rounded_rect(cfg: PilRectConfig):
    """Helper to draw rounded rectangle using PIL."""
    # Cache key based on dimensions and style
    cache_key = (
        cfg.width, cfg.height, cfg.radius, cfg.fill,
        cfg.outline, cfg.outline_width
    )

    if cache_key in _RECT_CACHE:
        tk_img = _RECT_CACHE[cache_key]
    else:
        # 2x Oversampling
        os_factor = 2
        full_w, full_h = cfg.width + cfg.margin * 2, cfg.height + cfg.margin * 2

        img = Image.new("RGBA", (int(full_w * os_factor), int(full_h * os_factor)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Center-aligned coordinates
        half_lw = (cfg.outline_width * os_factor) / 2
        r_left, r_top = cfg.margin * os_factor, cfg.margin * os_factor
        r_right = (cfg.margin + cfg.width) * os_factor
        r_bottom = (cfg.margin + cfg.height) * os_factor

        if cfg.fill and cfg.fill != "":
            draw.rounded_rectangle(
                [r_left, r_top, r_right, r_bottom],
                radius=int(cfg.radius * os_factor), fill=cfg.fill, width=0
            )

        if cfg.outline and cfg.outline != "":
            # Centered outline: draw slightly outside and inside the boundary
            draw.rounded_rectangle(
                [r_left-half_lw, r_top-half_lw, r_right+half_lw, r_bottom+half_lw],
                radius=int(cfg.radius * os_factor + half_lw),
                fill=None, outline=cfg.outline, width=int(cfg.outline_width * os_factor)
            )

        # Sharp resize
        img = img.resize((full_w, full_h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        if len(_RECT_CACHE) > 100:
            _RECT_CACHE.clear()
        _RECT_CACHE[cache_key] = tk_img

    return tk_img

def _draw_poly_rounded_rect(canvas, coords, radius, **kwargs):
    """Helper to draw rounded rectangle using polygons."""
    x1, y1, x2, y2 = coords
    pts = []
    steps = 32
    # Top-right
    for i in range(steps + 1):
        ang = math.radians(270 + 90 * i / steps)
        pts.extend([
            x2 - radius + radius * math.cos(ang),
            y1 + radius + radius * math.sin(ang)
        ])
    # Bottom-right
    for i in range(steps + 1):
        ang = math.radians(0 + 90 * i / steps)
        pts.extend([
            x2 - radius + radius * math.cos(ang),
            y2 - radius + radius * math.sin(ang)
        ])
    # Bottom-left
    for i in range(steps + 1):
        ang = math.radians(90 + 90 * i / steps)
        pts.extend([
            x1 + radius + radius * math.cos(ang),
            y2 - radius + radius * math.sin(ang)
        ])
    # Top-left
    for i in range(steps + 1):
        ang = math.radians(180 + 90 * i / steps)
        pts.extend([
            x1 + radius + radius * math.cos(ang),
            y1 + radius + radius * math.sin(ang)
        ])

    return canvas.create_polygon(pts, smooth=False, **kwargs)

def round_rectangle(canvas, coords, radius=25, use_pil=True, **kwargs):
    """
    Draws a high-quality antialiased rounded rectangle.
    Optimized with caching and 2x oversampling for performance.
    """
    coords = [int(v) for v in coords]
    b = (min(coords[0], coords[2]), max(coords[0], coords[2]),
         min(coords[1], coords[3]), max(coords[1], coords[3]))

    radius = max(min(radius, (b[1] - b[0]) // 2, (b[3] - b[2]) // 2), 0)

    s = {
        'fill': kwargs.pop('fill', None),
        'outline': kwargs.pop('outline', None),
        'width': kwargs.pop('width', 0),
        'tags': kwargs.get('tags', [])
    }

    if (b[1] - b[0]) < 4 or (b[3] - b[2]) < 4:
        use_pil = False

    if use_pil:
        try:
            m = int(s['width'] + 8)
            tk_img = _draw_pil_rounded_rect(PilRectConfig(
                width=b[1] - b[0], height=b[3] - b[2], radius=radius,
                fill=s['fill'], outline=s['outline'],
                outline_width=s['width'], margin=m
            ))
            item = canvas.create_image(
                b[0] - m, b[2] - m, image=tk_img, anchor="nw", tags=s['tags']
            )
            if not hasattr(canvas, "pil_images"):
                canvas.pil_images = {}
            canvas.pil_images[item] = tk_img
            return item
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
            debug_print(f"PIL drawing failed: {exc}")

    # Fallback to polygon
    p_kw = kwargs.copy()
    for k in ['fill', 'outline', 'width']:
        if s[k]:
            p_kw[k] = s[k]

    return _draw_poly_rounded_rect(canvas, b, radius, **p_kw)

def _get_amd_vram():
    """Detects AMD VRAM using sysfs."""
    vram_mb = 0
    try:
        amd_cards = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
        for card_path in amd_cards:
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    bytes_val = int(f.read().strip())
                    vram_mb += bytes_val // (1024 * 1024)
            except (ValueError, IOError):
                continue
    except (OSError, IOError) as exc:
        logger.warning("Error checking AMD VRAM: %s", exc)
    return vram_mb

def _get_nvidia_vram():
    """Detects NVIDIA VRAM using nvidia-smi."""
    vram_mb = 0
    try:
        cmd = [
            "nvidia-smi", "--query-gpu=memory.total",
            "--format=csv,noheader,nounits"
        ]
        res = subprocess.check_output(
            cmd, encoding='utf-8', stderr=subprocess.DEVNULL
        )
        for line in res.strip().split('\n'):
            if line.strip():
                vram_mb += int(line.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass
    return vram_mb

def _check_uma_fallback(vram_mb, ram_mb):
    """Checks for UMA/Integrated GPU to use system RAM as VRAM pool."""
    if vram_mb >= 1024:
        return vram_mb
    try:
        uma_vendors = ['0x8086', '0x1002']
        found_uma = False
        for card_path in glob.glob("/sys/class/drm/card*/device/vendor"):
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    vendor_id = f.read().strip()
                    if vendor_id in uma_vendors:
                        found_uma = True
                        logger.info(
                            "Integrated/UMA GPU detected (%s). Using system RAM.",
                            vendor_id
                        )
                        break
            except (IOError, ValueError):
                continue
        if found_uma:
            return max(vram_mb, ram_mb)
    except (OSError, IOError) as exc:
        logger.warning("Error checking for UMA fallback: %s", exc)
    return vram_mb

def get_system_resources():
    """
    Returns (total_ram_mb, total_vram_mb).
    """
    try:
        ram_mb = psutil.virtual_memory().total // (1024 * 1024)
        vram_mb = _get_nvidia_vram()
        vram_mb += _get_amd_vram()
        vram_mb = _check_uma_fallback(vram_mb, ram_mb)
        return ram_mb, vram_mb
    except (psutil.Error, OSError) as exc:
        logger.warning("Failed to get system resources: %s", exc)
        return None, None

def verify_env_health():
    """Performs critical startup checks."""
    errors = []
    logger.info("[*] Performing environment health checks...")

    try:
        get_ollama_client().list()
    except (ollama.ResponseError, RuntimeError, ConnectionError) as exc:
        errors.append(format_error_msg(exc))

    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res_dir = os.path.join(parent_dir, "res")
    try:
        os.makedirs(res_dir, exist_ok=True)
        test_file = os.path.join(res_dir, ".write_test")
        with open(test_file, "w", encoding='utf-8') as f:
            f.write("test")
        os.remove(test_file)
    except (OSError, IOError) as exc:
        errors.append(f"Cannot write to '{res_dir}': {exc}")

    if not errors:
        logger.info("[*] Environment check passed.")
    return len(errors) == 0, errors

class RedirectedStdout:
    """Redirects stdout to a queue for GUI display."""
    def __init__(self, queue, tag="system"):
        self.queue = queue
        self.tag = tag
        self._original_stdout = sys.__stdout__

    def write(self, string):
        """Writes to the queue and optionally to original stdout."""
        if not string:
            return

        # Handle Carriage Return for progress bars
        if string.startswith('\r'):
            clean = strip_ansi(string[1:])
            if clean:
                self.queue.put(("replace_last", clean, self.tag))
        else:
            clean = strip_ansi(string)
            if clean:
                self.queue.put(("text", clean, self.tag))

        if config.DEBUG:
            try:
                self._original_stdout.write(string)
                self._original_stdout.flush()
            except (IOError, OSError):
                pass

    def flush(self):
        """Flushes the stream."""
        # No-op for redirect
