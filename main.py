# -*- coding: utf-8 -*-
"""
Модуль для проверки конфигурации Check Point шлюзов.
Проверяет наличие строки "add allowed-client host any-host" в конфигурации.
Вывод данных в формате JSON для Splunk.
"""

import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import schedule

from services.checkpoint_ssh import CheckPointSSH
from services.netbox_handler import NetBoxHandler
from services.splunk_api import SplunkHEC
from services.ssh_accounts_parser import check_ssh_accounts_against_ad
from services.pyrus_task_builder import create_checkpoint_ssh_accounts_task
from config.config import settings, splunk_creds
from config.setup_logger import LOG


CHECK_NAME = "allowed-client-any-host"
SEARCH_STRING = "add allowed-client host any-host"

# Настройки расписания (время в UTC)
SCHEDULE_TIME = "09:00"  # Изменить на нужное время в формате HH:MM

# Проверка SSH-учетных записей запускается по отдельному расписанию,
# т.к. результат уходит не в Splunk, а в Pyrus (отдельной задачей)
SSH_ACCOUNTS_SCHEDULE_TIME = "10:00"  # Изменить на нужное время в формате HH:MM


@dataclass
class CheckResult:
    """Результат проверки конфигурации шлюза."""
    host: str
    gateway_ip: str
    has_any_host: bool
    error: Optional[str] = None


@dataclass
class SSHAccountsCheckResult:
    """Результат сверки SSH-учетных записей шлюза со списком пользователей AD."""
    host: str
    gateway_ip: str
    matched: List[str] = None
    not_in_ad: List[str] = None
    error: Optional[str] = None


def get_hostname(chp: CheckPointSSH) -> str:
    """
    Получает hostname шлюза Check Point.
    
    Args:
        chp: Объект подключения к шлюзу
        
    Returns:
        Имя хоста шлюза
    """
    try:
        # Выполняем команду hostname
        output = chp.send_show_command("hostname")
        # Извлекаем hostname из вывода
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        for line in lines:
            # Пропускаем строки с командными символами
            if line.startswith('>') or line.startswith('#'):
                continue
            # Пропускаем служебные сообщения
            if 'Warning' in line or 'warning' in line:
                continue
            if 'configuration' in line.lower():
                continue
            if 'expert' in line.lower():
                continue
            if 'You are in' in line:
                continue
            if 'Enter' in line:
                continue
            # Ищем строку, которая похожа на hostname (не содержит пробелов)
            if line and ' ' not in line and '\t' not in line:
                return line.strip()
        
        # Если не удалось определить из вывода команды, пробуем извлечь из приглашения
        for line in output.split('\n'):
            # Ищем формат [Expert@hostname или hostname:TACP
            if '@' in line:
                parts = line.split('@')
                if len(parts) > 1:
                    hostname_part = parts[1].split()[0] if parts[1].strip() else None
                    if hostname_part and ':' in hostname_part:
                        hostname_part = hostname_part.split(':')[0]
                    if hostname_part:
                        return hostname_part.strip()
            elif ':TACP' in line or ':0]' in line:
                hostname = line.split(':')[0].strip()
                if hostname and not hostname.startswith('#') and not hostname.startswith('>'):
                    return hostname
        
        # Если не удалось определить, возвращаем IP
        LOG.warning(f"Не удалось определить hostname из вывода, используем IP: {chp.ip}")
        return chp.ip
    except Exception as e:
        LOG.warning(f"Не удалось получить hostname для {chp.ip}: {e}")
        return chp.ip


