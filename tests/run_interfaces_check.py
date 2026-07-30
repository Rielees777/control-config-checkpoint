# -*- coding: utf-8 -*-
"""
Ручной запуск проверки интерфейсов Check Point шлюзов для тестирования
с терминального сервера.

Переменные окружения берутся из .env в корне проекта (CHP_LOGIN,
CHP_PASSWORD, CHP_EXPERT, NETBOX_URL, NETBOX_TOKEN, NETBOX_CERT).

Использование:
    python tests/run_interfaces_check.py
        Проверка всех шлюзов, полученных из NetBox (как в run_interfaces_check
        из main.py).

    python tests/run_interfaces_check.py <gateway_ip>
        Проверка одного шлюза.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List

from services.checkpoint_ssh import CheckPointSSH
from services.interfaces_parser import check_interfaces
from services.pyrus_task_builder import create_checkpoint_control_config_task
from main import (
    InterfacesCheckResult,
    build_pyrus_task_rows_interfaces,
    get_hostname,
    get_gateways_from_netbox,
    check_all_gateways_interfaces,
)


def print_result(result: InterfacesCheckResult) -> None:
    if result.error:
        print(f"\n{result.host} ({result.gateway_ip}): проверка не выполнена — {result.error}")
        return

    print(f"\n{result.host} ({result.gateway_ip})")
    print(f"  Отсутствуют ожидаемые интерфейсы: {result.missing}")
    print(f"  Обнаружены неожиданные интерфейсы: {result.unexpected}")

    if result.missing or result.unexpected:
        print("  ALERT: найдены расхождения в интерфейсах")


def check_single_gateway(gateway_ip: str) -> List[InterfacesCheckResult]:
    print(f"Подключение к шлюзу {gateway_ip}...")
    with CheckPointSSH(gateway_ip) as chp:
        hostname = get_hostname(chp)
        comparison = check_interfaces(chp)

    result = InterfacesCheckResult(
        host=hostname,
        gateway_ip=gateway_ip,
        missing=comparison["missing"],
        unexpected=comparison["unexpected"],
    )
    print_result(result)
    return [result]


def check_all_gateways() -> List[InterfacesCheckResult]:
    gateway_ips = get_gateways_from_netbox()
    if not gateway_ips:
        print("Не удалось получить список шлюзов из NetBox")
        return []

    print(f"Получено {len(gateway_ips)} шлюзов из NetBox, проверка в потоках...")
    results = check_all_gateways_interfaces(gateway_ips)
    for result in results:
        print_result(result)
    return results


def main():
    gateway_ip = sys.argv[1] if len(sys.argv) > 1 else None

    if gateway_ip:
        results = check_single_gateway(gateway_ip)
    else:
        results = check_all_gateways()

    rows = build_pyrus_task_rows_interfaces(results)
    if rows:
        print(f"\nСоздание задачи Pyrus по {len(rows)} найденным расхождениям в интерфейсах...")
        task_id = create_checkpoint_control_config_task(rows)
        print(f"Задача Pyrus создана: id={task_id}")
    else:
        print("\nРасхождений в интерфейсах не найдено, задача Pyrus не создается.")


if __name__ == "__main__":
    main()
