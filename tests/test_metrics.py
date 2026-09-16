"""Bob's metrics and zones (A10)."""

from archview.model.metrics import metrics


def test_a_stable_concrete_package_is_in_the_zone_of_pain():
    m = metrics(ca=5, ce=0, abstract=0, modules=4)

    assert (m.instability, m.abstractness, m.distance, m.zone) == (0.0, 0.0, 1.0, "pain")


def test_an_unstable_abstract_package_is_useless():
    assert metrics(ca=0, ce=3, abstract=2, modules=2).zone == "useless"


def test_close_to_the_main_sequence_is_healthy_within_the_threshold():
    assert metrics(ca=1, ce=3, abstract=0, modules=3).zone == "main_sequence"  # D = 0.25
    assert metrics(ca=1, ce=3, abstract=0, modules=3, threshold=0.2).zone == "pain"


def test_a_package_with_no_dependencies_is_isolated():
    m = metrics(ca=0, ce=0, abstract=0, modules=1)

    assert (m.instability, m.distance, m.zone) == (None, None, "isolated")
