# pizzeria

A small pizza shop to try archview on. The storefront takes orders, the kitchen cooks
them, payments and delivery do the rest.

```bash
archview examples/pizzeria          # the viewer
archview check examples/pizzeria    # fails, on purpose
```

Two problems are planted in the kitchen's assembly line (`pizzeria/kitchen/stations`):

- **A cycle:** `toppings` asks the `oven` how hot it is, and the `oven` takes pizzas from
  `toppings`.
- **A broken rule:** the stations' rules file says `boxing` takes pizzas from the `oven`
  only, but `boxing` imports `dough` to patch a torn base.

Everything above the stations is clean. `tests/test_examples.py` keeps it that way.
