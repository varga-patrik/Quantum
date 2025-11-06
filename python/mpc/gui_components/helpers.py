"""Helper functions for GUI operations."""

def format_number(number: int) -> str:
    """Format a number with space as thousand separator."""
    return f"{number:,}".replace(",", " ")


def format_angles(angles) -> str:
    """Format three angles for display."""
    try:
        return f"{angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f}"
    except (IndexError, TypeError):
        return "- , - , -"
