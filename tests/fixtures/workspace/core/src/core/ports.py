"""An internal, in-package dependency: ports depends on the model (M8 fixture)."""

from core.model import Thing


class Port:
    def hold(self, thing: Thing) -> None: ...
