"""Send a driver out with the order."""

from pizzeria import notifications


def dispatch(address: str, phone: str) -> str:
    notifications.send(phone, "Your pizza is on its way")
    return f"A driver is heading to {address}"
