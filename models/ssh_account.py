# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class SSHAccount:
    """Одна строка из вывода команды `show users` шлюза Check Point."""
    user: str
    uid: str
    gid: str
    home_dir: str
    shell: str
    real_name: str
    privileges: str
