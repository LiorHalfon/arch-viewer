"""An order: the pizzas one customer wants."""

from dataclasses import dataclass, field

from pizzeria.menu.pizzas import Pizza


@dataclass
class Order:
    phone: str
    address: str
    pizzas: list[Pizza] = field(default_factory=list)

    def total(self) -> float:
        return sum(pizza.price for pizza in self.pizzas)
