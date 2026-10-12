"""SWE4 packaging tests for TC-C-01 (compose + Dockerfiles + run docs).

Validates the shippable slice statically (no docker daemon needed):
compose defines gateway+controller+view with loopback-only ports, work +
settings volumes, healthchecks, and log rotation; Dockerfiles bake in no
secrets; the README documents fresh-checkout run + troubleshooting.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEPLOY = REPO / "deploy"


def _read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_compose_has_all_three_services():
    text = _read("docker-compose.yml")
    for service in ("gateway:", "controller:", "view:"):
        assert service in text


def test_compose_ports_loopback_only():
    text = _read("docker-compose.yml")
    assert "127.0.0.1:8787:8787" in text
    assert "127.0.0.1:8790:8790" in text
    assert "127.0.0.1:8791:80" in text


def test_compose_volumes_and_health():
    text = _read("docker-compose.yml")
    assert "crafter-work" in text
    assert "crafter-settings" in text
    assert "CRAFTER_SETTINGS_FILE" in text
    assert "healthcheck" in text
    assert "/api/health" in text
    assert "max-size" in text  # log rotation, no disk blowup


def test_dockerfiles_bake_no_secrets():
    for name in ("Dockerfile", "Dockerfile.controller", "Dockerfile.view"):
        text = _read(name)
        code_lines = [
            line
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines).lower()
        assert "api_key" not in code, name
        assert "secret" not in code, name
        assert "sk-" not in code, name
        assert "bearer " not in code or "enforced" in code, name
    controller = _read("Dockerfile.controller")
    assert "useradd" in controller
    assert "EXPOSE 8790" in controller


def test_nginx_proxies_api_with_sse():
    text = _read("nginx.view.conf")
    assert "proxy_pass http://controller:8790" in text
    assert "proxy_buffering off" in text
    assert "try_files" in text  # hash/static fallback


def test_readme_documents_fresh_run():
    text = _read("README.md")
    assert "docker compose up --build" in text
    assert "127.0.0.1:8791" in text
    assert "CRAFTER_DEV_TOKEN" in text
    assert "Troubleshooting" in text
    assert "mock" in text.lower()
