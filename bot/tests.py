import os
import json
import requests
from dotenv import load_dotenv


# from main import default_config

load_dotenv()


def is_json_valid(json_string):
    """
    Checks if the input string is a valid JSON.
    Returns True if valid, False otherwise.
    """
    try:
        json.loads(json_string)
        return "JSON valid ✔"
    except:
        return ("JSON invalid")
    return True


def check_env(variable="TEST", value="1"):
    if os.getenv(variable) == value:
        return "ENV variables loaded ✔"
    else:
        print(variable, value, os.getenv(variable))
        return ("ENVenv variables not loading")


def print_hierarchy(widget, depth=0):
    widget.update_idletasks()

    info = (f"{'  '*depth}{widget.winfo_class()} "
            f"w={widget.winfo_width()} h={widget.winfo_height()} "
            f"x={widget.winfo_x()} y={widget.winfo_y()} "
            f"path={str(widget)} name={widget.winfo_name()} parent={widget.winfo_parent()}")
    print(info)

    for child in widget.winfo_children():
        print_hierarchy(child, depth + 1)


def test_apis(api_name, api_config):
    if api_config["base_endpoint"] is None or api_config["api_key"] is None:
        return 0

    match api_name:
        case 'news_api':
            if api_config["enabled"] is False:
                return "Not enabled"
            params = {"apiKey": os.getenv(api_config["api_key"])}
            response = requests.get(api_config["base_endpoint"]+"/top-headlines/sources", params=params)
            data = response.json()

            if response.status_code == 200:
                return "It is working ✔"
        case _:
            return 0

    return 0