"""Simulated stand-ins for the chat tool, the HR system and the clock."""
from __future__ import annotations

from datetime import datetime, timedelta


class FakeChat:
    """Records every message. In real life these would be chat messages with buttons."""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []  # (recipient, text)

    def send(self, to: str, text: str):
        self.messages.append((to, text))

    def to(self, recipient: str) -> list[str]:
        return [text for who, text in self.messages if who == recipient]


class FakeHR:
    """The external HR system: accepts claims, approves them later (1-10 days)."""

    def __init__(self):
        self.claims: dict[str, dict] = {}

    def submit_claim(self, employee_id, amount, currency, description, receipt) -> str:
        claim_id = f"HR-{len(self.claims) + 1}"
        self.claims[claim_id] = {
            "employee_id": employee_id,
            "amount": amount,
            "currency": currency,
            "description": description,
            "receipt": receipt,
            "status": "pending",
        }
        return claim_id

    def status(self, claim_id: str) -> str:
        return self.claims[claim_id]["status"]

    def approve(self, claim_id: str):  # tests call this to simulate HR
        self.claims[claim_id]["status"] = "approved"


class FakeClock:
    def __init__(self, start: datetime):
        self.now = start

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)
