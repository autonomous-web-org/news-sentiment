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


def print_hierarchy(widget, depth=0):
    widget.update_idletasks()

    info = (f"{'  '*depth}{widget.winfo_class()} "
            f"w={widget.winfo_width()} h={widget.winfo_height()} "
            f"x={widget.winfo_x()} y={widget.winfo_y()} "
            f"path={str(widget)} name={widget.winfo_name()} parent={widget.winfo_parent()}")
    print(info)

    for child in widget.winfo_children():
        print_hierarchy(child, depth + 1)
