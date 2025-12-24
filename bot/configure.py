from tkinter import *
from tkinter import ttk
import json

from classes import Panel
from test import is_json_valid

screens = {
    "Exchanges": {
        "title": "Exchanges/Stocks",
        "subtitle": "Manage exchanges and respective stocks"
    },
    "Secrets": {
        "title": "Secrets",
        "subtitle": "View and Edit secrets"
    },
    "Tests": {
        "title": "Tests",
        "subtitle": "Run tests to see if the system is working fine or not"
    }
}




def load_default_config():
    with open("default.json", "r") as default_config_file:
        config = default_config_file.read()

    return config

def load_config():
    pass

def save_config():
    pass


try:
    panel = Panel()
    panel.setup(screens)
except Exception as e:
    print(e)
