"""The two offices from the brief. Budgets and purchase ranges are data, not code."""
from .models import Office
from .money import Money


def default_offices() -> list[Office]:
    return [
        Office(
            id="oslo",
            name="Oslo",
            currency="NOK",
            timezone="Europe/Oslo",
            monthly_budget=Money(6000, "NOK"),
            min_purchase=Money(300, "NOK"),
            max_purchase=Money(1200, "NOK"),
            chat_channel="#snacks-oslo",
            admin_chat_id="@oslo-coordinator",
        ),
        Office(
            id="blr",
            name="Bengaluru",
            currency="INR",
            timezone="Asia/Kolkata",
            monthly_budget=Money(15000, "INR"),
            min_purchase=Money(500, "INR"),
            max_purchase=Money(3000, "INR"),
            chat_channel="#snacks-bengaluru",
            admin_chat_id="@blr-coordinator",
        ),
    ]
