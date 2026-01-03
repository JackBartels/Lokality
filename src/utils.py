"""
Utility functions for Lokality.
Handles environment checks, resource detection, and GUI helpers.
"""
import glob
import os
import re
import subprocess
import sys
import traceback

import psutil
import ollama

import config
from logger import logger

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
_OLLAMA_CLIENT = ollama.Client()

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

def round_rectangle(canvas, coords, radius=25, **kwargs):
    """Draws a rounded rectangle on a Tkinter Canvas."""
    x1, y1, x2, y2 = coords
    # Ensure radius doesn't exceed dimensions to avoid visual glitches
    width = abs(x2 - x1)
    height = abs(y2 - y1)
    if radius > width // 2:
        radius = max(1, width // 2)
    if radius > height // 2:
        radius = max(1, height // 2)

    pts = [
        x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1,
        x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2,
        x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2,
        x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1
    ]
    return canvas.create_polygon(pts, **kwargs, smooth=True)

def _get_amd_vram():
    """Detects AMD VRAM using sysfs."""
    vram_mb = 0
    try:
        amd_cards = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
        for card_path in amd_cards:
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    # Value is in bytes
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
                            "Integrated/UMA GPU detected (%s). Using shared system RAM.",
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
        _OLLAMA_CLIENT.list()
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
