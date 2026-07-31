# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Optional


@dataclass
class CheckResult:
    """Результат проверки конфигурации шлюза."""
    host: str
    gateway_ip: str
    has_any_host: bool
    error: Optional[str] = None
