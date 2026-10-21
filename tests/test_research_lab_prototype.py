"""Smoke tests for the integrated research/replay prototype routes."""
from api import app


def test_research_lab_and_scenario_endpoints_are_registered():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("GET", "/research-lab") in routes
    assert ("GET", "/api/scenarios/options") in routes
    assert ("POST", "/api/scenarios/generate") in routes
    assert ("POST", "/api/scenarios/run") in routes


def test_research_lab_is_served_from_the_project_web_directory():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    lab = project_root / "web" / "research-lab.html"
    assert lab.is_file()
    source = lab.read_text(encoding="utf-8")
    assert "SIMULATION / RESEARCH MODE ONLY" in source
    assert "/api/scenarios/generate" in source
    assert "/api/scenarios/run" in source
