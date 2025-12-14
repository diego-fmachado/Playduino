from colorlog import ColoredFormatter
from logging import StreamHandler

_COLORED_FORMATTER = ColoredFormatter(
   "%(log_color)s%(message)s",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "white",
        "WARNING": "yellow",
        "ERROR": "bold_red",
        "CRITICAL": "red"
    }
)

class ColoredStreamHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.setFormatter(_COLORED_FORMATTER)