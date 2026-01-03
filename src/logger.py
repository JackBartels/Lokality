"""
Centralized logging configuration for Lokality.
"""
import datetime
import glob
import logging
import os
import sys

import config

def cleanup_logs(log_dir):
    """
    Removes logs older than MAX_LOG_AGE_DAYS if there are more than 
    MIN_LOGS_FOR_CLEANUP files. Also caps total log files at MAX_LOG_FILES.
    """
    log_files = glob.glob(os.path.join(log_dir, "*.txt"))
    if not log_files:
        return

    # 1. Remove logs older than MAX_LOG_AGE_DAYS
    if len(log_files) > config.MIN_LOGS_FOR_CLEANUP:
        now = datetime.datetime.now()
        cutoff = now - datetime.timedelta(days=config.MAX_LOG_AGE_DAYS)

        for f in log_files:
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f))
                if mtime < cutoff:
                    os.remove(f)
            except OSError:
                # Silently fail if we can't delete a file (e.g. it's open)
                pass

    # 2. Enforce MAX_LOG_FILES limit
    log_files = glob.glob(os.path.join(log_dir, "*.txt"))
    if len(log_files) > config.MAX_LOG_FILES:
        # Sort by modification time (oldest first)
        log_files.sort(key=os.path.getmtime)
        files_to_remove = len(log_files) - config.MAX_LOG_FILES

        for i in range(files_to_remove):
            try:
                os.remove(log_files[i])
            except OSError:
                pass

def get_logger(name="lokality"):
    """
    Initializes and returns a logger instance with file and stream handlers.
    """
    new_logger = logging.getLogger(name)
    if not new_logger.handlers:
        # Prevent double setup
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            config.LOG_DIR
        )
        os.makedirs(log_dir, exist_ok=True)

        cleanup_logs(log_dir)

        # Filename: MM-DD-YYYY-HH-mm-ss.txt
        now = datetime.datetime.now()
        log_file = now.strftime("%m-%d-%Y-%H-%M-%S.txt")
        log_path = os.path.join(log_dir, log_file)

        new_logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

        fmt = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
        formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

        # File Handler
        try:
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setFormatter(formatter)
            new_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            # Fallback if log file cannot be created
            print(f"Failed to create log file: {e}")

        # Stream Handler
        stream_handler = logging.StreamHandler(sys.__stdout__)
        stream_handler.setFormatter(formatter)
        new_logger.addHandler(stream_handler)

        # Avoid propagating to the root logger to prevent duplicates
        new_logger.propagate = False

    return new_logger

# Create a default instance for easy import
logger = get_logger()
