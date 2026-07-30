"""
Модуль для взаимодействия с API Pyrus
"""

import requests
import urllib3

from config.config import settings
from config.setup_logger import LOG
import json

requests.packages.urllib3.disable_warnings()

class PyrusClient:
    def __init__(self):
        self.base_url = 'https://pyrus.sovcombank.ru/api/v4'
        self.headers = {'Content-Type': 'application/json'}

    def _make_request(self, method, endpoint, token=None, data=None):
        url = f"{self.base_url}/{endpoint}"
        headers = self.headers.copy()
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=data,
                verify=False
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            LOG.error(f"Request error: {e}")
            raise

    def get_token(self):
        try:
            response = self._make_request(
                'POST',
                'auth',
                data={
                    "login": settings.PYRUS_LOGIN,
                    "security_key": settings.PYRUS_SECRET_KEY
                }
            )
            return response.json()['access_token']
        except (KeyError, json.JSONDecodeError) as e:
            LOG.error(f"Error parsing token response: {e}")
            raise

    def get_task(self, task_id):
        token = self.get_token()
        url = f'tasks/{str(task_id)}'
        response = self._make_request('GET', url, token=token)
        return response.json()

    def create_task(self, data: dict) -> dict:
        """
        Создает новую задачу в Pyrus по готовому телу запроса
        (form_id + fields, см. Pyrus API v4 POST /tasks).
        """
        token = self.get_token()
        try:
            response = self._make_request('POST', 'tasks', token=token, data=data)
            task_id = response.json().get('task', {}).get('id')
            LOG.info(f"Создана задача Pyrus, id={task_id}")
            return response.json()
        except Exception as e:
            LOG.error(f"Ошибка при создании задачи Pyrus: {e}")
            raise

    def add_comment(self, task_id, text):
        """Добавляет обычный комментарий к задаче."""
        token = self.get_token()
        endpoint = f'tasks/{task_id}/comments'
        data = {"text": text,
                 "approval_choice": "approved"
                 }

        try:
            response = self._make_request('POST', endpoint, token=token, data=data)
            LOG.info(f"Add comment for the task {task_id}")
            return response.status_code
        except Exception as e:
            LOG.error(f"Error when adding a comment to the task {task_id}: {e}")
            return -1

    def add_note(self, task_id, text, creds):
        """Добавляет приватную заметку к задаче."""
        token = self.get_token()
        endpoint = f'tasks/{task_id}/comments'
        data = {
            "formatted_text": f"<code>{text}<br></code>",
            "channel": {"type": "private_channel"}
        }

        try:
            response = self._make_request('POST', endpoint, token=token, data=data)
            LOG.info(f"Создана заметка в задачу {task_id}")
            return response.status_code
        except Exception as e:
            LOG.error(f"Ошибка при добавлении заметки в задачу {task_id}: {e}")
            return -1

    def add_comment_and_note_together(self, task_id, llm_diag, raw_diag, creds):
        """
        Создает и комментарий, и заметку в одной задаче.
        """
        comment_status = self.add_comment(task_id, llm_diag)
        note_status = self.add_note(task_id, raw_diag, creds)
        return (comment_status, note_status)

pyrus_client = PyrusClient()
