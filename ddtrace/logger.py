import collections
import logging

from .settings import config

loggers = dict()

config._add('tracer', dict(log_everything=False))


class DDLogFilter(object):
    __slots__ = ('buckets', )

    LEVEL_RATES = {
        # Log debug messages once per 5 minutes
        logging.DEBUG: 300,
        # Log info messages once per 2 minutes
        logging.INFO: 120,
        # Log warn messages once per 1 minute
        logging.WARN: 60,
        # Log error messages once per 30 seconds
        logging.ERROR: 30,
        # Log critical messages once per 10 seconds
        logging.CRITICAL: 10,
    }

    def __init__(self):
        # Keep track of the current time bucket for each log record
        # Value is (<last logged time bucket>, <count of skipped records>)
        self.buckets = collections.defaultdict(lambda: (0, 0))

    # DEV: `filter` will only get called if the logger is configured to log that log level
    #      this means we do not need to worry about tracking rates for records that would
    #      not be logged anyways due to the current level
    #   https://github.com/python/cpython/blob/902196d867a34cc154fa9c861c883e69232251c6/Lib/logging/__init__.py#L1448-L1449
    def filter(self, record):
        # Check for config option that allows logging every message... firehose mode
        if config.tracer.log_everything:
            return True

        # Allow 1 log record by name/level/pathname/lineno every X seconds
        # DEV: current unix time / rate (e.g. 300 seconds) = time bucket
        #      int(1546615098.8404942 / 300) = 515538
        # DEV: LogRecord `created` is a unix timestamp/float
        # DEV: LogRecord has `levelname` and `levelno`, we want `levelno` e.g. `logging.DEBUG = 10`
        bucket = int(record.created / DDLogFilter.LEVEL_RATES.get(record.levelno, 300))

        # Limit based on logger name, record level, filename, and line number
        #   ('ddtrace.writer', 'DEBUG', '../site-packages/ddtrace/writer.py', 137)
        # This way each unique log message can get logged at least once per time period
        # DEV: LogRecord has `levelname` and `levelno`, we want `levelno` e.g. `logging.DEBUG = 10`
        key = (record.name, record.levelno, record.pathname, record.lineno)

        # Only log this message if the time bucket has changed from the previous time we ran
        last_bucket, skipped = self.buckets[key]
        if last_bucket != bucket:
            self.buckets[key] = (bucket, 0)
            return True
        else:
            # Increment the count of records we have skipped
            self.buckets[key] = (last_bucket, skipped + 1)
            return False


def get_logger(name):
    global loggers

    logger = loggers[name] = logging.getLogger(name)
    logger.addFilter(DDLogFilter())

    return logger


def configure(level):
    global loggers
    for name, logger in loggers.items():
        logger.setLevel(level)
