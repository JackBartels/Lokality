"""
Performance profiling for Lokality operations.
Tracks duration of key tasks like Memory Lookup, Search Decision, and Scraping.
"""
import time
import threading
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class TaskRecord:
    """Record of a single profiled task."""
    name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0

class Profiler:
    """
    Thread-safe singleton for tracking task durations.
    """
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        """Ensures only one instance of the Profiler exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Profiler, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        """Initializes the profiler if not already done."""
        if not hasattr(self, '_initialized'):
            with self._lock:
                if not hasattr(self, '_initialized'):
                    self.enabled = False
                    self.active_tasks: Dict[str, float] = {}
                    self.completed_tasks: List[TaskRecord] = []
                    self._initialized = True

    def reset(self):
        """Clears all recorded metrics."""
        with self._lock:
            self.active_tasks.clear()
            self.completed_tasks.clear()

    def start(self, task_name: str):
        """Starts timing a task."""
        if not getattr(self, 'enabled', False):
            return
        with self._lock:
            self.active_tasks[task_name] = time.time()

    def stop(self, task_name: str):
        """Stops timing a task and records the duration."""
        if not getattr(self, 'enabled', False):
            return
        end_time = time.time()
        with self._lock:
            start_time = self.active_tasks.pop(task_name, None)
            if start_time:
                duration = (end_time - start_time) * 1000
                self.completed_tasks.append(TaskRecord(
                    name=task_name,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=round(duration, 2)
                ))

    def get_summary(self) -> str:
        """Returns a formatted summary string of the latest turn."""
        with self._lock:
            if not self.completed_tasks:
                return "No data"
            # Sort by start time
            sorted_tasks = sorted(self.completed_tasks, key=lambda x: x.start_time)
            return " | ".join([f"{t.name}: {t.duration_ms}ms" for t in sorted_tasks])

    def get_latest_data(self) -> List[Dict]:
        """Returns the raw data for UI rendering."""
        with self._lock:
            return [
                {"name": t.name, "duration": t.duration_ms}
                for t in sorted(self.completed_tasks, key=lambda x: x.start_time)
            ]
