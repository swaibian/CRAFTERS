#!/usr/bin/env python3
"""Validate generated team JSON against the reference Scaico team schema."""
import glob
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(BASE, "example", "timeattack_vehicle_dynamics_2026-10-11T18-10-42.json")

ref = json.load(open(REF))
ref_team = set(ref.keys())
ref_sub = set(ref["teams"][0].keys())
ref_agent = set(ref["agents"][0].keys())

print(f"reference: team keys = {sorted(ref_team)}")
print(f"reference: agent keys = {sorted(ref_agent)}")
print()

fail = 0
for path in sorted(glob.glob(os.path.join(BASE, "teams", "*.json"))):
    d = json.load(open(path))
    name = os.path.basename(path)
    checks = {
        "team_keys": set(d.keys()) == ref_team,
        "subteam_keys": set(d["teams"][0].keys()) == ref_sub,
        "agent_keys": all(set(a.keys()) == ref_agent for a in d["agents"]),
        "agents_mirror_subteam": d["agents"] == d["teams"][0]["agents"],
        "no_dup_tools": all(len(a["tools"]) == len(set(a["tools"])) for a in d["agents"]),
        "no_dup_agent_ids": len(d["agents"]) == len({a["id"] for a in d["agents"]}),
        "one_leader": sum(1 for a in d["agents"] if a["type"] == "team_leader") == 1,
        "leader_resolves": d["team_leader_id"] in {a["id"] for a in d["agents"]},
        "mcp_tools_match": all(a["mcp_servers"][0]["tools"] == a["tools"] for a in d["agents"]),
        "transport_ok": all(a["mcp_servers"][0]["transport"] == "streamable_http" for a in d["agents"]),
        "url_token_present": all(
            a["mcp_servers"][0].get("url") and a["mcp_servers"][0].get("token")
            for a in d["agents"]
        ),
        "skills_present": all(len(a["skills"]) > 0 for a in d["agents"]),
        "skills_wellformed": all(
            all(set(s.keys()) == {"name", "description", "content"} for s in a["skills"])
            for a in d["agents"]
        ),
        "readonly_agents_clean": all(
            not any(t.startswith("act_") for t in a["tools"])
            for a in d["agents"] if a["id"].endswith(("_qa", "_curator", "_lead"))
        ),
        "claim_present_on_editors": all(
            "team_claim" in a["tools"] and "team_checkpoint" in a["tools"]
            for a in d["agents"]
            if any(t.startswith("act_") for t in a["tools"])
        ),
        "readers_can_wait": all(
            "job_wait" in a["tools"]
            for a in d["agents"] if a["id"].endswith(("_qa", "_curator", "_lead"))
        ),
    }
    bad = [k for k, v in checks.items() if not v]
    fail += len(bad)
    status = "OK  " if not bad else "FAIL"
    print(f"{status} {name}: agents={len(d['agents'])} tools/agent={len(d['agents'][0]['tools'])} bad={bad}")

print()
print("FAILURES:", fail)