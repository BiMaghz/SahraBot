import logging
import sys

class Colors:
    RESET = "\033[0m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    CYAN = "\033[0;36m"
    BOLD_RED = "\033[1;31m"

    if not sys.stdout.isatty():
        RED = GREEN = YELLOW = CYAN = BOLD_RED = RESET = ""

class CustomFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: f"{Colors.CYAN}%(asctime)s - DEBUG - [%(name)s:%(lineno)d]{Colors.RESET} - %(message)s",
        logging.INFO: f"{Colors.GREEN}%(asctime)s - INFO - [%(name)s:%(lineno)d]{Colors.RESET} - %(message)s",
        logging.WARNING: f"{Colors.YELLOW}%(asctime)s - WARNING - [%(name)s:%(lineno)d]{Colors.RESET} - %(message)s",
        logging.ERROR: f"{Colors.RED}%(asctime)s - ERROR - [%(name)s:%(lineno)d]{Colors.RESET} - %(message)s",
        logging.CRITICAL: f"{Colors.BOLD_RED}%(asctime)s - CRITICAL - [%(name)s:%(lineno)d]{Colors.RESET} - %(message)s",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

def setup_logging():
    root_logger = logging.getLogger()
    
    root_logger.setLevel(logging.INFO)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomFormatter())
    root_logger.addHandler(console_handler)

    logging.info("Logging setup is complete.")