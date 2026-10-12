"""Runtime operating guides for the attached application."""

from pathlib import Path


def app_skill(app: str) -> str:
    """Load a known application's guide without accepting arbitrary paths."""
    if app not in {"photocraft", "gridcraft"}:
        return ""
    return (Path(__file__).with_name("app_skills") / f"{app}.md").read_text()
