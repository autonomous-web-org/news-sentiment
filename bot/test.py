import json

# from main import default_config


def is_json_valid(json_string):
    """
    Checks if the input string is a valid JSON.
    Returns True if valid, False otherwise.
    """
    try:
        json.loads(json_string)
        return "default config json valid ✔"
    except json.decoder.JSONDecodeError:
        return False
    except TypeError:
        return False
    return True


