"""A cross-package import (core, a sibling) plus a third-party one (M8 fixture).

`core.ports` is squashed by grimp to the external node `core`, whether or not `core`
is installed; `openai` is an ordinary external, not a sibling, and must not be
mistaken for one.
"""

from core.ports import Port
from openai import OpenAI


class Adapter:
    def __init__(self, port: Port, client: OpenAI) -> None:
        self.port = port
        self.client = client
