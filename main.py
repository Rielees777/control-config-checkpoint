# -*- coding: utf-8 -*-
"""
Модуль для проверки конфигурации Check Point шлюзов.
Проверяет наличие строки "add allowed-client host any-host" в конфигурации.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.checkpoint_ssh import CheckPointSSH
from services.netbox_handler import NetBoxHandler
from config.setup_logger import LOG


@dataclass
class CheckResult:
    """Результат проверки конфигурации шлюза."""
    gateway_ip: str
    has_any_host: bool
    config_snippet: Optional[str] = None
    error: Optional[str] = None


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
            config = chp.cfg
            LOG.info(f"Получена конфигурация с {gateway_ip}, длина: {len(config)} символов")
            
            # Ищем строку "add allowed-client host any-host" в конфигурации
            search_string = "add allowed-client host any-host"
            has_any_host = search_string in config
            
            # Если строка найдена, извлекаем контекст (несколько строк до и после)
            config_snippet = None
            if has_any_host:
                lines = config.split('\n')
                for i, line in enumerate(lines):
                    if search_string in line:
                        # Берем 3 строки до и 3 после найденной строки
                        start = max(0, i - 3)
                        end = min(len(lines), i + 4)
                        context_lines = lines[start:end]
                        config_snippet = '\n'.join(context_lines)
                        LOG.info(f"Найдена строка '{search_string}' в конфигурации {gateway_ip}")
                        break
            
            return CheckResult(
                gateway_ip=gateway_ip,
                has_any_host=has_any_host,
                config_snippet=config_snippet
            )
            
    except Exception as e:
        LOG.error(f"Ошибка при подключении к {gateway_ip}: {e}")
        return CheckResult(
            gateway_ip=gateway_ip,
            has_any_host=False,
            error=str(e)
        )


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
                    gateway_ip=ip,
                    has_any_host=False,
                    error=str(e)
                ))
    
    return results


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


def generate_report(results: List[CheckResult]) -> str:
    """
    Генерирует текстовый отчет по результатам проверки.
    
    Args:
        results: Список результатов проверки
        
    Returns:
        Строка с отчетом
    """
    report_lines = ["=" * 60, "ОТЧЕТ ПО ПРОВЕРКЕ КОНФИГУРАЦИИ CHECK POINT", "=" * 60, ""]
    
    gateways_with_any_host = [r for r in results if r.has_any_host]
    gateways_without_any_host = [r for r in results if not r.has_any_host and not r.error]
    gateways_with_errors = [r for r in results if r.error]
    
    report_lines.append(f"Всего проверено шлюзов: {len(results)}")
    report_lines.append(f"Строка 'add allowed-client host any-host' НАЙДЕНА: {len(gateways_with_any_host)}")
    report_lines.append(f"Строка НЕ найдена: {len(gateways_without_any_host)}")
    report_lines.append(f"Ошибки подключения: {len(gateways_with_errors)}")
    report_lines.append("")
    
    if gateways_with_any_host:
        report_lines.append("-" * 60)
        report_lines.append("ШЛЮЗЫ С 'add allowed-client host any-host':")
        report_lines.append("-" * 60)
        for r in gateways_with_any_host:
            report_lines.append(f"\n[+] {r.gateway_ip}")
            if r.config_snippet:
                report_lines.append("  Контекст:")
                for line in r.config_snippet.split('\n'):
                    report_lines.append(f"    {line}")
    
    if gateways_without_any_host:
        report_lines.append("")
        report_lines.append("-" * 60)
        report_lines.append("ШЛЮЗЫ БЕЗ 'add allowed-client host any-host':")
        report_lines.append("-" * 60)
        for r in gateways_without_any_host:
            report_lines.append(f"[-] {r.gateway_ip}")
    
    if gateways_with_errors:
        report_lines.append("")
        report_lines.append("-" * 60)
        report_lines.append("ОШИБКИ ПОДКЛЮЧЕНИЯ:")
        report_lines.append("-" * 60)
        for r in gateways_with_errors:
            report_lines.append(f"[!] {r.gateway_ip}: {r.error}")
    
    report_lines.append("")
    report_lines.append("=" * 60)
    
    return '\n'.join(report_lines)


def main():
    """
    Основная функция для запуска проверки конфигурации Check Point шлюзов.
    """
    LOG.info("Запуск проверки конфигурации Check Point шлюзов")
    
    # Получаем список шлюзов из NetBox
    gateway_ips = get_gateways_from_netbox()
    
    if not gateway_ips:
        LOG.warning("Не удалось получить список шлюзов из NetBox")
        return
    
    # Проверяем конфигурацию всех шлюзов
    results = check_all_gateways(gateway_ips)
    
    # Генерируем и выводим отчет
    report = generate_report(results)
    print(report)
    
    LOG.info("Проверка конфигурации завершена")


if __name__ == "__main__":
    main()