def check_gateway_config(gateway_ip: str) -> CheckResult:
    """
    Подключается к Check Point шлюзу и проверяет конфигурацию.
    
    Args:
        gateway_ip: IP-адрес шлюза Check Point
        
    Returns:
        CheckResult с результатами проверки
    """
    try:
        with CheckPointSSH(gateway_ip) as chp:
            # Получаем hostname шлюза
            hostname = get_hostname(chp)
            LOG.info(f"Подключение к шлюзу {hostname} ({gateway_ip})")
            
            # Получаем конфигурацию
            config = chp.cfg
            LOG.info(f"Получена конфигурация с {hostname}, длина: {len(config)} символов")
            
            # Проверяем наличие строки в конфигурации
            has_any_host = SEARCH_STRING in config
            
            if has_any_host:
                LOG.info(f"Строка '{SEARCH_STRING}' найдена в конфигурации {hostname}")
            else:
                LOG.info(f"Строка '{SEARCH_STRING}' НЕ найдена в конфигурации {hostname}")
            
            return CheckResult(
                host=hostname,
                gateway_ip=gateway_ip,
                has_any_host=has_any_host
            )
            
    except Exception as e:
        LOG.error(f"Ошибка при подключении к {gateway_ip}: {e}")
        return CheckResult(
            host=gateway_ip,
            gateway_ip=gateway_ip,
            has_any_host=False,
            error=str(e)
        )


def get_gateways_from_netbox(device_key: str = 'checkpoint') -> List[str]:
    """
    Получает список IP-адресов шлюзов из NetBox.
    
    Args:
        device_key: Ключ для поиска устройств в NetBox (по умолчанию 'checkpoint')
        
    Returns:
        Список IP-адресов шлюзов
    """
    try:
        netbox = NetBoxHandler()
        ips = netbox.get_ipaddresses(device_key)
        LOG.info(f"Получено {len(ips)} IP-адресов из NetBox")
        return ips
    except Exception as e:
        LOG.error(f"Ошибка при получении IP-адресов из NetBox: {e}")
        return []


def check_all_gateways(gateway_ips: List[str], max_workers: int = 10) -> List[CheckResult]:
    """
    Проверяет конфигурацию всех указанных шлюзов с использованием потоков.
    
    Args:
        gateway_ips: Список IP-адресов шлюзов для проверки
        max_workers: Максимальное количество одновременных потоков (по умолчанию 10)
        
    Returns:
        Список результатов проверки для каждого шлюза
    """
    results: List[CheckResult] = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Создаем future для каждого шлюза
        future_to_ip = {
            executor.submit(check_gateway_config, ip): ip
            for ip in gateway_ips
        }
        
        # Собираем результаты по мере их выполнения
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                result = future.result()
                results.append(result)
                status = "OK" if result.has_any_host else "NOT FOUND"
                LOG.info(f"Завершена проверка шлюза {ip}: {status}")
            except Exception as e:
                LOG.error(f"Ошибка при проверке шлюза {ip}: {e}")
                results.append(CheckResult(
                    host=ip,
                    gateway_ip=ip,
                    has_any_host=False,
                    error=str(e)
                ))
    
    return results


def check_gateway_ssh_accounts(gateway_ip: str) -> SSHAccountsCheckResult:
    """
    Подключается к Check Point шлюзу и сверяет его именные SSH-учетные
    записи со списком пользователей AD-группы.

    Args:
        gateway_ip: IP-адрес шлюза Check Point

    Returns:
        SSHAccountsCheckResult с результатами сверки
    """
    if not settings.AD_SSH_GROUP_NAME:
        LOG.warning("AD_SSH_GROUP_NAME не задан, проверка SSH-учетных записей пропущена")
        return SSHAccountsCheckResult(
            host=gateway_ip,
            gateway_ip=gateway_ip,
            error="AD_SSH_GROUP_NAME не задан",
        )

    try:
        with CheckPointSSH(gateway_ip) as chp:
            hostname = get_hostname(chp)
            LOG.info(f"Проверка SSH-учетных записей шлюза {hostname} ({gateway_ip})")

            comparison = check_ssh_accounts_against_ad(chp, settings.AD_SSH_GROUP_NAME)

            return SSHAccountsCheckResult(
                host=hostname,
                gateway_ip=gateway_ip,
                matched=comparison["matched"],
                not_in_ad=comparison["not_in_ad"],
            )
    except Exception as e:
        LOG.error(f"Ошибка при проверке SSH-учетных записей {gateway_ip}: {e}")
        return SSHAccountsCheckResult(
            host=gateway_ip,
            gateway_ip=gateway_ip,
            error=str(e),
        )


