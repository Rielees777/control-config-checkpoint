# -*- coding: utf-8 -*-
"""
Парсинг вывода команды `show users` на шлюзе Check Point и сверка
именных учетных записей со списком пользователей AD-группы.
"""
import re
from dataclasses import dataclass
from typing import List, Set

from config.setup_logger import LOG
from services.checkpoint_ssh import CheckPointSSH
from services.ldap_handler import LDAPRadiusGroups

# Сервисные учетные записи, которые не участвуют в сверке с AD
SERVICE_ACCOUNTS: Set[str] = {
    "admin",
    "monitor",
    "n_netscaner",
}

_HEADER_RE = re.compile(r"^User\s+Uid\s+Gid\s+Home\s+Dir\.\s+Shell\s+Real\s+Name\s+Privileges", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s{2,}")


@dataclass
class SSHAccount:
    user: str
    uid: str
    gid: str
    home_dir: str
    shell: str
    real_name: str
    privileges: str


def is_service_account(username: str) -> bool:
    """
    Определяет, является ли учетная запись сервисной.
    Сервисные логины перечислены в SERVICE_ACCOUNTS, либо распознаются
    по признаку "svc" в имени (например hq-svc-devnet-rona).
    """
    login = username.strip().lower()
    return login in SERVICE_ACCOUNTS or "svc" in login


def parse_show_users(raw_output: str) -> List[SSHAccount]:
    """
    Парсит вывод команды `show users` шлюза Check Point.

    Args:
        raw_output: сырой вывод команды `show users`
                    (может содержать эхо команды и приглашение CLI)

    Returns:
        Список учетных записей SSHAccount
    """
    accounts: List[SSHAccount] = []
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

        columns = _SPLIT_RE.split(stripped)
        if len(columns) < 6:
            # строка не похожа на строку таблицы (например, следующее приглашение CLI)
            break

        user, uid, gid, home_dir, shell, *rest = columns
        real_name = rest[0] if rest else ""
        privileges = " ".join(rest[1:]) if len(rest) > 1 else ""

        accounts.append(
            SSHAccount(
                user=user,
                uid=uid,
                gid=gid,
                home_dir=home_dir,
                shell=shell,
                real_name=real_name,
                privileges=privileges,
            )
        )

    return accounts


def get_named_accounts(accounts: List[SSHAccount]) -> List[SSHAccount]:
    """Возвращает только именные (не сервисные) учетные записи."""
    return [acc for acc in accounts if not is_service_account(acc.user)]


def compare_with_ad(named_accounts: List[SSHAccount], ad_users: List[str]) -> dict:
    """
    Сравнивает именные учетные записи шлюза со списком пользователей из AD-группы.

    Args:
        named_accounts: именные учетные записи (результат get_named_accounts)
        ad_users: список sAMAccountName пользователей AD-группы

    Returns:
        dict с ключами:
            "matched" - логины, присутствующие и на шлюзе, и в AD-группе
            "not_in_ad" - логины на шлюзе, отсутствующие в AD-группе
                          (кандидаты на отзыв доступа)
    """
    ad_set = {u.strip().lower() for u in ad_users}
    matched = []
    not_in_ad = []

    for acc in named_accounts:
        if acc.user.strip().lower() in ad_set:
            matched.append(acc.user)
        else:
            not_in_ad.append(acc.user)

    LOG.info(
        "SSH accounts vs AD: matched=%d, not_in_ad=%d",
        len(matched), len(not_in_ad),
    )

    return {"matched": matched, "not_in_ad": not_in_ad}


def check_ssh_accounts_against_ad(
    chp: CheckPointSSH, ad_group: str, nested: bool = False
) -> dict:
    """
    Получает список SSH-учетных записей шлюза и сверяет именные учетные
    записи со списком пользователей указанной AD-группы.

    Args:
        chp: активное подключение к шлюзу Check Point
        ad_group: имя (CN) или DN группы AD
        nested: учитывать ли вложенное членство в группе

    Returns:
        dict с ключами "matched" и "not_in_ad" (см. compare_with_ad)
    """
    # "show users" - команда clish, а не Expert-режима (bash), в который
    # CheckPointSSH переходит сразу при подключении, поэтому перед
    # выполнением обязательно выходим из Expert-режима
    if chp.check_expert_mode():
        chp.exit_from_expert()

    raw_output = chp.send_show_command("show users")
    named_accounts = get_named_accounts(parse_show_users(raw_output))

    ad_users: List[str] = []
    ldap = LDAPRadiusGroups()
    if ldap.connect():
        try:
            ad_users = ldap.get_users_by_group(ad_group, nested=nested)
        finally:
            ldap.disconnect()
    else:
        LOG.error("Не удалось подключиться к AD, сверка учетных записей пропущена")

    return compare_with_ad(named_accounts, ad_users)
