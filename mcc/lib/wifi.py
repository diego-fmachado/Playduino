from network import WLAN
from machine import idle
from json import loads

def connect_network():
    sta_if = WLAN(WLAN.IF_STA)
    if not sta_if.isconnected():
        with open("env/env.json") as f:
            env = loads(f.read())
        wifi_ap = env["wifi_ap"]
        wifi_pass = env["wifi_pass"]
        print(f'Connecting Wi-Fi... ({wifi_ap}, {wifi_pass})')
        sta_if.active(True)
        sta_if.connect(wifi_ap, wifi_pass)
        sta_if.config(pm=sta_if.PM_NONE)
        while not sta_if.isconnected():
            idle()
        print('Wi-Fi connected! IP: ', get_ip_address())

def get_ip_address() -> str:
    return WLAN(WLAN.IF_STA).ipconfig("addr4")[0]
