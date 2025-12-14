from socket import socket
from socket import AF_INET
from socket import SOCK_DGRAM

def _get_local_ip():
    with socket(AF_INET, SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    
LOCAL_IP = _get_local_ip()