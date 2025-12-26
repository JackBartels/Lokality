import re
import config

# ANSI escape code stripper
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\-_]| \[0-?]*[ -/]*[@-~])')

def strip_ansi(text):
    return ANSI_ESCAPE.sub('', text)

def debug_print(msg):
    """Prints only if DEBUG is enabled in config."""
    if config.DEBUG:
        print(msg)

def round_rectangle(canvas, x1, y1, x2, y2, radius=25, **kwargs):
    """Draws a rounded rectangle on a Tkinter Canvas."""
    points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
    return canvas.create_polygon(points, **kwargs, smooth=True)

class RedirectedStdout:
    def __init__(self, queue, tag="system"):
        self.queue = queue
        self.tag = tag

    def write(self, string):
        if string:
            clean = strip_ansi(string)
            if clean:
                self.queue.put(("text", clean, self.tag))

    def flush(self):
        pass
