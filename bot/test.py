import json

# from main import default_config


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


