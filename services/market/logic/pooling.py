"""Pooling logic — MOQ, tier selection, progress.
Spec: docs/PROJECT_SPEC.md Section 4.8
Owner: Software Developer
"""
from typing import Optional


def progress_pct(committed_qty: int, moq: int) -> float:
    """Return committed_qty / moq * 100, clamped to 100."""
    if moq <= 0:
        return 0.0
    pct = (committed_qty / moq) * 100
    return min(round(pct, 1), 100.0)


def current_tier_price(tiers: list[dict], committed_qty: int) -> int:
    """Return the unit price for the highest tier whose min_qty <= committed_qty."""
    if not tiers:
        raise ValueError("tiers must not be empty")

    sorted_tiers = sorted(tiers, key=lambda t: t["min_qty"])
    chosen = sorted_tiers[0]

    for tier in sorted_tiers:
        if committed_qty >= tier["min_qty"]:
            chosen = tier
        else:
            break

    return chosen["unit_price_minor"]


def next_tier(tiers: list[dict], committed_qty: int) -> Optional[dict]:
    """Return the next tier up, or None if already at the highest."""
    sorted_tiers = sorted(tiers, key=lambda t: t["min_qty"])
    for tier in sorted_tiers:
        if committed_qty < tier["min_qty"]:
            return tier
    return None


def pool_can_close(committed_qty: int, moq: int) -> bool:
    """Success condition for pool close (spec 4.8)."""
    return committed_qty >= moq


def final_unit_price(tiers: list[dict], committed_qty: int) -> int:
    """Price used at close time: tier with highest min_qty <= committed_qty."""
    return current_tier_price(tiers, committed_qty)


def settlement_amounts(
    *,
    committed_qty: int,
    hold_amount_minor: int,
    tiers: list[dict],
    success: bool,
) -> tuple[int, int]:
    """Return (release_minor, refund_minor) for a pool close.

    On success: release = committed_qty * final_unit_price; refund = hold - release.
    On failure: release = 0; refund = hold_amount_minor.

    Spec 4.8: release + refund must equal hold amount.
    """
    if not success:
        return (0, hold_amount_minor)

    final_price = final_unit_price(tiers, committed_qty)
    release = committed_qty * final_price
    refund = hold_amount_minor - release

    if refund < 0:
        raise ValueError(
            f"release ({release}) exceeds hold ({hold_amount_minor}). "
            "Hold was created at a smaller tier — check pricing."
        )

    return (release, refund)