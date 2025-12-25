import os
import json
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
        return "json valid ✔"
    except:
        return "json invalid"
    return True


def check_env(variable="TEST", value="1"):
    if os.getenv(variable) == value:
        return "env variables loaded ✔"
    else:
        print(variable, value, os.getenv(variable))
        return "env variables not loading"
