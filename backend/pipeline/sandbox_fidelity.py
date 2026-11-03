"""Does the simulation say exactly what the scenario says, and does the scenario fit its people and the evidence?

Three plain-code checks, no model involved:

* round trip: every step the scenario gave comes out as the same step in the simulation (same person, place,
  action), every stated change to a door or object happens, nobody extra appears, nothing is invented.
  A failure here means a bug in the software, so it is a hard violation.
* roles: a person listed as a victim, witness or member of staff is not shown doing what only an offender does
  (taking things, forcing things, restraining people) unless the scenario lists them as a suspect.
* coverage: people the evidence talks about, and the most relevant timed observations, are either used or
  reported as not used.

What it cannot see is meaning inside the free text; that is for the reviewer model.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from pipeline import sandbox_geometry as geo
from pipeline import sandbox_evidence as evd

NUM_WORDS = {"one": 1, "a single": 1, "single": 1, "lone": 1, "two": 2, "a pair of": 2, "three": 3, "four": 4, "five": 5, "2": 2, "3": 3, "4": 4, "5": 5}
_PEOPLE_NOUNS = r"(?:intruders?|suspects?|burglars?|thieves|thief|assailants?|attackers?|offenders?|perpetrators?|men|man|individuals?|persons?|people|accomplices?)"
_COUNT_RE = re.compile(r"\b(a single|a pair of|one|single|lone|two|three|four|five|2|3|4|5)\s+(?:[\w/'-]+\s+){0,2}?" + _PEOPLE_NOUNS + r"\b", re.I)

# what only someone taking part in the offence does, by the role the scenario gave the person
_OFFENDER_ACTIONS = {"take_item": "taking something", "damage": "damaging or forcing something", "restrain": "restraining someone"}
_NON_OFFENDER_ROLES = {"victim", "witness", "officer", "staff"}
_ACTION_PLAIN = {"take_item": "takes an item", "damage": "damages or forces something", "restrain": "restrains someone", "hand_over": "hands something over"}


def _nid(x: Any) -> str:
    return geo.normalize_id(x)


def round_trip(steps_in: List[Any], actors_in: List[dict], plan: Dict[str, Any], layout: dict) -> Tuple[List[dict], List[str], Dict[str, Any]]:
    """Compares what was asked for with what the simulation contains."""
    violations: List[dict] = []
    warnings: List[str] = []
    declared = [_nid(a.get("id")) for a in actors_in if isinstance(a, dict) and _nid(a.get("id"))] or ["a0"]
    declared_label = {_nid(a.get("id")): geo.clean_text(a.get("label"), 60) for a in actors_in if isinstance(a, dict) and _nid(a.get("id"))}
    labels = {a["id"]: a.get("label", a["id"]) for a in plan.get("actors", [])}
    dropped = {d.get("index") for d in plan.get("dropped_steps", [])}
    node_ids = {n["id"] for g in ("openings", "fixtures", "outdoor_objects") for n in layout.get(g, [])}

    expected: Dict[str, List[Tuple[str, str]]] = {}
    effects_expected: List[Tuple[str, str, str]] = []
    items_expected = set()
    for idx, st in enumerate(steps_in):
        if not isinstance(st, dict) or idx in dropped:
            continue
        aid = _nid(st.get("actor")) or declared[0]
        if aid not in declared:
            continue
        act = _nid(st.get("action"))
        act = act if act in geo.ACTIONS else "other"
        nid = _nid(st.get("node_id"))
        nid = "exterior" if nid in ("exterior", "outside") else nid
        expected.setdefault(aid, []).append((nid, act))
        if st.get("item"):
            items_expected.add(geo.clean_text(st.get("item"), 60).lower())
        for e in (st.get("effects") or [])[:4]:
            if isinstance(e, dict):
                tgt, state = _nid(e.get("target")), str(e.get("state") or "").lower()
                if tgt in node_ids and state in geo.EFFECT_STATES:
                    effects_expected.append((aid, tgt, state))

    shown_steps = 0
    expected_steps = 0
    for a in plan.get("actors", []):
        aid = a["id"]
        want = expected.get(aid, [])
        got = [("exterior" if s["node_id"] in ("exterior", "outside") else s["node_id"], s["action"]) for s in a["steps"]]
        expected_steps += len(want)
        shown_steps += len(got)
        if want != got:
            # the simulation may drop whole steps (over the cap, dropped person); anything else is a defect
            missing = [w for w in want if w not in got]
            extra = [g for g in got if g not in want]
            if missing or extra or len(want) != len(got):
                violations.append({"code": "fidelity_steps", "step": None, "actor": aid,
                                   "message": f"{labels.get(aid, aid)}: the simulation does not contain exactly the steps the scenario gave (missing {len(missing)}, extra {len(extra)})"})
    for aid in expected:
        if aid not in {a["id"] for a in plan.get("actors", [])} and expected[aid]:
            violations.append({"code": "fidelity_steps", "step": None, "actor": aid, "message": f"{aid}: steps were given for this person but they do not appear in the simulation"})

    shown_effects = {(e["actor"], e["target"], e["state"]) for e in plan.get("effects", [])}
    missing_fx = [e for e in effects_expected if e not in shown_effects]
    for aid, tgt, state in missing_fx:
        violations.append({"code": "fidelity_effect", "step": None, "actor": aid, "message": f"the scenario says '{tgt}' becomes {state}, but the simulation never changes it"})

    shown_items = {(s.get("item") or "").lower() for a in plan.get("actors", []) for s in a["steps"] if s.get("item")}
    for it in sorted(shown_items - items_expected):
        violations.append({"code": "fidelity_item", "step": None, "actor": None, "message": f"the simulation shows an item '{it}' that the scenario never mentions"})

    declared_with_steps = {aid for aid, w in expected.items() if w}
    for aid in declared:
        if aid not in declared_with_steps:
            warnings.append(f"{declared_label.get(aid) or aid} is listed as a person in this scenario but has no steps, so they are not shown")
    report = {
        "steps_given": sum(len(v) for v in expected.values()), "steps_in_simulation": shown_steps, "steps_not_placed": len(dropped),
        "effects_expected": len(effects_expected), "effects_in_simulation": len(effects_expected) - len(missing_fx),
        "people_listed": len(declared), "people_shown": len(plan.get("actors", [])),
        "round_trip_ok": not violations,
    }
    return violations, warnings, report


def summary_count_warnings(texts: List[str], plan: Dict[str, Any]) -> List[str]:
    """'Two intruders' in the summary but one suspect in the steps (or the reverse)."""
    suspects = [a for a in plan.get("actors", []) if a.get("role") == "suspect"]
    if not suspects:
        return []
    out: List[str] = []
    seen = set()
    for tx in texts:
        for m in _COUNT_RE.finditer(tx or ""):
            n = NUM_WORDS.get(m.group(1).lower())
            if n and n != len(suspects) and (n, len(suspects)) not in seen:
                seen.add((n, len(suspects)))
                out.append(f"The text says {m.group(0).strip()!r}, but the scenario shows {len(suspects)} suspect(s)")
    return out


def role_warnings(plan: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for a in plan.get("actors", []):
        role = a.get("role")
        if role not in _NON_OFFENDER_ROLES:
            continue
        seen = set()
        for s in a["steps"]:
            act = s["action"]
            if act in _OFFENDER_ACTIONS and act not in seen:
                seen.add(act)
                out.append(f"{a['label']} is listed as {('a ' if role != 'staff' else '')}{role if role != 'staff' else 'a member of staff'}, but is shown {_OFFENDER_ACTIONS[act]} at step {s['k'] + 1}. "
                           f"If this is meant to be an insider or accomplice account, the scenario should list them as a suspect and say why.")
    return out


# names that are not a particular person, and people who investigated afterwards rather than took part
_GENERIC_WORDS = {"several", "people", "person", "persons", "individual", "individuals", "unknown", "unidentified", "male", "female", "man", "men", "woman", "women",
                  "staff", "witness", "witnesses", "suspect", "suspects", "group", "crowd", "public", "someone", "somebody", "others", "another", "second", "third", "guard", "customer", "customers"}
_UNNAMED_MARKERS = {"unidentified", "unknown", "unnamed", "individual", "individuals", "male", "female"}
_INVESTIGATOR_WORDS = {"inspector", "sub-inspector", "investigating", "investigator", "examiner", "forensic", "analyst", "sergeant", "detective", "magistrate"}


def _is_participant_name(name: str) -> bool:
    words = [w for w in re.split(r"[^a-z0-9-]+", name.lower()) if w]
    if not words or all(w in _GENERIC_WORDS for w in words):
        return False
    if any(w in _UNNAMED_MARKERS for w in words):  # "unidentified person in a dark jacket" describes someone, it does not name them
        return False
    return not any(w in _INVESTIGATOR_WORDS for w in words)


def named_suspect_warnings(ev: Dict[str, Any], plan: Dict[str, Any]) -> List[str]:
    """Treating a real, named person from the case as a suspect is serious. It is allowed only as a visible, checkable claim."""
    out: List[str] = []
    names = []
    for e in ev.get("entities", []):
        if e.get("entity_type") == "person" and _is_participant_name((e.get("canonical_name") or "").strip()):
            words = [w for w in re.split(r"[^a-z0-9]+", (e.get("canonical_name") or "").lower()) if len(w) >= 4]
            if words:
                names.append((e["canonical_name"], words))
    for a in plan.get("actors", []):
        if a.get("role") != "suspect":
            continue
        label = (a.get("label") or "").lower()
        for name, words in names:
            if any(w in label for w in words):
                cited = len({r for s in a["steps"] for r in s.get("evidence_refs", [])})
                out.append(f"This scenario treats {name}, a named person in the evidence, as a suspect. Only {cited} piece(s) of evidence are cited for the steps attributed to them. "
                           f"Check that the evidence itself points at them before relying on this.")
                break
    return out


def coverage(ev: Dict[str, Any], plan: Dict[str, Any], texts: List[str], cited: set) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    body = " ".join(texts + [a["label"] + " " + a["id"] for a in plan.get("actors", [])]).lower()
    obs_text = [(o["observation_id"], (o.get("description") or "").lower()) for o in ev.get("observations", [])]
    missing_people = []
    for e in ev.get("entities", []):
        if e.get("entity_type") != "person":
            continue
        name = (e.get("canonical_name") or "").strip()
        if not _is_participant_name(name):
            continue
        words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if len(w) >= 4]
        if not words:
            continue
        n = sum(1 for _, t in obs_text if any(w in t for w in words))
        if n >= 2 and not any(w in body for w in words):
            missing_people.append((n, name))
    missing_people.sort(reverse=True)
    for n, name in missing_people[:4]:
        warnings.append(f"The evidence mentions {name} in {n} observations, but this scenario neither includes nor mentions them")
    try:
        selected, _ = evd.select_observations(ev)
    except Exception:  # noqa: BLE001 - coverage is advisory; never block a scenario
        selected = []
    key = [o["observation_id"] for o in selected[:15]]
    used = [i for i in key if i in cited]
    unused = [i for i in key if i not in cited]
    if key and len(used) / len(key) < 0.35:
        warnings.append(f"This scenario uses only {len(used)} of the {len(key)} most relevant observations")
    return {"key_observations": len(key), "key_used": len(used), "key_unused": unused[:6], "people_not_covered": [n for _, n in missing_people[:4]]}, warnings


def check(steps_in: List[Any], actors_in: List[dict], plan: Dict[str, Any], layout: dict, ev: Dict[str, Any], texts: List[str], cited: set) -> Dict[str, Any]:
    """Everything above, in one call. Violations are software defects; warnings are for the reader."""
    v, w, report = round_trip(steps_in, actors_in, plan, layout)
    count_w = summary_count_warnings(texts, plan)
    role_w = role_warnings(plan)
    cov, cov_w = coverage(ev, plan, texts, cited)
    named_w = named_suspect_warnings(ev, plan)
    return {"violations": v, "warnings": w + count_w + role_w + named_w + cov_w, "report": report, "coverage": cov,
            "caution_counts": {"summary_count_mismatch": len(count_w), "role_mismatch": len(role_w), "coverage_gaps": len(cov_w), "named_suspect": len(named_w)}}
