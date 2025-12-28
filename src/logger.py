import datetime
import glob
import logging
import os
import sys

import config

def cleanup_logs(log_dir):
    """Removes logs older than MAX_LOG_AGE_DAYS if there are more than MIN_LOGS_FOR_CLEANUP files."""
    log_files = glob.glob(os.path.join(log_dir, "*.txt"))
    if len(log_files) <= config.MIN_LOGS_FOR_CLEANUP:
        return

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=config.MAX_LOG_AGE_DAYS)

    for f in log_files:
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f))
            if mtime < cutoff:
                os.remove(f)
        except Exception:
            # Silently fail if we can't delete a file (e.g. it's open)
            pass

def get_logger(name="lokality"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Prevent double setup
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config.LOG_DIR)
        os.makedirs(log_dir, exist_ok=True)

        cleanup_logs(log_dir)

        # Filename: MM-DD-YYYY-HH-mm-ss.txt
        now = datetime.datetime.now()
        log_file = now.strftime("%m-%d-%Y-%H-%M-%S.txt")
        log_path = os.path.join(log_dir, log_file)

        logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # File Handler
        try:
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fallback if log file cannot be created
            print(f"Failed to create log file: {e}")

        # Stream Handler
        stream_handler = logging.StreamHandler(sys.__stdout__)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
        # Avoid propagating to the root logger to prevent duplicate logs in some environments
        logger.propagate = False

    return logger

# Create a default instance for easy import
logger = get_logger()
