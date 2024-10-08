import logging
import logging.handlers
import sys


def _get_log_format():
    return logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')


class Logger:
    loggers = {}
    logLevel = logging.DEBUG # Capture all logs prior to switching

    sys.stderr = open('errout.txt', 'w')

    def configure_logger(self, level):
        self.logLevel = getattr(logging, level)

        for loggerName in self.loggers:
            self.loggers[loggerName].handlers.clear()
            self._setup_logger(loggerName)

    def _setup_logger(self, name):
        logger = logging.getLogger(name)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_get_log_format())
        handler.setLevel(logging.DEBUG)
        handler.addFilter(lambda record: record.levelno <= logging.INFO)
        logger.addHandler(handler)

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_get_log_format())
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)

        handler = logging.handlers.RotatingFileHandler(filename='diyhue.log', maxBytes=(10000000), backupCount=7)
        handler.setFormatter(_get_log_format())
        handler.setLevel(logging.DEBUG)
        handler.addFilter(lambda record: record.levelno <= logging.CRITICAL)
        logger.addHandler(handler)

        logger.setLevel(self.logLevel)
        logger.propagate = False
        return logger

    def get_logger(self, name):
        if name not in self.loggers:
            self.loggers[name] = self._setup_logger(name)
        return self.loggers[name]
