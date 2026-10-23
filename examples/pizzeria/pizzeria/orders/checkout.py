"""Pay, cook, deliver."""

from pizzeria.delivery.drivers import dispatch
from pizzeria.kitchen.tickets import cook
from pizzeria.orders.order import Order
from pizzeria.payments.card import charge


def place(order: Order) -> str:
    if not charge(order.phone, order.total()):
        return "Payment declined"
    for pizza in order.pizzas:
        cook(pizza)
    return dispatch(order.address, order.phone)
