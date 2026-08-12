import os
import re


def is_test_file_name(file_name):
    """Return whether a C# file name belongs to the dedicated test output."""
    if not isinstance(file_name, str):
        return False
    name = os.path.basename(file_name.strip().replace("\\", "/"))
    return bool(re.search(r"(?:test|tests)\.cs$", name, re.IGNORECASE))
