import json

# from main import default_config


def is_json_valid(json_string):
    """
    Checks if the input string is a valid JSON.
    Returns True if valid, False otherwise.
    """
    try:
        json.loads(json_string)
        print("default config json valid ✔")
    except json.decoder.JSONDecodeError:
        return False
    except TypeError:
        # Handles cases where the input is not a string, bytes or bytearray
        return False
    return True


