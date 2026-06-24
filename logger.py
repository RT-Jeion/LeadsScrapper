"""
Logging utilities for structured terminal output.
"""

import time


def now_stamp():
    """Return current time as HH:MM:SS string."""
    return time.strftime("%H:%M:%S")


def log_line(level, message):
    """
    Print a timestamped log line.
    
    Args:
        level: Log level tag (INFO, OK, WARN, ERROR, etc.)
        message: Log message
    """
    print(f"[{now_stamp()}] [{level}] {message}")


def section(title):
    """
    Print a formatted section header with separator lines.
    
    Args:
        title: Section title to display
    """
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")