def check_all_gateways_ssh_accounts(
    gateway_ips: List[str], max_workers: int = 10
) -> List[SSHAccountsCheckResult]:
    """
    Проверяет SSH-учетные записи всех указанных шлюзов с использованием потоков.

    Args:
        gateway_ips: Список IP-адресов шлюзов для проверки
        max_workers: Максимальное количество одновременных потоков (по умолчанию 10)

    Returns:
        Список результатов проверки для каждого шлюза
    """
    results: List[SSHAccountsCheckResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {
            executor.submit(check_gateway_ssh_accounts, ip): ip
            for ip in gateway_ips
        }

        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                results.append(future.result())
            except Exception as e:
                LOG.error(f"Ошибка при проверке SSH-учетных записей {ip}: {e}")
                results.append(SSHAccountsCheckResult(host=ip, gateway_ip=ip, error=str(e)))

    return results


def build_pyrus_task_payload(result: SSHAccountsCheckResult) -> Dict:
    """
    Формирует данные будущей задачи Pyrus по найденным лишним SSH-учетным
    записям (именные учетки на шлюзе, которых нет в AD-группе и нет в
    исключениях). Возвращает только сырые данные, без вызова Pyrus API.
    """
    return {
        "host": result.host,
        "gateway_ip": result.gateway_ip,
        "ad_group": settings.AD_SSH_GROUP_NAME,
        "extra_accounts": result.not_in_ad,
    }


def build_pyrus_task_rows(results: List[SSHAccountsCheckResult]) -> List[Dict]:
    """
    Формирует строки будущей задачи Pyrus (Host/IP/Trouble) по всем
    найденным за прогон лишним SSH-учетным записям, см.
    templates/checkpoint_ssh_accounts_task.j2.
    """
    rows = []
    for result in results:
        if result.error or not result.not_in_ad:
            continue
        for account in result.not_in_ad:
            rows.append({
                "host": result.host,
                "ip": result.gateway_ip,
                "trouble": (
                    f"Учетная запись {account} отсутствует в AD-группе "
                    f"'{settings.AD_SSH_GROUP_NAME}' и не входит в исключения"
                ),
            })
    return rows


def handle_ssh_accounts_results(results: List[SSHAccountsCheckResult]) -> None:
    """
    Обрабатывает результаты сверки SSH-учетных записей: логирует ALERT по
    каждому шлюзу с лишними учетками и создает одну задачу Pyrus на весь
    прогон со всеми найденными проблемами (форма 459137, "ОСУДиИ" ->
    "Checkpoint Control Config").
    """
    for result in results:
        if result.error:
            LOG.warning(f"{result.host}: проверка SSH-учетных записей не выполнена — {result.error}")
            continue

        if result.not_in_ad:
            LOG.error(
                f"ALERT: {result.host} ({result.gateway_ip}) — найдены SSH-учетные записи, "
                f"отсутствующие в AD-группе '{settings.AD_SSH_GROUP_NAME}' и не входящие "
                f"в исключения (SERVICE_ACCOUNTS): {result.not_in_ad}"
            )
        else:
            LOG.info(f"{result.host}: все именные учетные записи присутствуют в AD-группе")

    rows = build_pyrus_task_rows(results)
    if rows:
        create_checkpoint_ssh_accounts_task(rows)


def run_ssh_accounts_check():
    """
    Выполняет сверку SSH-учетных записей Check Point шлюзов со списком
    пользователей AD-группы. Запускается по собственному расписанию,
    отдельно от проверки конфигурации (SCHEDULE_TIME).
    """
    LOG.info("Запуск проверки SSH-учетных записей Check Point шлюзов")

    gateway_ips = get_gateways_from_netbox()
    if not gateway_ips:
        LOG.warning("Не удалось получить список шлюзов из NetBox")
        return

    results = check_all_gateways_ssh_accounts(gateway_ips)
    handle_ssh_accounts_results(results)

    LOG.info("Проверка SSH-учетных записей завершена")


def generate_splunk_output(results: List[CheckResult]) -> List[Dict]:
    """
    Генерирует данные в формате для Splunk.
    
    Args:
        results: Список результатов проверки
        
    Returns:
        Список словарей для Splunk
    """
    output = []
    for result in results:
        # Определяем статус: ok если строка НЕ найдена, defect если найдена
        status = "defect" if result.has_any_host else "ok"
        
        entry = {
            "host": result.host,
            "check": CHECK_NAME,
            "status": status
        }
        output.append(entry)
    
    return output


def send_to_splunk(results: List[CheckResult]) -> bool:
    """
    Отправляет результаты проверки в Splunk.
    
    Args:
        results: Список результатов проверки
        
    Returns:
        True если отправка успешна, False в противном случае
    """
    try:
        splunk = SplunkHEC(**splunk_creds())
        splunk_data = generate_splunk_output(results)
        
        LOG.info(f"Начало отправки {len(splunk_data)} событий в Splunk")
        LOG.debug(f"Данные для отправки: {splunk_data}")
        
        success_count = 0
        error_count = 0
        
        for event in splunk_data:
            LOG.debug(f"Отправка события: {event}")
            response = splunk.send(event)
            
            if response:
                LOG.debug(f"Response status code: {response.status_code}")
                LOG.debug(f"Response headers: {response.headers}")
                LOG.debug(f"Response text: {response.text}")
                
                if response.status_code == 200:
                    LOG.info(f"Успешно отправлено в Splunk: host={event['host']}, status={event['status']}")
                    success_count += 1
                else:
                    LOG.error(f"Ошибка отправки в Splunk: host={event['host']}, status_code={response.status_code}, response={response.text}")
                    error_count += 1
            else:
                LOG.error(f"Ошибка отправки в Splunk: host={event['host']}, response=None (нет ответа от сервера)")
                error_count += 1
        
        LOG.info(f"Отправка в Splunk завершена. Успешно: {success_count}, Ошибок: {error_count}")
        return error_count == 0
        
    except Exception as e:
        LOG.error(f"Ошибка при отправке в Splunk: {e}")
        return False


def run_check():
    """
    Выполняет проверку конфигурации Check Point шлюзов.
    """
    LOG.info("Запуск проверки конфигурации Check Point шлюзов")
    
    # Получаем список шлюзов из NetBox
    gateway_ips = get_gateways_from_netbox()
    
    if not gateway_ips:
        LOG.warning("Не удалось получить список шлюзов из NetBox")
        return
    
    # Проверяем конфигурацию всех шлюзов
    results = check_all_gateways(gateway_ips)
    
    # Отправляем данные в Splunk
    send_to_splunk(results)
    
    LOG.info("Проверка конфигурации завершена")


def main():
    """
    Запускает планировщик для ежедневного выполнения проверки.
    Время запуска настраивается через переменную SCHEDULE_TIME.
    """
    # Настраиваем расписание
    schedule.every().day.at(SCHEDULE_TIME).do(run_check)
    schedule.every().day.at(SSH_ACCOUNTS_SCHEDULE_TIME).do(run_ssh_accounts_check)

    LOG.info(
        f"Планировщик запущен. Проверка конфигурации в {SCHEDULE_TIME} UTC, "
        f"проверка SSH-учетных записей в {SSH_ACCOUNTS_SCHEDULE_TIME} UTC"
    )
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем каждую минуту


if __name__ == "__main__":
    main()