import logging

from graypy import GELFUDPHandler

FORMAT = "%(asctime)s | %(levelname)s | %(filename)s:%(funcName)s:%(lineno)d | %(message)s"  # настройка форматирования записей
DATEFMT = "%Y-%m-%d %H:%M:%S"  # настройка отображения времени


def setup_logger(
        name: str,
        graylog_host: str,
        graylog_port: int,
        console_level: int = logging.DEBUG,
        # в этом примере в консоль будут выводиться логи уровня DEBUG и выше, а в Graylog - INFO и выше
        graylog_level: int = logging.INFO
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(FORMAT, datefmt=DATEFMT)

    con = logging.StreamHandler()
    con.setLevel(console_level)
    con.setFormatter(formatter)
    logger.addHandler(con)

    glog = GELFUDPHandler(graylog_host, graylog_port, localname=name)
    glog.setLevel(graylog_level)
    glog.setFormatter(formatter)
    logger.addHandler(glog)

    logger.propagate = False
    return logger


LOG = setup_logger("checkpoint-user-reset", graylog_host="graylog-pcidss.sovcombank.group", graylog_port=14427)