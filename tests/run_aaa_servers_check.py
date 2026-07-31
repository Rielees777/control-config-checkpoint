# -*- coding: utf-8 -*-
"""
Ручной запуск проверки AAA TACACS-серверов Check Point шлюзов для
тестирования с терминального сервера.

Переменные окружения берутся из .env в корне проекта (CHP_LOGIN,
CHP_PASSWORD, CHP_EXPERT, NETBOX_URL, NETBOX_TOKEN, NETBOX_CERT).

Использование:
    python tests/run_aaa_servers_check.py
        Проверка всех шлюзов, полученных из NetBox (AAA-часть того, что
        делает run_ssh_accounts_check из main.py).

    python tests/run_aaa_servers_check.py <gateway_ip>
        Проверка одного шлюза.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List

from services.checkpoint_ssh import CheckPointSSH
from services.aaa_servers_parser import check_aaa_servers
from services.pyrus_task_builder import create_checkpoint_control_config_task
from main import (
    AaaServersCheckResult,
    build_pyrus_task_rows_aaa_servers,
    get_hostname,
    get_gateways_from_netbox,
    check_all_gateways_aaa_servers,
)


def print_result(result: AaaServersCheckResult) -> None:
    if result.error:
        print(f"\n{result.host} ({result.gateway_ip}): проверка не выполнена — {result.error}")
        return

    print(f"\n{result.host} ({result.gateway_ip})")
    print(f"  Отсутствуют ожидаемые TACACS-серверы: {result.missing}")
    print(f"  Обнаружены неожиданные TACACS-серверы: {result.unexpected}")

    if result.missing or result.unexpected:
        print("  ALERT: найдены расхождения в AAA-серверах")


def check_single_gateway(gateway_ip: str) -> List[AaaServersCheckResult]:
    print(f"Подключение к шлюзу {gateway_ip}...")
    with CheckPointSSH(gateway_ip) as chp:
        hostname = get_hostname(chp)
        comparison = check_aaa_servers(chp)

    result = AaaServersCheckResult(
        host=hostname,
        gateway_ip=gateway_ip,
        missing=comparison["missing"],
        unexpected=comparison["unexpected"],
    )
    print_result(result)
    return [result]


def check_all_gateways() -> List[AaaServersCheckResult]:
    gateway_ips = get_gateways_from_netbox()
    if not gateway_ips:
        print("Не удалось получить список шлюзов из NetBox")
        return []

    print(f"Получено {len(gateway_ips)} шлюзов из NetBox, проверка в потоках...")
    results = check_all_gateways_aaa_servers(gateway_ips)
    for result in results:
        print_result(result)
    return results


def main():
    gateway_ip = sys.argv[1] if len(sys.argv) > 1 else None

    if gateway_ip:
        results = check_single_gateway(gateway_ip)
    else:
        results = check_all_gateways()

    rows = build_pyrus_task_rows_aaa_servers(results)
    if rows:
        print(f"\nСоздание задачи Pyrus по {len(rows)} найденным расхождениям в AAA-серверах...")
        task_id = create_checkpoint_control_config_task(rows)
        print(f"Задача Pyrus создана: id={task_id}")
    else:
        print("\nРасхождений в AAA-серверах не найдено, задача Pyrus не создается.")


if __name__ == "__main__":
    main()
