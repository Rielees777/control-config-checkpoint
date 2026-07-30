# -*- coding: utf-8 -*-
"""
Парсинг вывода команды `show interfaces all` на шлюзе Check Point и
сверка списка интерфейсов с эталонным набором.
"""
import re
from typing import List, Set

from services.checkpoint_ssh import CheckPointSSH

# Интерфейсы, которые должны присутствовать на каждом шлюзе
EXPECTED_INTERFACES: Set[str] = {"eth0", "eth1", "lo", "loop00"}

# Вывод "show interfaces all" - блок на каждый интерфейс вида:
#   Interface eth0
#       state on
#       ...
#   Statistics:
#       ...
# Имя интерфейса берем только из строки-заголовка блока "Interface <имя>",
# остальные строки (детали, статистика, эхо команды, лишние строки CLI)
# игнорируются - это исключает ложные срабатывания на посторонний текст.
_INTERFACE_HEADER_RE = re.compile(r"^Interface\s+(\S+)\s*$")


def parse_show_interfaces(raw_output: str) -> List[str]:
    """
    Парсит вывод команды `show interfaces all` шлюза Check Point - список
    имен интерфейсов, по одному на блок "Interface <имя>".

    Args:
        raw_output: сырой вывод команды `show interfaces all`
                    (может содержать эхо команды и приглашение CLI)

    Returns:
        Список имен интерфейсов
    """
    interfaces = []
    for line in raw_output.splitlines():
        match = _INTERFACE_HEADER_RE.match(line.strip())
        if match:
            interfaces.append(match.group(1))
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
    # "show interfaces all" - команда clish, а не Expert-режима (bash), в
    # который CheckPointSSH переходит сразу при подключении
    if chp.check_expert_mode():
        chp.exit_from_expert()

    raw_output = chp.send_show_command("show interfaces all")
    return compare_interfaces(parse_show_interfaces(raw_output))
