# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class InterfacesCheckResult:
    """Результат сверки интерфейсов шлюза с эталонным набором."""
    host: str
    gateway_ip: str
    missing: List[str] = None
    unexpected: List[str] = None
    error: Optional[str] = None
