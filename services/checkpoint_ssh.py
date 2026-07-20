# -*- coding: utf-8 -*-
import paramiko
import time
import socket
from config.config import settings
from config.setup_logger import LOG


class CheckPointSSH:
    def __init__(self, ip):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ip = ip
        self._cfg = None
        client.connect(
            hostname=self.ip,
            username=settings.CHP_LOGIN,
            password=settings.CHP_PASSWORD,
        )
        self.ssh = client.invoke_shell()
        self.ssh.send('set clienv rows 0\n')
        self.ssh.send('expert\n')
        self.ssh.send(settings.CHP_EXPERT + '\n')
        time.sleep(1)
        self.ssh.recv(5000)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ssh.close()

    def send_show_command(self, command):
        self.ssh.send(command +'\n')
        self.ssh.settimeout(10)
        time.sleep(1)
        result = ""
        while True:
            try:
                part = self.ssh.recv(60000).decode('utf-8', 'ignore')
                result += part
                time.sleep(1)
            except socket.timeout:
                break
        return result

    def send_show_commands(self, commands):
        result = {}
        for command in commands:
            self.ssh.send(f"{command}\n")
            self.ssh.settimeout(5)
            output = ""

            while True:
                try:
                    part = self.ssh.recv(60000).decode('utf-8')
                    output += part
                    time.sleep(1)
                except socket.timeout:
                    break
            result[command] = output

        return result

    def disconnect(self):
        self.ssh.close()

    def get_prompt(self):
        self.ssh.send('\n')
        time.sleep(1)
        output = self.ssh.recv(5000).decode('ascii').split('\r\n')[-1]
        return output.strip()

    def exit_from_expert(self):
        prompt_str = self.get_prompt()
        if '#' in prompt_str:
            self.ssh.send('exit\n')
        else:
            return

    def expert_mode(self):
        if '>' in self.get_prompt():
            self.ssh.send('expert\n')
            self.ssh.send(settings.CHP_EXPERT + '\n')
            time.sleep(1)
        elif '#' in self.get_prompt():
            LOG.info('You already in expert mode!')
            return

    def check_expert_mode(self):
        if '#' in self.get_prompt():
            return True
        else:
            return False
    @property
    def cfg(self):
        if self.check_expert_mode():
            self.exit_from_expert()
            if not self._cfg:
                self._cfg = self.send_show_command('show configuration')
        else:
            self._cfg = self.send_show_command('show configuration')
        return self._cfg
