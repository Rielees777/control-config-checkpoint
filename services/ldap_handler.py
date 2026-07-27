# -*- coding: utf-8 -*-
from ldap3 import Server, Connection, SUBTREE

from config.setup_logger import LOG
from config.config import settings


class LDAPRadiusGroups:
    def __init__(
        self,
        server_url: str = "ldaps://svcldaphq.sovcombank.group",
        search_base: str = "DC=sovcombank,DC=group",
        port: int = 636,
    ):
        """
        Инициализация класса для работы с LDAP и получения radius-групп

        Args:
            server_url: URL LDAP сервера
            search_base: База поиска в LDAP
            port: Порт LDAP сервера
        """
        self.server_url = server_url
        self.search_base = search_base
        self.port = port
        self.server = None
        self.connection = None

    def connect(self) -> bool:
        """
        Установка соединения с LDAP сервером

        Returns:
            bool: True если подключение успешно, False в противном случае
        """
        try:
            LOG.debug("AD: Connecting | %s:%d", self.server_url, self.port)
            self.server = Server(
                self.server_url, port=self.port, get_info=None, connect_timeout=10
            )

            self.connection = Connection(
                self.server,
                user=settings.AD_LOGIN,
                password=settings.AD_PASSWORD,
                auto_bind=True,
                receive_timeout=30,
            )
            LOG.debug("AD: Connected |  %s:%d", self.server_url, self.port)
            return True
        except Exception as e:
            LOG.error(
                "AD: Error connecting | %s:%d | %s",
                self.server_url,
                self.port,
                e,
                exc_info=True,
            )
            return False

    def disconnect(self):
        """Закрытие соединения с LDAP сервером"""
        if self.connection:
            try:
                self.connection.unbind()
                LOG.debug("AD: disconnected | %s:%d", self.server_url, self.port)
            except Exception as e:
                LOG.error(
                    "AD: Error disconnecting | %s:%d | %s",
                    self.server_url,
                    self.port,
                    e,
                    exc_info=True,
                )
            finally:
                self.connection = None

    def get_users_by_group(self, group_name: str, nested: bool = False) -> list[dict]:
        """
        Получение списка пользователей, входящих в указанную группу

        Args:
            group_name: Имя группы (CN) или полный DN группы
            nested: Учитывать ли вложенные группы (рекурсивное членство).
                    Использует LDAP_MATCHING_RULE_IN_CHAIN, работает только с AD.

        Returns:
            list[dict]: Список словарей с данными пользователей
                        (sAMAccountName, distinguishedName, mail, displayName)
        """
        if not self.connection:
            LOG.error("AD: No active connection. Call connect() first.")
            return []

        # Определяем DN группы
        if group_name.lower().startswith("cn="):
            group_dn = group_name
        else:
            try:
                self.connection.search(
                    search_base=self.search_base,
                    search_filter=f"(&(objectClass=group)(cn={group_name}))",
                    search_scope=SUBTREE,
                    attributes=["distinguishedName"],
                )
                if not self.connection.entries:
                    LOG.error("AD: Group not found | %s", group_name)
                    return []
                group_dn = str(self.connection.entries[0].distinguishedName)
            except Exception as e:
                LOG.error("AD: Error searching group | %s | %s", group_name, e, exc_info=True)
                return []

        # Формируем фильтр поиска пользователей
        if nested:
            member_filter = (
                f"(memberOf:1.2.840.113556.1.4.1941:={group_dn})"
            )
        else:
            member_filter = f"(memberOf={group_dn})"

        search_filter = f"(&(objectClass=user)(objectCategory=person){member_filter})"

        users = []
        try:
            entries_generator = self.connection.extend.standard.paged_search(
                search_base=self.search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=[
                    "sAMAccountName",
                    "distinguishedName",
                    "mail",
                    "displayName",
                ],
                paged_size=500,
                generator=True,
            )

            for entry in entries_generator:
                if entry.get("type") != "searchResEntry":
                    continue
                attrs = entry.get("attributes", {})
                users.append(attrs.get("sAMAccountName")[0])

            LOG.debug(
                "AD: Found %d users in group %s (nested=%s)",
                len(users), group_dn, nested,
            )
            return users

        except Exception as e:
            LOG.error(
                "AD: Error searching users in group | %s | %s",
                group_dn, e, exc_info=True,
            )
            return []
