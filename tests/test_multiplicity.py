"""Multiplicity correction, including the handling of non-estimable comparisons."""

from __future__ import annotations

import numpy as np
import pytest

from experimentguard.stats.multiplicity import adjust, bh_adjust, holm_adjust


def test_holm_matches_the_hand_computed_procedure():
    """Holm: sort ascending, multiply p_(i) by (m - i + 1), enforce monotonicity."""
    p = [0.001, 0.012, 0.030, 0.400]
    m = len(p)
    order = np.argsort(p)
    stepped, running = np.empty(m), 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        stepped[idx] = min(running, 1.0)

    _, adjusted = holm_adjust(p, alpha=0.05)
    assert adjusted == pytest.approx(stepped)


def test_holm_is_more_conservative_than_bh():
    p = [0.001, 0.012, 0.030, 0.045, 0.400]
    holm_reject, _ = holm_adjust(p, alpha=0.05)
    bh_reject, _ = bh_adjust(p, alpha=0.05)
    assert holm_reject.sum() <= bh_reject.sum()


def test_bh_matches_benjamini_hochberg_worked_example():
    """The BH(1995) illustration: 15 p-values, 4 declared significant at q = 0.05."""
    p = [
        0.0001,
        0.0004,
        0.0019,
        0.0095,
        0.0201,
        0.0278,
        0.0298,
        0.0344,
        0.0459,
        0.3240,
        0.4262,
        0.5719,
        0.6528,
        0.7590,
        1.000,
    ]
    reject, _ = bh_adjust(p, alpha=0.05)
    assert int(reject.sum()) == 4


def test_non_estimable_comparisons_never_reject_and_do_not_inflate_the_family():
    """A None p-value is 'no evidence', not 'p = 1'.

    Treating it as 1.0 would enlarge the family and weaken every other comparison,
    so it is excluded from the rank accounting instead.
    """
    with_none = [0.001, None, 0.012]
    without = [0.001, 0.012]

    reject_n, adjusted_n = holm_adjust(with_none, alpha=0.05)
    reject_w, adjusted_w = holm_adjust(without, alpha=0.05)

    assert reject_n[1] is np.False_ or not reject_n[1]
    assert np.isnan(adjusted_n[1])
    assert adjusted_n[[0, 2]] == pytest.approx(adjusted_w)


def test_all_non_estimable_rejects_nothing():
    reject, adjusted = holm_adjust([None, None])
    assert not reject.any()
    assert np.isnan(adjusted).all()


def test_unknown_method_is_rejected():
    with pytest.raises(ValueError, match="unsupported multiplicity method"):
        adjust([0.01], method="sidak")
