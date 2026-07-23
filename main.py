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
from config.config import settings, splunk_creds
from config.setup_logger import LOG


CHECK_NAME = "allowed-client-any-host"
SEARCH_STRING = "add allowed-client host any-host"

# Настройки расписания (время в UTC)
SCHEDULE_TIME = "07:35"  # Изменить на нужное время в формате HH:MM


@dataclass
class CheckResult:
    """Результат проверки конфигурации шлюза."""
    host: str
    gateway_ip: str
    has_any_host: bool
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
    
    LOG.info(f"Планировщик запущен. Следующая проверка в {SCHEDULE_TIME} UTC")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем каждую минуту


if __name__ == "__main__":
    main()