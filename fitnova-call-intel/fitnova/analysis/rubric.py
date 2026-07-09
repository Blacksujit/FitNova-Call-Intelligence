"""Scoring dimensions for call quality analysis."""

DIMENSIONS = [
    "needs_discovery",
    "product_knowledge",
    "objection_handling",
    "compliance",
    "next_step_booking",
]

SEVERITY_LEVELS = ["low", "medium", "high"]

ALLOWED_TAGS = [
    "no_needs_discovery",
    "over_promising",
    "pressure_tactics",
    "price_before_value",
    "undisclosed_costs",
    "weak_trial_booking",
    "talking_over_customer",
]
