# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SSHAccountsCheckResult:
    """Результат сверки SSH-учетных записей шлюза со списком пользователей AD."""
    host: str
    gateway_ip: str
    matched: List[str] = None
    not_in_ad: List[str] = None
    error: Optional[str] = None
