from datetime import datetime
import json


class TaskParsed:
    def __init__(
            self,
            full_body: json
                ) -> None:
        self._full_body = full_body.get('task')

        self.pyrus_id: int = self._get_pyrus_id()
        self.is_closed: bool = self._get_status()
        self.create_date: datetime = self._get_create_date()
        self.close_date: datetime | None = self._get_close_date() if self.is_closed else None
        self._fields = self._get_fields()
        self._comments = self._get_comments()
        self._author = self._get_author()
        self.current_step: int = self._get_current_step()
        self._approvals = self._get_approvals()
        self._subscribers = self._get_subscribers()

    def _get_fields(self):
        return self._full_body.get('fields', {})

    def _get_comments(self):
        return self._full_body.get('comments', [])

    def _get_pyrus_id(self):
        return self._full_body.get('id')

    def _get_author(self):
        return self._full_body.get('author')

    def _get_status(self):
        return self._full_body.get('is_closed')

    def _get_create_date(self):
        return self._full_body.get('create_date')

    def _get_close_date(self):
        return self._full_body.get('close_date')

    def _get_current_step(self):
        return self._full_body.get('current_step')

    def _get_approvals(self):
        return self._full_body.get('approvals', [])

    def _get_subscribers(self):
        return self._full_body.get('subscribers', [])

    def __repr__(self):
        return (f'id: {self.pyrus_id}; '
                f'create_date: {self.create_date}; '
                f'is_closed: {self.is_closed}; '
                f'close_date: {self.close_date}; '
                f'current_step: {self.current_step}')

    def __str__(self):
        return self.__repr__()


class AccessLockForm(TaskParsed):
    def __init__(self, full_body: json):
        super().__init__(full_body)
        self.access_type = self.get_access_type()
        self.user_login = self.get_user_login()

    def _get_field(self):
        for field in self._get_fields():
            yield field

    def get_task_id(self):
        return self._get_pyrus_id()

    def get_access_type(self):
        for field in self._get_field():
            if field.get('id') == 5:
                value = field.get('value') or {}
                return value.get('choice_names') or []
        return [] 

    def get_user_login(self):
        for field in self._get_field():
            if field.get('id') == 3:
                return field.get('value') or {}
        return {}

    def get_user_login_if_access_ok(self):
        access_type = self.get_access_type() or []
        if "Заблокировать базовой набор" in access_type:
            return self.get_user_login()
        return None
    
    def get_bot_approve(self):
        return self._get_approvals()