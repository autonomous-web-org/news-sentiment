import os
import json
import pprint
import traceback
from PyQt6.QtWidgets import (
    QApplication,
)

from classes1 import Panel
from tests import is_json_valid, check_env, test_apis



# configs ====================================================================================

screens = {
    "Exchanges": {
        "title": "Exchanges/Stocks",
        "subtitle": "Manage exchanges and respective stocks"
    },
    "APIs": {
        "title": "API management",
        "subtitle": "View and Edit APIs"
    },
    "Tests": {
        "title": "Tests",
        "subtitle": "Run tests to see if the APIs, Configs, etc. are working fine or not"
        # The UI working is not being tested here. Basically its like backend testing
    }
}


def load_config(filename="original_config.json"):
    to_open = "default.json" # load default
    if os.path.isfile(filename) and os.path.getsize(filename) != 0:
        to_open = filename

    with open(to_open, "r") as config_file:
        config = config_file.read()

    return to_open, config


def save_config(filename="original_config.json", complete_config: str=None):
    if complete_config is None:
        return

    with open(filename, "w") as config_file:
        config_file.write(complete_config)


def save_env(key, value):
    if key is None or value is None:
        return

    with open(filename, "w") as config_file:
        config_file.write(complete_config)



# tests functionality ====================================================================================
def run_tests():
    tests_results = []

    filename, config = load_config()
    # tests_results.append( f"config_integrity_and_loading ({filename}) -> " + is_json_valid(config) )
    tests_results.append( "env_variables_loading -> " + check_env() )

    config = json.loads(config)
    for api_name, api_config in config["apis"].items():
        res = test_apis(api_name, api_config)
        if res:
            tests_results.append(f"{api_name} -> {res}")
        else:
            tests_results.append(f"{api_name} -> Either the test function is not set or its not working")

    return tests_results



# main loop starts ====================================================================================
try:
    screens["Tests"]["run_tests_callback"] = run_tests

    filename, config = load_config()

    app = QApplication([])
    panel = Panel(screens=screens, config=json.loads(config), save_config=save_config, save_env=save_env)
    panel.setup()
    panel.window.show()
    app.exec()
except Exception as e:
    print(e)
    print(traceback.format_exc())
