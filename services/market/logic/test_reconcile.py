from reconcile import (
    IntentSnapshot,
    OrderPaymentRequest,
    intent_matches,
    resolve_order_status,
)


PAYMENT = OrderPaymentRequest(
    payee_id="pay_market_escrow",
    amount_minor=12_000_000,
    currency="NGN",
    reference="ord_test_001",
)


def _intent(**overrides) -> IntentSnapshot:
    base = dict(
        intent_id="pi_abc123",
        status="executed",
        payee_id="pay_market_escrow",
        amount_minor=12_000_000,
        currency="NGN",
        reference="ord_test_001",
    )
    base.update(overrides)
    return IntentSnapshot(**base)


def test_full_match():
    assert intent_matches(PAYMENT, _intent()) is True


def test_wrong_payee():
    assert intent_matches(PAYMENT, _intent(payee_id="pay_evil")) is False


def test_wrong_amount():
    assert intent_matches(PAYMENT, _intent(amount_minor=99)) is False


def test_wrong_reference():
    assert intent_matches(PAYMENT, _intent(reference="ord_someone_else")) is False


def test_executed_and_matched_is_paid():
    assert resolve_order_status(PAYMENT, _intent()) == "paid"


def test_executed_but_mismatch_is_never_paid():
    # This is the critical security rule from spec 4.8
    assert resolve_order_status(PAYMENT, _intent(payee_id="pay_evil")) == "awaiting_payment"
    assert resolve_order_status(PAYMENT, _intent(amount_minor=1)) == "awaiting_payment"
    assert resolve_order_status(PAYMENT, _intent(reference="wrong")) == "awaiting_payment"


def test_pending_approval():
    assert resolve_order_status(PAYMENT, _intent(status="pending_approval")) == "awaiting_approval"


def test_blocked():
    for st in ("blocked", "denied", "expired", "failed"):
        assert resolve_order_status(PAYMENT, _intent(status=st)) == "blocked"


def test_unknown_status_unchanged():
    assert resolve_order_status(PAYMENT, _intent(status="weird")) == "awaiting_payment"


if __name__ == "__main__":
    test_full_match()
    test_wrong_payee()
    test_wrong_amount()
    test_wrong_reference()
    test_executed_and_matched_is_paid()
    test_executed_but_mismatch_is_never_paid()
    test_pending_approval()
    test_blocked()
    test_unknown_status_unchanged()
    print("All reconcile tests passed")