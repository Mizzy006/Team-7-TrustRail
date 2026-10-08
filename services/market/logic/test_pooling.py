from pooling import (
    progress_pct,
    current_tier_price,
    next_tier,
    settlement_amounts,
)


TIERS = [
    {"min_qty": 1, "unit_price_minor": 1200000},
    {"min_qty": 50, "unit_price_minor": 1120000},
    {"min_qty": 200, "unit_price_minor": 1050000},
]


def test_progress():
    assert progress_pct(32, 50) == 64.0
    assert progress_pct(60, 50) == 100.0
    assert progress_pct(0, 50) == 0.0


def test_current_price():
    assert current_tier_price(TIERS, 10) == 1200000
    assert current_tier_price(TIERS, 50) == 1120000
    assert current_tier_price(TIERS, 199) == 1120000
    assert current_tier_price(TIERS, 200) == 1050000


def test_next_tier():
    assert next_tier(TIERS, 10) == {"min_qty": 50, "unit_price_minor": 1120000}
    assert next_tier(TIERS, 50) == {"min_qty": 200, "unit_price_minor": 1050000}
    assert next_tier(TIERS, 200) is None


def test_settlement_success():
    release, refund = settlement_amounts(
        committed_qty=100,
        hold_amount_minor=120_000_000,
        tiers=TIERS,
        success=True,
    )
    assert release == 112_000_000
    assert refund == 8_000_000


def test_settlement_failure():
    release, refund = settlement_amounts(
        committed_qty=30,
        hold_amount_minor=36_000_000,
        tiers=TIERS,
        success=False,
    )
    assert release == 0
    assert refund == 36_000_000


if __name__ == "__main__":
    test_progress()
    test_current_price()
    test_next_tier()
    test_settlement_success()
    test_settlement_failure()
    print("All pooling tests passed")