"""Put the toppings on, as the recipe says."""

from pizzeria.kitchen import inventory
from pizzeria.kitchen.recipes import toppings_for
from pizzeria.kitchen.stations import oven
from pizzeria.kitchen.stations.sauce import spread
from pizzeria.menu.pizzas import Pizza

DELICATE = {"basil"}


def top(pizza: Pizza) -> list[str]:
    layers = spread()
    for item in toppings_for(pizza):
        if item in DELICATE and oven.TEMPERATURE > 400:
            continue  # it would burn: goes on after baking
        inventory.take(item)
        layers.append(item)
    return layers
