# -*- coding: utf-8 -*-
"""
Парсинг вывода команды `show aaa tacacs-servers list` на шлюзе Check
Point и сверка списка TACACS-серверов с эталонным набором.
"""
import re
from typing import List, Set

from services.checkpoint_ssh import CheckPointSSH

# TACACS-серверы, которые должны быть настроены на каждом шлюзе
EXPECTED_AAA_SERVERS: Set[str] = {"10.80.91.2", "10.80.91.3"}

_HEADER_RE = re.compile(r"^Priority\s+Server\s+Timeout", re.IGNORECASE)


def parse_show_aaa_tacacs_servers(raw_output: str) -> List[str]:
    """
    Парсит вывод команды `show aaa tacacs-servers list` шлюза Check Point.

    Args:
        raw_output: сырой вывод команды `show aaa tacacs-servers list`
                    (может содержать эхо команды и приглашение CLI)

    Returns:
        Список адресов TACACS-серверов
    """
    servers = []
    in_table = False

    for line in raw_output.splitlines():
        stripped = line.strip()

        if not stripped:
            if in_table:
                break
            continue

        if _HEADER_RE.match(stripped):
            in_table = True
            continue

        if not in_table:
            continue

        columns = stripped.split()
        if len(columns) < 3:
            # строка не похожа на строку таблицы (например, следующее приглашение CLI)
            break

        servers.append(columns[1])

    return servers


def compare_aaa_servers(servers: List[str]) -> dict:
    """
    Сравнивает список TACACS-серверов шлюза с эталонным набором
    EXPECTED_AAA_SERVERS.

    Returns:
        dict с ключами:
            "missing" - ожидаемые серверы, отсутствующие на шлюзе
            "unexpected" - серверы на шлюзе, которых не должно быть
    """
    actual = set(servers)
    return {
        "missing": sorted(EXPECTED_AAA_SERVERS - actual),
        "unexpected": sorted(actual - EXPECTED_AAA_SERVERS),
    }


def check_aaa_servers(chp: CheckPointSSH) -> dict:
    """
    Получает список TACACS-серверов шлюза и сверяет его с эталонным набором.

    Args:
        chp: активное подключение к шлюзу Check Point

    Returns:
        dict с ключами "missing" и "unexpected" (см. compare_aaa_servers)
    """
    # "show aaa tacacs-servers list" - команда clish, а не Expert-режима
    # (bash), в который CheckPointSSH переходит сразу при подключении
    if chp.check_expert_mode():
        chp.exit_from_expert()

    raw_output = chp.send_show_command("show aaa tacacs-servers list")
    return compare_aaa_servers(parse_show_aaa_tacacs_servers(raw_output))
