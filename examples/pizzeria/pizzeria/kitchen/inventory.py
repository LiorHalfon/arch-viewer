"""What is left in the fridge."""

STOCK = {"dough": 40, "tomato": 30, "mozzarella": 30, "basil": 10, "pepperoni": 15, "mushrooms": 12}


def take(item: str) -> None:
    if STOCK.get(item, 0) == 0:
        raise LookupError(f"Out of {item}")
    STOCK[item] -= 1
