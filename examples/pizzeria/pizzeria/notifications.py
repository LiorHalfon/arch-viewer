"""Tell the customer what is happening to their order."""


def send(phone: str, message: str) -> str:
    return f"SMS to {phone}: {message}"
