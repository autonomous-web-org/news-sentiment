import os
import json
import traceback
import pprint
from dotenv import load_dotenv

from classes import Panel
from test import is_json_valid, check_env



# configs ====================================================================================
load_dotenv()

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
        "subtitle": "Run tests to see if the APIs, Configs, etc. are working fine or not"
        # The UI working is not being tested here. Basically its like backend testing
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




# tests functionality ====================================================================================
def tests():
    tests_results = []

    tests_results.append("load_default_config -> " + is_json_valid(load_default_config()))
    tests_results.append("env variables -> " + check_env())

    return tests_results



# main loop starts ====================================================================================
try:
    screens["Tests"]["run_tests_callback"] = tests

    panel = Panel()
    panel.setup(screens)
except Exception as e:
    print(e)
    print(traceback.format_exc())
