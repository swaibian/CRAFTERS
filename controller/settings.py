"""LLM provider profiles + gateway/team settings (JSON-file-backed store).

User requirement: "a setup view where I can enter custom AI endpoints + keys
which then will be used". This module owns that persistence:

- ``LlmProfile`` — one custom endpoint: ``{id, label, api_base
  (OpenAI-compatible /v1), api_key, default_model}``.
- ``SettingsStore`` — JSON file (path from ``CRAFTER_SETTINGS_FILE`` env,
  default ``controller/settings.local.json`` which is gitignored): profiles
  CRUD + active-profile pointer + gateway endpoint config + Scaico key +
  selected team id.
- Keys are NEVER logged (only ``key_id``/``last4`` flow to logs) and NEVER
  sent to the view except masked (``mask_key`` shows ``…last4``).

Team JSONs are read from ``Scaico_Teams/teams/`` (passthrough listing).

SW-REQ: SW-REQ-STREAM (settings surface: custom endpoints + keys).
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .logger import get_logger, safe_event

log = get_logger()

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.local.json"

TEAMS_DIR = Path(__file__).resolve().parent.parent / "Scaico_Teams" / "teams"

MASKED_PREFIX = "…"


class SettingsError(Exception):
    """Invalid settings operation (bad id, bad payload — safe message)."""


def mask_key(api_key: str) -> str:
    """Mask an API key for view display (last 4 chars only).

    :param api_key: Raw key (never logged, never returned in full).
    :returns: ``"…last4"`` or ``""`` when empty.
    """
    if not api_key:
        return ""
    tail = api_key[-4:] if len(api_key) >= 4 else "****"
    return f"{MASKED_PREFIX}{tail}"


def key_ref(api_key: str) -> str:
    """Log-safe key reference (last4 only, no key material).

    :param api_key: Raw key.
    :returns: ``"key_…last4"`` or ``"key_none"`` when empty.
    """
    if not api_key:
        return "key_none"
    return f"key_{MASKED_PREFIX}{api_key[-4:]}"


@dataclass
class LlmProfile:
    """One custom OpenAI-compatible endpoint profile.

    :param id: Stable id (``prof_<hex>``).
    :param label: Human label shown in the setup view.
    :param api_base: Base URL of the OpenAI-compatible ``/v1`` endpoint.
    :param api_key: Secret key (stored in the JSON file, never logged).
    :param default_model: Model name sent as ``model`` in chat completions.
    """

    id: str
    label: str
    api_base: str
    api_key: str = ""
    default_model: str = ""

    def public_dict(self) -> dict[str, Any]:
        """View-safe dict: key replaced by its masked form.

        :returns: ``{id, label, api_base, api_key_masked, default_model}``.
        """
        return {
            "id": self.id,
            "label": self.label,
            "api_base": self.api_base,
            "api_key_masked": mask_key(self.api_key),
            "has_key": bool(self.api_key),
            "default_model": self.default_model,
        }


@dataclass
class SettingsState:
    """Full persisted settings document."""

    profiles: list[LlmProfile] = field(default_factory=list)
    active_profile_id: str | None = None
    gateway_endpoint: str = "http://127.0.0.1:8787"
    scaico_api_key: str = ""
    selected_team_id: str | None = None


def _new_profile_id() -> str:
    return f"prof_{secrets.token_hex(8)}"


def _validate_profile_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Validate a create/update payload (raises SettingsError on problems).

    :param payload: Raw caller mapping.
    :returns: Cleaned ``{label, api_base, api_key, default_model}``.
    :raises SettingsError: Missing label/api_base or wrong types.
    """
    if not isinstance(payload, dict):
        raise SettingsError("profile must be a mapping")
    label = payload.get("label", "")
    api_base = payload.get("api_base", "")
    api_key = payload.get("api_key", "")
    default_model = payload.get("default_model", "")
    for name, value in (
        ("label", label),
        ("api_base", api_base),
        ("api_key", api_key),
        ("default_model", default_model),
    ):
        if value is not None and not isinstance(value, str):
            raise SettingsError(f"profile field {name} must be a string")
    if not str(label).strip():
        raise SettingsError("profile label is required")
    if not str(api_base).strip():
        raise SettingsError("profile api_base is required")
    base = str(api_base).strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise SettingsError("profile api_base must be an http(s) URL")
    return {
        "label": str(label).strip(),
        "api_base": base,
        "api_key": str(api_key or ""),
        "default_model": str(default_model or "").strip(),
    }


