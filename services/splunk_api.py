# -*- coding: utf-8 -*-
"""
Модуль для отправки событий в Splunk через HTTP Event Collector (HEC).
"""

import json
import requests
import threading
from typing import List, Dict, Any

from config.setup_logger import LOG


class SplunkHEC:
    """
    Класс для отправки событий в Splunk через HTTP Event Collector (HEC).
    
    HEC (HTTP Event Collector) - это способ отправки данных напрямую
    в Splunk через HTTP/HTTPS протокол с аутентификацией по токену.
    
    Атрибуты класса:
        sent_counter (int): Общий счетчик всех отправленных событий (общий для всех экземпляров).
        _lock (threading.Lock): Блокировка для потокобезопасной работы со счетчиком.
    """
    
    sent_counter = 0  
    _lock = threading.Lock()

    def __init__(self, url: str, token: str, port: int, index: str = "itctrl") -> None:
        """
        Инициализация объекта HEC.
        
        Параметры:
            url (str): URL-адрес хоста Splunk (без протокола).
            token (str): Токен аутентификации HEC.
            port (int): Порт для подключения к Splunk HEC.
            index (str): Индекс Splunk для записи событий (по умолчанию "itctrl").
        
        Пример:
            hec = SplunkHEC("splunk.example.com", "your-hec-token", 8088)
        """
        self.url = f"https://{url}:{port}"
        self.hec_endpoint = f"{self.url}/services/collector/event"
        self.token = token
        self.port = port
        self.index = index

    def send(self, event: Dict[str, Any], source: str = "control-config-checkpoint") -> requests.Response:
        """
        Отправляет событие в Splunk через HEC.
        
        Параметры:
            event: Данные события для отправки (любой сериализуемый в JSON формат).
            source: Источник события (по умолчанию "control-config-checkpoint").
        
        Возвращает:
            requests.Response: Объект ответа от Splunk HEC.
        
        Особенности:
            - Использует токен аутентификации типа "Splunk <token>"
            - Событие отправляется в указанный индекс
            - verify=False отключает проверку SSL-сертификатов
        """
        headers = {"Authorization": "Splunk " + self.token}
        payload = {
            "index": self.index,
            "source": source,
            "event": event
        }

        try:
            r = requests.post(
                self.hec_endpoint, 
                data=json.dumps(payload), 
                headers=headers, 
                verify="/usr/local/share/ca-certificates/splunk.crt"
            )
            
            with self._lock:
                SplunkHEC.sent_counter += 1
            
            return r
        except requests.exceptions.RequestException as e:
            LOG.error(f"Ошибка при отправке в Splunk: {e}")
            raise

    def send_batch(self, events: List[Dict[str, Any]], source: str = "control-config-checkpoint") -> List[requests.Response]:
        """
        Отправляет несколько событий в Splunk.
        
        Параметры:
            events: Список событий для отправки.
            source: Источник события (по умолчанию "control-config-checkpoint").
        
        Возвращает:
            List[requests.Response]: Список объектов ответа от Splunk HEC.
        """
        responses = []
        for event in events:
            try:
                response = self.send(event, source)
                responses.append(response)
            except requests.exceptions.RequestException as e:
                LOG.error(f"Ошибка при отправке события в Splunk: {e}")
                responses.append(None)
        
        return responses