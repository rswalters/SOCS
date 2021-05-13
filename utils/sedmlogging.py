import logging
import time
from logging.handlers import TimedRotatingFileHandler

formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")


def setup_logger(logname, log_file, level=logging.DEBUG):
    """To setup as many loggers as you want"""

    logger = logging.getLogger(logname)
    logger.setLevel(logging.DEBUG)
    logging.Formatter.converter = time.gmtime
    logHandler = TimedRotatingFileHandler(log_file, when='midnight', utc=True,
                                          interval=1, backupCount=360)
    logHandler.setFormatter(formatter)
    logHandler.setLevel(level)
    logger.addHandler(logHandler)
    logger.info("Starting Logger: Logger file is %s", '%s' % log_file)

    return logger
