import os
import pty
import select
import signal
import subprocess
from config import MODEL_NAME

class ShellIntegration:
    @staticmethod
    def run_ollama_bypass(prompt, msg_queue, stop_check_callback):
        """Runs Ollama in bypass mode using a PTY for raw CLI interaction."""
        try:
            master, slave = pty.openpty()
            new_env = os.environ.copy()
            new_env["TERM"] = "xterm"
            
            process = subprocess.Popen(
                ["ollama", "run", MODEL_NAME],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                text=True,
                bufsize=0,
                env=new_env,
                close_fds=True
            )
            os.close(slave)
            
            full_response = ""
            in_ansi = False
            prompt_detector = ""
            command_sent = False
            
            while True:
                if stop_check_callback():
                    break
                    
                r, _, _ = select.select([master], [], [], 0.1)
                if not r:
                    if process.poll() is not None:
                        break
                    continue
                    
                try:
                    data = os.read(master, 1024).decode(errors='ignore')
                    if not data:
                        break
                        
                    for char in data:
                        if char == '\x1b':
                            in_ansi = True
                            continue
                        if in_ansi:
                            if char.isalpha() or char in '@~_':
                                in_ansi = False
                            continue
                        if char in ['\x07', '\r']:
                            continue

                        prompt_detector += char
                        if len(prompt_detector) > 10:
                            prompt_detector = prompt_detector[-10:]
                        
                        if not command_sent and ">>>" in prompt_detector:
                            os.write(master, (prompt + "\n").encode())
                            command_sent = True
                            prompt_detector = ""
                            continue
                        
                        if command_sent and ">>>" in prompt_detector:
                            return "COMPLETED", process
                        
                        if command_sent:
                            full_response += char
                            msg_queue.put(("text", char, "assistant"))
                    
                except OSError:
                    break
            
            return full_response, process
            
        except Exception as e:
            msg_queue.put(("text", f"Error in bypass: {e}\n", "error"))
            return None, None
        finally:
            try:
                os.close(master)
            except:
                pass
