"""Review fixture illustrating explicit domain logic."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentNotification:
    account_id: str
    amount_cents: int
    currency: str

    def message(self) -> str:
        amount = self.amount_cents / 100
        return f"Payment received: {amount:.2f} {self.currency}"


def receipt_subject(notification: PaymentNotification) -> str:
    return f"Receipt for account {notification.account_id}"
