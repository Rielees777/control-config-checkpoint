# -*- coding: utf-8 -*-
"""
Ручной запуск проверки SSH-учетных записей одного Check Point шлюза
для тестирования с терминального сервера.

Переменные окружения берутся из .env в корне проекта (CHP_LOGIN,
CHP_PASSWORD, CHP_EXPERT, AD_LOGIN, AD_PASSWORD, AD_SSH_GROUP_NAME).

Использование:
    python tests/run_ssh_accounts_check.py <gateway_ip> [ad_group_name]

Если ad_group_name не передан, используется AD_SSH_GROUP_NAME из .env.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import settings
from services.checkpoint_ssh import CheckPointSSH
from services.ssh_accounts_parser import check_ssh_accounts_against_ad
from main import SSHAccountsCheckResult, build_pyrus_task_payload, get_hostname


def main():
    if len(sys.argv) < 2:
        print("Использование: python tests/run_ssh_accounts_check.py <gateway_ip> [ad_group_name]")
        sys.exit(1)

    gateway_ip = sys.argv[1]
    ad_group = sys.argv[2] if len(sys.argv) > 2 else settings.AD_SSH_GROUP_NAME

    if not ad_group:
        print("Не задана AD-группа: передайте вторым аргументом или заполните AD_SSH_GROUP_NAME в .env")
        sys.exit(1)

    print(f"Подключение к шлюзу {gateway_ip}...")
    with CheckPointSSH(gateway_ip) as chp:
        hostname = get_hostname(chp)
        comparison = check_ssh_accounts_against_ad(chp, ad_group)

    print(f"\nСовпадают с AD-группой '{ad_group}': {comparison['matched']}")
    print(f"Отсутствуют в AD-группе '{ad_group}': {comparison['not_in_ad']}")

    result = SSHAccountsCheckResult(
        host=hostname,
        gateway_ip=gateway_ip,
        matched=comparison["matched"],
        not_in_ad=comparison["not_in_ad"],
    )

    if result.not_in_ad:
        print(f"\nALERT: найдены лишние учетные записи, задача Pyrus будет создана из payload:")
        print(build_pyrus_task_payload(result))
    else:
        print("\nВсе именные учетные записи присутствуют в AD-группе, алерта нет.")


if __name__ == "__main__":
    main()
