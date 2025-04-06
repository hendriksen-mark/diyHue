import logging
import logging.handlers
import sys


class Logger:
    loggers = {}
    logLevel = logging.DEBUG  # Capture all logs prior to switching

    @staticmethod
    def _get_log_format():
        """Return the log format for the logger."""
        return logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')

    @staticmethod
    def _get_werkzeug_log_format():
        """Return the log format for Werkzeug logger."""
        return logging.Formatter('%(message)s')  # Exclude timestamp and other metadata

    def configure_logger(self, level):
        """Configure the logging level for all loggers."""
        self.logLevel = getattr(logging, level.upper(), logging.DEBUG)

        for loggerName in self.loggers:
            self.loggers[loggerName].handlers.clear()
            self._setup_logger(loggerName)

    def _setup_logger(self, name):
        """Set up a logger with the given name."""
        logger = logging.getLogger(name)

        # Stream handler for stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(self._get_log_format())
        stdout_handler.setLevel(self.logLevel)
        stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)
        logger.addHandler(stdout_handler)

        # Stream handler for stderr
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(self._get_log_format())
        stderr_handler.setLevel(logging.WARNING)
        logger.addHandler(stderr_handler)

        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename='diyhue.log', maxBytes=10000000, backupCount=7)
        file_handler.setFormatter(self._get_log_format())
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(lambda record: record.levelno <= logging.CRITICAL)
        logger.addHandler(file_handler)

        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        return logger

    def get_logger(self, name):
        """Get a logger by name, creating it if necessary."""
        if name not in self.loggers:
            self.loggers[name] = self._setup_logger(name)
        return self.loggers[name]

    def get_level_name(self):
        """Get the name of the current logging level."""
        return logging.getLevelName(self.logLevel)
