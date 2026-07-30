# -*- coding: utf-8 -*-
"""
Парсинг вывода команды `show interfaces` на шлюзе Check Point и сверка
списка интерфейсов с эталонным набором.
"""
import re
from typing import List, Set

from services.checkpoint_ssh import CheckPointSSH

# Интерфейсы, которые должны присутствовать на каждом шлюзе
EXPECTED_INTERFACES: Set[str] = {"eth0", "eth1", "lo", "loop00"}

_INTERFACE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def parse_show_interfaces(raw_output: str) -> List[str]:
    """
    Парсит вывод команды `show interfaces` шлюза Check Point - список
    имен интерфейсов, по одному на строку.

    Args:
        raw_output: сырой вывод команды `show interfaces`
                    (может содержать эхо команды и приглашение CLI)

    Returns:
        Список имен интерфейсов
    """
    interfaces = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        # эхо команды и приглашение CLI содержат пробелы/":"/">"/"#" и
        # отсекаются регэкспом, валидным именем остаются только строки
        # вида "eth0", "loop00" и т.п.
        if _INTERFACE_NAME_RE.match(stripped):
            interfaces.append(stripped)
    return interfaces


def compare_interfaces(interfaces: List[str]) -> dict:
    """
    Сравнивает список интерфейсов шлюза с эталонным набором EXPECTED_INTERFACES.

    Returns:
        dict с ключами:
            "missing" - ожидаемые интерфейсы, отсутствующие на шлюзе
            "unexpected" - интерфейсы на шлюзе, которых не должно быть
    """
    actual = set(interfaces)
    return {
        "missing": sorted(EXPECTED_INTERFACES - actual),
        "unexpected": sorted(actual - EXPECTED_INTERFACES),
    }


def check_interfaces(chp: CheckPointSSH) -> dict:
    """
    Получает список интерфейсов шлюза и сверяет его с эталонным набором.

    Args:
        chp: активное подключение к шлюзу Check Point

    Returns:
        dict с ключами "missing" и "unexpected" (см. compare_interfaces)
    """
    # "show interfaces" - команда clish, а не Expert-режима (bash), в
    # который CheckPointSSH переходит сразу при подключении
    if chp.check_expert_mode():
        chp.exit_from_expert()

    raw_output = chp.send_show_command("show interfaces")
    return compare_interfaces(parse_show_interfaces(raw_output))
