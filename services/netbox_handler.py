import pynetbox
from config.setup_logger import LOG
from config.config import settings

class NetBoxHandler:
    """
    class for getting IP-addresses from NetBox.
    """
    def __init__(self) -> None:
        self.nd = pynetbox.api(settings.NETBOX_URL, token=settings.NETBOX_TOKEN, threading=True)
        self.nd.http_session.verify= settings.NETBOX_CERT
        self.tag_mapping = {
            'checkpoint': ['checkpoint', 'checkpoint-internal']
        }

    def get_ipaddresses(self, device_key: str, status='active') -> list:

        if device_key in self.tag_mapping:
            tags = self.tag_mapping[device_key]
            output = self.nd.ipam.ip_addresses.filter(tag=tags, status=status)
            return  [str(ip)[:-3] for ip in output]
        else:
            LOG.error("Netbox Error!")
            return []

