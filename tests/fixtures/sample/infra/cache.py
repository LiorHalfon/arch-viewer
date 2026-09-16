"""Dynamic import: must be reported as a warning, never silently dropped."""

import importlib


def get_rate() -> int:
    return 7


def load_routes():
    return importlib.import_module("sample.api.routes")
