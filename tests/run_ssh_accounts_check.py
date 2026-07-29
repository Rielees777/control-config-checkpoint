# -*- coding: utf-8 -*-
"""
Ручной запуск проверки SSH-учетных записей Check Point шлюзов
для тестирования с терминального сервера.

Переменные окружения берутся из .env в корне проекта (CHP_LOGIN,
CHP_PASSWORD, CHP_EXPERT, AD_LOGIN, AD_PASSWORD, AD_SSH_GROUP_NAME,
NETBOX_URL, NETBOX_TOKEN, NETBOX_CERT).

Использование:
    python tests/run_ssh_accounts_check.py
        Проверка всех шлюзов, полученных из NetBox (как в run_ssh_accounts_check
        из main.py), AD-группа берется из AD_SSH_GROUP_NAME в .env.

    python tests/run_ssh_accounts_check.py <gateway_ip> [ad_group_name]
        Проверка одного шлюза. Если ad_group_name не передан, используется
        AD_SSH_GROUP_NAME из .env.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import settings
from services.checkpoint_ssh import CheckPointSSH
from services.ssh_accounts_parser import check_ssh_accounts_against_ad
from main import (
    SSHAccountsCheckResult,
    build_pyrus_task_payload,
    get_hostname,
    get_gateways_from_netbox,
    check_gateway_ssh_accounts,
)


def print_result(result: SSHAccountsCheckResult, ad_group: str) -> None:
    if result.error:
        print(f"\n{result.host} ({result.gateway_ip}): проверка не выполнена — {result.error}")
        return

    print(f"\n{result.host} ({result.gateway_ip})")
    print(f"  Совпадают с AD-группой '{ad_group}': {result.matched}")
    print(f"  Отсутствуют в AD-группе '{ad_group}': {result.not_in_ad}")

    if result.not_in_ad:
        print("  ALERT: найдены лишние учетные записи, задача Pyrus будет создана из payload:")
        print(f"  {build_pyrus_task_payload(result)}")


def check_single_gateway(gateway_ip: str, ad_group: str) -> None:
    print(f"Подключение к шлюзу {gateway_ip}...")
    with CheckPointSSH(gateway_ip) as chp:
        hostname = get_hostname(chp)
        comparison = check_ssh_accounts_against_ad(chp, ad_group)

    result = SSHAccountsCheckResult(
        host=hostname,
        gateway_ip=gateway_ip,
        matched=comparison["matched"],
        not_in_ad=comparison["not_in_ad"],
    )
    print_result(result, ad_group)


def check_all_gateways(ad_group: str) -> None:
    gateway_ips = get_gateways_from_netbox()
    if not gateway_ips:
        print("Не удалось получить список шлюзов из NetBox")
        return

    print(f"Получено {len(gateway_ips)} шлюзов из NetBox")
    for gateway_ip in gateway_ips:
        result = check_gateway_ssh_accounts(gateway_ip)
        print_result(result, ad_group)


def main():
    gateway_ip = sys.argv[1] if len(sys.argv) > 1 else None
    ad_group_override = sys.argv[2] if len(sys.argv) > 2 else None

    if gateway_ip:
        ad_group = ad_group_override or settings.AD_SSH_GROUP_NAME
        if not ad_group:
            print("Не задана AD-группа: передайте вторым аргументом или заполните AD_SSH_GROUP_NAME в .env")
            sys.exit(1)
        check_single_gateway(gateway_ip, ad_group)
    else:
        if not settings.AD_SSH_GROUP_NAME:
            print("Не задана AD_SSH_GROUP_NAME в .env")
            sys.exit(1)
        check_all_gateways(settings.AD_SSH_GROUP_NAME)


if __name__ == "__main__":
    main()
