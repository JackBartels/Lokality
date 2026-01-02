"""
Shell integration for Lokality.
Provides PTY-based raw access to the Ollama CLI.
"""
import os
import pty
import select
import subprocess

from config import MODEL_NAME
from logger import logger
from utils import error_print

class ShellIntegration:
    """
    Handles raw interaction with the Ollama CLI using pseudo-terminals.
    """
    @staticmethod
    def _process_ansi(char, state):
        """Handles ANSI escape sequences."""
        if char == "\x1b":
            state["in_ansi"] = True
            return True
        if state["in_ansi"]:
            if char.isalpha() or char in "@~_":
                state["in_ansi"] = False
            return True
        return False

    @staticmethod
    def _detect_prompt(char, master, prompt, state):
        """Detects the Ollama prompt and sends the command."""
        if char in ["\x07", "\r"]:
            return False

        state["prompt_detector"] += char
        if len(state["prompt_detector"]) > 10:
            state["prompt_detector"] = state["prompt_detector"][-10:]

        # Initial prompt detection
        if not state["command_sent"] and ">>>" in state["prompt_detector"]:
            os.write(master, (prompt + "\n").encode())
            state["command_sent"] = True
            state["prompt_detector"] = ""
            return True

        # Final prompt detection
        if state["command_sent"] and ">>>" in state["prompt_detector"]:
            state["completed"] = True
            return True
        return False

    @staticmethod
    def _handle_pty_data(master, prompt, state, msg_queue):
        """Processes a chunk of data from the PTY."""
        try:
            data = os.read(master, 1024).decode(errors="ignore")
            if not data:
                return False

            output_buffer = []
            for char in data:
                if ShellIntegration._process_ansi(char, state):
                    continue

                is_prompt = ShellIntegration._detect_prompt(char, master, prompt, state)

                if state["completed"]:
                    # Flush buffer before returning
                    if output_buffer:
                        chunk = "".join(output_buffer)
                        state["full_response"] += chunk
                        msg_queue.put(("text", chunk, "assistant"))
                    return False

                if is_prompt:
                    continue

                if state["command_sent"]:
                    output_buffer.append(char)

            # Flush buffer at end of chunk
            if output_buffer:
                chunk = "".join(output_buffer)
                state["full_response"] += chunk
                msg_queue.put(("text", chunk, "assistant"))

            return True
        except OSError:
            return False

    @staticmethod
    def _start_ollama_process(slave):
        """Starts the Ollama process with the given slave PTY."""
        new_env = os.environ.copy()
        new_env["TERM"] = "xterm"
        return subprocess.Popen(
            ["ollama", "run", MODEL_NAME],
            stdin=slave, stdout=slave, stderr=slave,
            text=True, bufsize=0, env=new_env, close_fds=True
        )

    @staticmethod
    def run_ollama_bypass(prompt, msg_queue, stop_check_callback):
        """Runs Ollama in bypass mode using a PTY for raw CLI interaction."""
        logger.info("Starting bypass mode for prompt: %s...", prompt[:50])
        master = None
        process = None
        try:
            master, slave = pty.openpty()
            process = ShellIntegration._start_ollama_process(slave)
            os.close(slave)

            state = {
                "full_response": "", "in_ansi": False, "prompt_detector": "",
                "command_sent": False, "completed": False
            }

            while not state["completed"]:
                if stop_check_callback():
                    break
                r_fds, _, _ = select.select([master], [], [], 0.1)
                if not r_fds:
                    if process.poll() is not None:
                        break
                    continue
                if not ShellIntegration._handle_pty_data(master, prompt, state, msg_queue):
                    break

            if state["completed"]:
                return "COMPLETED", process
            return state["full_response"], process

        except (OSError, subprocess.SubprocessError) as exc:
            error_print(f"Error in bypass: {exc}")
            return None, None
        finally:
            if master is not None:
                try:
                    os.close(master)
                except OSError:
                    pass

    @staticmethod
    def is_available():
        """Checks if ollama is available in the system path."""
        try:
            subprocess.run(["ollama", "--version"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False
