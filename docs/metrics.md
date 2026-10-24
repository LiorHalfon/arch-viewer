# Instability, abstractness and zones

`archview metrics` prints Robert C. Martin's package metrics for every component. The
viewer uses the same numbers: View → Colour by → Instability or Zone colours the boxes
by them, and the link under the legend's buttons opens a panel that plots the current
view's boxes and explains them in short. This page is the longer version.

The metrics come from Martin's *Agile Software Development: Principles, Patterns and
Practices* (2002). Wikipedia's
[Software package metrics](https://en.wikipedia.org/wiki/Software_package_metrics)
page summarises them. archview uses the same formulas with one change of unit, described
under [Modules, not classes](#modules-not-classes).

## What `archview metrics` prints

On the demo in `examples/pizzeria`:

```
component      Ca  Ce  I     A     D     zone
delivery       1   1   0.50  0.00  0.50  pain
kitchen        1   1   0.50  0.00  0.50  pain
menu           7   0   0.00  0.00  1.00  pain
notifications  2   0   0.00  0.00  1.00  pain
orders         1   4   0.80  0.00  0.20  main_sequence
payments       1   1   0.50  0.00  0.50  pain
storefront     0   3   1.00  0.00  0.00  main_sequence
```

- **Ca** (afferent coupling): how many modules outside the component import something
  in it.
- **Ce** (efferent coupling): how many modules outside the component something in it
  imports.
- **I**, **A**, **D** and **zone**: below.

Both counts are distinct modules across the whole project, so a component's numbers do
not change with the level you are looking at in the viewer.

## Instability, I

I = Ce ÷ (Ca + Ce). It says how much a component leans on others compared with how
much others lean on it.

- **I = 0**: other code imports it and it imports nothing. A change to it can break
  everything that depends on it, so it is expensive to change. `menu` is 0: 7 modules
  elsewhere import it and it imports nothing.
- **I = 1**: it imports other code and nothing imports it. Nothing breaks when it
  changes. `storefront` is 1: it imports from 3 modules and nothing imports it.

A component with no imports either way has no instability. Its zone is `isolated`, which
the viewer shows as "no dependencies".

## Abstractness, A

A is the share of a component's modules that are abstract.

- A Python module counts as abstract when it defines a class that subclasses `Protocol`
  or `ABC`, uses `metaclass=ABCMeta`, or has an `@abstractmethod`.
- A TypeScript file counts when it has an `abstract class`, or exports types and
  interfaces and no values.

A component with 2 such modules out of 5 has A = 0.40. One abstract class is enough for
the whole module to count, even next to ten concrete classes.

## Distance and the zones

Code that much else depends on should be abstract, so that a change lands behind an
interface instead of in every caller. Code that nothing depends on can be concrete. Plot
A against I and the healthy components sit near the line from (I 0, A 1) to (I 1, A 0),
the **main sequence**. D = |A + I − 1| is the distance from it.

A component more than the threshold away from the line is in a zone. The threshold is
0.3 unless the rules file sets another:

```toml
[archview.metrics]
threshold = 0.3            # distance from the main sequence counted as healthy
fail_on_zones = ["pain"]   # optional: archview check fails when a component enters a zone
ignore = ["menu"]          # components fail_on_zones leaves alone
```

- **Zone of pain** (A + I below 1 − threshold, bottom left): stable and concrete. Much
  imports it and it offers no interface, so every change spreads. That is fine for code
  that rarely changes, such as settings, shared utilities or data models.
- **Zone of uselessness** (A + I above 1 + threshold, top right): abstract and
  unstable. Interfaces that little or nothing uses.
- **Main sequence**: within the threshold of the line.

In the pizzeria, `menu` and `notifications` are in the zone of pain and expected to be:
everything uses them and they rarely change. `kitchen`, `payments` and `delivery` sit
there too, at D = 0.50: each is imported once and offers no abstraction to import
instead. `orders` and `storefront` are on the main sequence: unstable and concrete, the
top of the app, where change belongs. Nothing here is in the zone of uselessness; that
takes abstract code that nothing imports.

## Modules, not classes

Martin and the Wikipedia page count classes: Ca and Ce count the classes in other
packages that depend on, or are depended on by, the package's classes, and A is the
share of a package's classes and interfaces that are abstract. archview counts modules
instead, because the module is the unit its model holds (ADR 0008):

- Ca and Ce count modules outside the component, not classes.
- A is the share of the component's modules that are abstract, where a module counts
  as abstract when one class in it is.

I and D use Martin's formulas unchanged. The numbers read the same way, but they are
coarser than a class-level tool's: a module with one `Protocol` and ten concrete classes
counts as fully abstract.

## Reading the chart in the viewer

The panel's chart puts every box of the current view on these axes: instability across,
abstractness up, with the two zones shaded and the main sequence dashed. Boxes at the
same point share one dot labelled with the first name and `+N`. Third-party boxes and
boxes with no dependencies are left out.

Hover a dot to light up its box in the diagram, or hover a box to find its dot. Click a
dot to flash its box. The chart follows you as you drill down.
