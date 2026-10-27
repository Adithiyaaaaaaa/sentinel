"""Illustrative test source, never executed by SENTINEL's indexer."""

from services.notifications import PaymentNotification


def test_message_formats_money() -> None:
    notification = PaymentNotification("demo-account", 1250, "USD")
    assert notification.message() == "Payment received: 12.50 USD"