class SettingsStore:
    """JSON-file-backed settings store (profiles + gateway + Scaico + team).

    :param path: Settings file path. Defaults to ``CRAFTER_SETTINGS_FILE``
        env or ``controller/settings.local.json``. Parent dirs are created.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        raw = (
            path or os.environ.get("CRAFTER_SETTINGS_FILE", "") or DEFAULT_SETTINGS_PATH
        )
        self._path = Path(raw)
        self._lock = threading.Lock()
        self._state = SettingsState()
        self._load()

    @property
    def path(self) -> Path:
        """Settings file path."""
        return self._path

    # -- persistence ------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SettingsError(f"cannot read settings file: {exc}") from None
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SettingsError(f"settings file is not valid JSON: {exc}") from None
        if not isinstance(doc, dict):
            raise SettingsError("settings file must hold a JSON object")
        profiles = []
        for item in doc.get("profiles", []):
            if not isinstance(item, dict):
                continue
            try:
                cleaned = _validate_profile_payload(item)
            except SettingsError:
                continue
            profiles.append(
                LlmProfile(
                    id=str(item.get("id") or _new_profile_id()),
                    **cleaned,
                )
            )
        self._state = SettingsState(
            profiles=profiles,
            active_profile_id=doc.get("active_profile_id"),
            gateway_endpoint=str(doc.get("gateway_endpoint", "http://127.0.0.1:8787")),
            scaico_api_key=str(doc.get("scaico_api_key", "")),
            selected_team_id=doc.get("selected_team_id"),
        )

    def _save(self) -> None:
        doc = {
            "profiles": [asdict(p) for p in self._state.profiles],
            "active_profile_id": self._state.active_profile_id,
            "gateway_endpoint": self._state.gateway_endpoint,
            "scaico_api_key": self._state.scaico_api_key,
            "selected_team_id": self._state.selected_team_id,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    # -- profiles CRUD ----------------------------------------------------

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return view-safe profile dicts (keys masked).

        :returns: List of :meth:`LlmProfile.public_dict`.
        """
        with self._lock:
            return [p.public_dict() for p in self._state.profiles]

    def create_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a profile (logs id + key ref only, never the key).

        :param payload: ``{label, api_base, api_key?, default_model?}``.
        :returns: View-safe dict of the new profile.
        :raises SettingsError: Invalid payload.
        """
        cleaned = _validate_profile_payload(payload)
        profile = LlmProfile(id=_new_profile_id(), **cleaned)
        with self._lock:
            self._state.profiles.append(profile)
            if self._state.active_profile_id is None:
                self._state.active_profile_id = profile.id
            self._save()
        log.info(
            "profile created: %s",
            safe_event(
                event="profile_create",
                profile_id=profile.id,
                key_id=key_ref(profile.api_key),
                ok=True,
            ),
        )
        return profile.public_dict()

    def get_profile(self, profile_id: str) -> LlmProfile | None:
        """Return the full profile (server-side only — includes the key).

        :param profile_id: Profile id.
        """
        with self._lock:
            for profile in self._state.profiles:
                if profile.id == profile_id:
                    return profile
        return None

    def update_profile(
        self, profile_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a profile (empty ``api_key`` keeps the stored key).

        :param profile_id: Profile id.
        :param payload: Partial ``{label?, api_base?, api_key?, default_model?}``.
        :returns: View-safe dict of the updated profile.
        :raises SettingsError: Unknown id or invalid payload.
        """
        with self._lock:
            target = next((p for p in self._state.profiles if p.id == profile_id), None)
            if target is None:
                raise SettingsError("unknown profile")
            merged = {
                "label": payload.get("label", target.label),
                "api_base": payload.get("api_base", target.api_base),
                "api_key": payload.get("api_key", None),
                "default_model": payload.get("default_model", target.default_model),
            }
            if merged["api_key"] in (None, ""):
                merged["api_key"] = target.api_key
            cleaned = _validate_profile_payload(merged)
            target.label = cleaned["label"]
            target.api_base = cleaned["api_base"]
            target.api_key = cleaned["api_key"]
            target.default_model = cleaned["default_model"]
            self._save()
            result = target.public_dict()
            ref = key_ref(target.api_key)
        log.info(
            "profile updated: %s",
            safe_event(
                event="profile_update", profile_id=profile_id, key_id=ref, ok=True
            ),
        )
        return result

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile (clears the active pointer when it pointed here).

        :param profile_id: Profile id.
        :returns: True when a profile was removed.
        """
        with self._lock:
            before = len(self._state.profiles)
            self._state.profiles = [
                p for p in self._state.profiles if p.id != profile_id
            ]
            if self._state.active_profile_id == profile_id:
                self._state.active_profile_id = (
                    self._state.profiles[0].id if self._state.profiles else None
                )
            removed = len(self._state.profiles) < before
            if removed:
                self._save()
        log.info(
            "profile deleted: %s",
            safe_event(event="profile_delete", profile_id=profile_id, ok=removed),
        )
        return removed

    # -- active profile / misc settings -----------------------------------

    def set_active_profile(self, profile_id: str | None) -> None:
        """Point chat completions at a profile (None = MockBrain fallback).

        :param profile_id: Profile id or None.
        :raises SettingsError: Unknown profile id.
        """
        with self._lock:
            if profile_id is not None and not any(
                p.id == profile_id for p in self._state.profiles
            ):
                raise SettingsError("unknown profile")
            self._state.active_profile_id = profile_id
            self._save()
        log.info(
            "active profile: %s",
            safe_event(event="profile_activate", profile_id=profile_id or "", ok=True),
        )

    def active_profile(self) -> LlmProfile | None:
        """Return the active profile (server-side, includes key) or None.

        None means no profile is configured → the agent loop uses MockBrain.
        """
        with self._lock:
            active = self._state.active_profile_id
            if active is None:
                return None
            return next((p for p in self._state.profiles if p.id == active), None)

    def get_gateway_endpoint(self) -> str:
        """Return the configured gateway endpoint URL."""
        with self._lock:
            return self._state.gateway_endpoint

    def set_gateway_endpoint(self, endpoint: str) -> str:
        """Set the gateway endpoint URL (validated http(s)).

        :param endpoint: New endpoint URL.
        :returns: The stored endpoint.
        :raises SettingsError: Not an http(s) URL.
        """
        value = str(endpoint or "").strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise SettingsError("gateway endpoint must be an http(s) URL")
        with self._lock:
            self._state.gateway_endpoint = value
            self._save()
        log.info("gateway endpoint: %s", safe_event(event="gateway_config", ok=True))
        return value

    def set_scaico_key(self, api_key: str) -> dict[str, str]:
        """Store the Scaico API key (logs key ref only, never the key).

        :param api_key: Raw Scaico key (empty clears it).
        :returns: ``{has_key, api_key_masked}`` for the view.
        """
        value = str(api_key or "")
        with self._lock:
            self._state.scaico_api_key = value
            self._save()
        log.info(
            "scaico key stored: %s",
            safe_event(event="scaico_key", key_id=key_ref(value), ok=True),
        )
        return {"has_key": str(bool(value)).lower(), "api_key_masked": mask_key(value)}

    def get_scaico_key(self) -> str:
        """Return the raw Scaico key (server-side only)."""
        with self._lock:
            return self._state.scaico_api_key

    def scaico_status(self) -> dict[str, Any]:
        """View-safe Scaico status (masked key + mailto fallback flag).

        :returns: ``{has_key, api_key_masked, mailto}`` — the view shows the
            ``contact@swaibian.com`` mailto CTA whenever ``has_key`` is false.
        """
        with self._lock:
            key = self._state.scaico_api_key
        return {
            "has_key": bool(key),
            "api_key_masked": mask_key(key),
            "mailto": "contact@swaibian.com",
        }

    def set_selected_team(self, team_id: str | None) -> None:
        """Persist the selected team id (passthrough, validated on read).

        :param team_id: Team id or None to clear.
        """
        with self._lock:
            self._state.selected_team_id = team_id
            self._save()
        log.info("team selected: %s", safe_event(event="team_select", ok=True))

    def get_selected_team(self) -> str | None:
        """Return the selected team id (or None)."""
        with self._lock:
            return self._state.selected_team_id


def list_teams(teams_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """List available teams from the Scaico_Teams JSON dir (passthrough).

    Reads ``*.json`` team files and returns summaries: ``{id, name,
    description, agents: [{id, name, model, runtime_model_name,
    custom_llm_provider, api_base_url}]}``. Secrets are never present in
    team files; only shape metadata is returned.

    :param teams_dir: Override for the teams directory (tests).
    :returns: Team summaries (empty list when the dir is missing).
    """
    root = Path(teams_dir) if teams_dir is not None else TEAMS_DIR
    summaries: list[dict[str, Any]] = []
    try:
        files = sorted(root.glob("*.json"))
    except OSError:
        return []
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        agents: list[dict[str, Any]] = []
        for container in (doc.get("teams", []),):
            if not isinstance(container, list):
                continue
            for team in container:
                if not isinstance(team, dict):
                    continue
                for agent in team.get("agents", []) or []:
                    if not isinstance(agent, dict):
                        continue
                    runtime = agent.get("model_runtime") or {}
                    agents.append(
                        {
                            "id": agent.get("id"),
                            "name": agent.get("name"),
                            "model": agent.get("model"),
                            "runtime_model_name": runtime.get("runtime_model_name"),
                            "custom_llm_provider": runtime.get("custom_llm_provider"),
                            "api_base_url": runtime.get("api_base_url"),
                        }
                    )
        summaries.append(
            {
                "id": doc.get("id", path.stem),
                "name": doc.get("name", path.stem),
                "description": doc.get("description", ""),
                "source": path.name,
                "agents": agents,
            }
        )
    log.info(
        "teams listed: %s",
        safe_event(event="teams_list", count=len(summaries), ok=True),
    )
    return summaries


__all__ = [
    "LlmProfile",
    "SettingsError",
    "SettingsState",
    "SettingsStore",
    "key_ref",
    "list_teams",
    "mask_key",
]
