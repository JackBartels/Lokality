import glob
import os
import re
import subprocess
import sys

import psutil

import config
from logger import logger

# ANSI escape code stripper
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\-_]| \[0-?]*[ -/]*[@-~])')

def strip_ansi(text):
    return ANSI_ESCAPE.sub('', text)

def format_error_msg(e):
    """Converts technical exceptions into user-friendly strings."""
    err_str = str(e)
    # Check for Ollama connection refusal
    if "Connection refused" in err_str or "[Errno 111]" in err_str:
        return "Unable to connect to Ollama. Ensure the service is running."
    return err_str

def debug_print(msg):
    """Logs to DEBUG level and prints to stdout if DEBUG is enabled.
    Truncates extremely long messages to prevent log/UI bloat."""
    msg_str = str(msg)
    if len(msg_str) > 2048:
        msg_str = msg_str[:2048] + "... [TRUNCATED]"
        
    logger.debug(msg_str)
    if config.DEBUG:
        print(f"DEBUG: {msg_str}")

def error_print(msg):
    """Logs to ERROR level and prints to stderr. These appear in the GUI chat."""
    logger.error(msg)
    print(f"Error: {msg}", file=sys.stderr)

def info_print(msg):
    """Logs to INFO level and prints to stdout. These appear in the GUI chat."""
    logger.info(msg)
    print(msg)

def round_rectangle(canvas, x1, y1, x2, y2, radius=25, **kwargs):
    """Draws a rounded rectangle on a Tkinter Canvas."""
    # Ensure radius doesn't exceed dimensions to avoid visual glitches
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if radius > w // 2: radius = max(1, w // 2)
    if radius > h // 2: radius = max(1, h // 2)
    
    points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
    return canvas.create_polygon(points, **kwargs, smooth=True)

def get_system_resources():
    """
    Returns (total_ram_mb, total_vram_mb).
    RAM is system RAM. VRAM is Discrete GPU VRAM (NVIDIA or AMD).
    Returns (None, None) on failure.
    """
    try:
        # 1. System RAM
        ram_mb = psutil.virtual_memory().total // (1024 * 1024)
        
        # 2. VRAM
        vram_mb = 0
        
        # Check NVIDIA
        try:
            res = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                encoding='utf-8', stderr=subprocess.DEVNULL
            )
            for line in res.strip().split('\n'):
                if line.strip():
                    vram_mb += int(line.strip())
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            pass
            
        # Check AMD (Direct Rendering Manager sysfs)
        # We look for 'mem_info_vram_total' which is typically exposed for Discrete GPUs
        # or the dedicated portion of APUs.
        try:
            amd_cards = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
            for card_path in amd_cards:
                try:
                    with open(card_path, 'r') as f:
                        # Value is in bytes
                        bytes_val = int(f.read().strip())
                        vram_mb += bytes_val // (1024 * 1024)
                except (ValueError, IOError):
                    continue
        except Exception as e:
            logger.warning(f"Error checking AMD VRAM: {e}")

        # Unified Memory Architecture (UMA) Fallback
        # If detected discrete VRAM is effectively unusable (< 1GB) for LLMs,
        # but we detect an Intel (0x8086) or AMD (0x1002) GPU, 
        # assume it's an Integrated/UMA system and use System RAM.
        if vram_mb < 1024:
            try:
                # Check for Intel or AMD vendor IDs
                # 0x8086 = Intel, 0x1002 = AMD
                uma_vendors = ['0x8086', '0x1002']
                found_uma = False
                
                for card_path in glob.glob("/sys/class/drm/card*/device/vendor"):
                    try:
                        with open(card_path, 'r') as f:
                            vendor_id = f.read().strip()
                            if vendor_id in uma_vendors:
                                found_uma = True
                                logger.info(f"Integrated/UMA GPU detected ({vendor_id}). Using shared system RAM.")
                                break
                    except (IOError, ValueError):
                        continue
                
                if found_uma:
                    # Use full system RAM as the memory pool for the LLM.
                    # We take the max of what we found in discrete vs total RAM.
                    vram_mb = max(vram_mb, ram_mb)
                    
            except Exception as e:
                logger.warning(f"Error checking for UMA fallback: {e}")

        return ram_mb, vram_mb
    except Exception as e:
        logger.warning(f"Failed to get system resources: {e}")
        return None, None

def verify_env_health():
    """Performs critical startup checks. Returns (True, []) or (False, [errors])."""
    errors = []
    logger.info("[*] Performing environment health checks...")
    
    # 1. Ollama & 2. Resource Permissions
    try:
        import ollama
        ollama.Client().list()
    except Exception as e:
        errors.append(format_error_msg(e))

    res_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "res")
    try:
        os.makedirs(res_dir, exist_ok=True)
        test_file = os.path.join(res_dir, ".write_test")
        with open(test_file, "w") as f: f.write("test")
        os.remove(test_file)
    except Exception as e:
        errors.append(f"Cannot write to '{res_dir}': {e}")

    if not errors: logger.info("[*] Environment check passed.")
    return len(errors) == 0, errors

class RedirectedStdout:
    def __init__(self, queue, tag="system"):
        self.queue = queue
        self.tag = tag
        self._original_stdout = sys.__stdout__

    def write(self, string):
        if string:
            # Handle Carriage Return for line replacement (progress bars)
            if string.startswith('\r'):
                clean = strip_ansi(string[1:])
                if clean:
                    self.queue.put(("replace_last", clean, self.tag))
            else:
                clean = strip_ansi(string)
                if clean:
                    # Normal prints go to GUI
                    self.queue.put(("text", clean, self.tag))

            # Also mirror to terminal if debugging
            if config.DEBUG:
                    try:
                        self._original_stdout.write(string)
                        self._original_stdout.flush()
                    except:
                        pass

    def flush(self):
        pass
