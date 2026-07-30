# -*- coding: utf-8 -*-
"""
Формирование и отправка задачи в Pyrus по найденным лишним SSH-учетным
записям на шлюзах Check Point.

Форма "УСС. Устранение неисправностей" (form_id=459137), ветка
Направление="ОСУДиИ" -> "ОСУДиИ Неисправности"="Checkpoint Control Config",
таблица "CheckPoint Control Config" с колонками Host/IP/Trouble.
"""
import json
import os
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from config.setup_logger import LOG
from services.pyrus_api import pyrus_client

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
_TEMPLATE_NAME = "checkpoint_ssh_accounts_task.j2"

_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))


def build_checkpoint_ssh_accounts_task_body(rows: List[Dict]) -> dict:
    """
    Рендерит шаблон templates/checkpoint_ssh_accounts_task.j2 строками вида
    {"host": ..., "ip": ..., "trouble": ...} и возвращает готовое тело
    запроса для Pyrus API (POST /tasks).
    """
    template = _env.get_template(_TEMPLATE_NAME)
    rendered = template.render(rows=rows)
    return json.loads(rendered)


def create_checkpoint_ssh_accounts_task(rows: List[Dict]) -> Optional[int]:
    """
    Создает задачу в Pyrus по найденным лишним SSH-учетным записям.

    Args:
        rows: список найденных проблем вида {"host", "ip", "trouble"}

    Returns:
        ID созданной задачи, либо None, если rows пуст
    """
    if not rows:
        return None

    body = build_checkpoint_ssh_accounts_task_body(rows)
    response = pyrus_client.create_task(body)
    task_id = response.get("task", {}).get("id")
    LOG.info(f"Создана задача Pyrus по лишним SSH-учетным записям Check Point: id={task_id}")
    return task_id
