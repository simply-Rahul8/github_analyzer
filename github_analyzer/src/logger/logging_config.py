import logging
import os
import sys

_logging_configured = False

def setup_logging(log_file_path=None):
    """
    Configures logging to write to console (and optionally a file).
    Idempotent: safe to call from multiple modules.
    On Render/production, uses /tmp/logs.txt to ensure write access.
    """
    global _logging_configured

    logger = logging.getLogger("GitHubAnalyzer")

    if _logging_configured:
        return logger

    _logging_configured = True

    handlers = [logging.StreamHandler(sys.stdout)]

    # Determine a writable log file path
    if log_file_path is None:
        # Use /tmp on Linux/Render, fallback to local logs.txt on Windows dev
        if os.name == 'nt':
            log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs.txt')
            log_file_path = os.path.normpath(log_file_path)
        else:
            log_file_path = '/tmp/logs.txt'

    try:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        handlers.append(file_handler)
    except Exception:
        # If file logging fails (e.g. permission error), silently use stdout only
        pass

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )

    return logger
