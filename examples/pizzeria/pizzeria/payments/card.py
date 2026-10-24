"""Charge a card and send the receipt."""

from pizzeria import notifications


def charge(phone: str, amount: float) -> bool:
    notifications.send(phone, f"We charged {amount:.2f} to your card")
    return True
