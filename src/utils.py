import re

# ANSI escape code stripper
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\-_]| \[0-?]*[ -/]*[@-~])')

def strip_ansi(text):
    return ANSI_ESCAPE.sub('', text)

class RedirectedStdout:
    def __init__(self, queue, tag="system"):
        self.queue = queue
        self.tag = tag

    def write(self, string):
        # Filter out purely whitespace writes that might clutter, unless it's a newline
        if string:
            clean = strip_ansi(string)
            # We want to capture meaningful logs.
            if clean:
                self.queue.put(("text", clean, self.tag))

    def flush(self):
        pass
