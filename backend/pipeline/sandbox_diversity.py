"""Makes the candidate scenarios genuinely different possibilities, not three tellings of one story.

The model is not left to decide what "different" means. Code finds the questions the evidence leaves open
(which entry, how many people, inside knowledge, which clock to trust, each unresolved conflict between
sources) and gives every scenario a different position on them: the first takes the best-supported answer to
all of them, the others each take the alternative on a different question. Afterwards code measures how
different the finished scenarios really are and sends near-copies back.

Nothing here invents facts. An alternative is offered only where the evidence itself points both ways or is
silent, and it is labelled as less supported whenever the evidence leans the other way.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

MIN_DISTANCE = 0.22  # below this two scenarios are treated as the same story

_SINGLE_RE = re.compile(r"\b(lone|single|alone|solo|one (?:man|person|individual|intruder|suspect))\b", re.I)
_MULTI_RE = re.compile(r"\b(two|three|second|another|both|accomplice|accomplices|lookout|look-out|driver|group of|pair of|a team)\b[^.\n]{0,40}\b(men|man|persons?|people|individuals?|suspects?|intruders?|burglars?|youths?)\b|\b(accomplices?|lookout|look-out|getaway driver)\b", re.I)
_INSIDE_RE = re.compile(r"\b(inside knowledge|insider|knew the (?:layout|alarm|code|routine)|had a key|used a key|key was|no sign of forced|not forced|without forcing|alarm (?:was )?disabled|cctv (?:was )?(?:off|disabled)|familiar with)\b", re.I)
_FORCED_RE = re.compile(r"\b(forced|pried|prised|broken|smashed|jemmied|crowbar|tool marks?|cut)\b", re.I)
_CLOCK_RE = re.compile(r"\b(clock|offset|overlay|timestamp|time stamp|ntp|running (?:fast|slow)|minutes? (?:fast|slow|ahead|behind)|out of sync|synchron)", re.I)


def _texts(ev: Dict[str, Any]) -> List[str]:
    return [(o.get("description") or "") for o in ev.get("observations", [])]


def people_ambiguity(ev: Dict[str, Any]) -> Dict[str, Any]:
    texts = _texts(ev)
    single = sum(1 for t in texts if _SINGLE_RE.search(t))
    multi = sum(1 for t in texts if _MULTI_RE.search(t))
    return {"single_cues": single, "multi_cues": multi, "ambiguous": bool(single and multi)}


def open_questions(layout: Dict[str, Any], ev: Dict[str, Any], max_conflicts: int = 3) -> List[Dict[str, Any]]:
    """The real open questions, most important first. Each option says how well the evidence supports it."""
    axes: List[Dict[str, Any]] = []
    ext = [o for o in layout.get("openings", []) if o.get("kind") == "external" and o.get("reachable", True)]
    if len(ext) >= 2:
        def rank(o: dict) -> Tuple[int, int]:
            return (0 if o["state"] == "forced" else 1 if o["state"] in ("open", "unknown") else 2, 0 if o.get("basis") == "stated" else 1)
        ranked = sorted(ext, key=rank)
        axes.append({"key": "entry", "question": "Which outside door or opening did they come in by?",
                     "options": [{"id": o["id"], "text": f"in through '{o['label']}' (recorded as {o['state']})", "support": "best" if i == 0 else "alternative"} for i, o in enumerate(ranked[:3])]})
    pa = people_ambiguity(ev)
    if pa["ambiguous"]:
        axes.append({"key": "people", "question": "How many people were involved?",
                     "options": [{"id": "1", "text": "one person acting alone", "support": "best" if pa["single_cues"] >= pa["multi_cues"] else "alternative"},
                                 {"id": "2", "text": "two or more people working together", "support": "best" if pa["multi_cues"] > pa["single_cues"] else "alternative"}]})
    texts = _texts(ev)
    inside = sum(1 for t in texts if _INSIDE_RE.search(t))
    forced = sum(1 for t in texts if _FORCED_RE.search(t))
    if inside and forced:
        axes.append({"key": "inside", "question": "Did the offender have inside knowledge or access?",
                     "options": [{"id": "outsider", "text": "an outsider who forced their way in", "support": "best" if forced >= inside else "alternative"},
                                 {"id": "insider", "text": "someone with inside knowledge or access (say what in the evidence points to it)", "support": "best" if inside > forced else "alternative"}]})
    clock_conf = [c for c in ev.get("conflicts", []) if _CLOCK_RE.search(f"{c.get('claim_a', '')} {c.get('claim_b', '')} {c.get('nature_of_conflict', '')} {c.get('question', '')}")]
    if clock_conf:
        axes.append({"key": "clock", "question": "Which clock should be trusted where the recordings disagree?",
                     "options": [{"id": "corrected", "text": "apply the documented clock offset so the recordings line up", "support": "best"},
                                 {"id": "face_value", "text": "take each recording's times at face value, so the sequence is different", "support": "alternative"}]})
    done = 0
    for c in ev.get("conflicts", []):
        if done >= max_conflicts or (c.get("review_status") or "unresolved") != "unresolved" or c in clock_conf:
            continue
        a, b = (c.get("claim_a") or "")[:140], (c.get("claim_b") or "")[:140]
        if a and b:
            axes.append({"key": f"conflict:{c.get('conflict_id')}", "question": f"Sources disagree: {a}  versus  {b}",
                         "options": [{"id": "a", "text": f"take this as true: {a}", "support": "best"}, {"id": "b", "text": f"take this as true: {b}", "support": "alternative"}]})
            done += 1
    return axes


def assign_branches(axes: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    """What each scenario must decide. Scenario 1 follows the best-supported answers; every other one flips
    a different question to its alternative (a second question too once there are enough of them)."""
    flippable = [a for a in axes if len(a["options"]) >= 2]
    plans: List[Dict[str, Any]] = [{"scenario": 1, "flips": []}]
    for i in range(1, n):
        flips = []
        if flippable:
            flips.append(flippable[(i - 1) % len(flippable)])
            if len(flippable) >= 4 and i == n - 1:
                flips.append(flippable[(i + 1) % len(flippable)])
        plans.append({"scenario": i + 1, "flips": flips})
    out = []
    for p in plans:
        flips = []
        for a in p["flips"]:
            alt = [o for o in a["options"] if o["support"] != "best"] or a["options"][1:]
            flips.append({"key": a["key"], "question": a["question"], "option": alt[0]})
        out.append({"scenario": p["scenario"], "flips": flips})
    return out


def brief_text(axes: List[Dict[str, Any]], assignment: List[Dict[str, Any]]) -> str:
    """The instructions added to the scenario prompt."""
    if not axes:
        return ("The evidence leaves no obvious open question, so make the three scenarios differ in at least two real ways "
                "(for example the order of the key actions, who does what, or how a disputed fact is read), and say which in differs_by.")
    lines = ["OPEN QUESTIONS the evidence leaves unsettled (found by the system):"]
    for a in axes:
        lines.append(f"- {a['question']}  Options: " + "  |  ".join(f"[{o['id']}] {o['text']} ({o['support']} supported)" for o in a["options"]))
    lines.append("\nEach scenario MUST take the position below, so that the three are different possibilities and not three tellings of one story:")
    for p in assignment:
        if not p["flips"]:
            lines.append(f"- Scenario {p['scenario']}: take the best-supported option on every open question.")
        else:
            lines.append(f"- Scenario {p['scenario']}: take the best-supported option on every open question EXCEPT: " + "; ".join(f"{f['question']} -> [{f['option']['id']}] {f['option']['text']}" for f in p["flips"]) +
                         ". Set \"less_supported\": true and explain in contradicted_points what weakens it.")
    lines.append("Never turn a named real person from the evidence into a suspect unless the evidence itself points at them. For an inside-knowledge "
                 "scenario use an unnamed 'person with inside knowledge' and say what in the evidence suggests it.")
    lines.append("Give each scenario a \"differs_by\": one short sentence saying what is different about it. The scenarios must differ in what people do "
                 "(entry, who is involved, the order of the key actions), not only in wording or timing.")
    return "\n".join(lines)


# ---------------------------------------------------------------- measuring difference

_KEY_ACTIONS = {"damage", "take_item", "unlock", "open", "hand_over", "restrain", "struggle", "drop_item"}


def signature(scn: Dict[str, Any], layout: Dict[str, Any]) -> Dict[str, Any]:
    ext_ids = {o["id"] for o in layout.get("openings", []) if o.get("kind") == "external"}
    plan = scn["plan"]
    suspects = [a for a in plan["actors"] if a.get("role") == "suspect"] or plan["actors"][:1]
    entry = sorted({d["id"] for d in plan.get("doors_used", []) if d["id"] in ext_ids and d.get("actor") in {a["id"] for a in suspects}})
    nodes, seq, items = set(), [], set()
    for a in suspects:
        for st in a["steps"]:
            nodes.add(st["node_id"])
            if st["action"] in _KEY_ACTIONS:
                seq.append(f"{st['action']}@{st['node_id']}")
            if st.get("item"):
                items.add(st["item"].lower())
    origin = None
    ca = scn.get("time", {}).get("clock_anchors") or []
    if ca:
        origin = ca[0]["sod"] - ca[0]["t_model"]
    return {"entry": entry, "suspects": len(suspects), "nodes": sorted(nodes), "seq": seq, "items": sorted(items), "clock_origin": origin}


def _jaccard_distance(a, b) -> float:
    a, b = set(a), set(b)
    return 0.0 if not a and not b else 1.0 - len(a & b) / len(a | b)


def _edit_distance(a: List[str], b: List[str]) -> float:
    if not a and not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] / max(len(a), len(b))


def distance(sa: Dict[str, Any], sb: Dict[str, Any]) -> Tuple[float, List[str]]:
    """0 = the same story, 1 = nothing in common. Also says in what ways they differ."""
    parts = [
        ("entry", 0.25, _jaccard_distance(sa["entry"], sb["entry"])),
        ("number of people", 0.20, 0.0 if sa["suspects"] == sb["suspects"] else 1.0),
        ("places visited", 0.15, _jaccard_distance(sa["nodes"], sb["nodes"])),
        ("order of key actions", 0.25, _edit_distance(sa["seq"], sb["seq"])),
        ("items taken", 0.05, _jaccard_distance(sa["items"], sb["items"])),
        ("clock reading", 0.10, 0.0 if sa["clock_origin"] is None or sb["clock_origin"] is None else (1.0 if abs(sa["clock_origin"] - sb["clock_origin"]) > 120 else 0.0)),
    ]
    total = sum(w * d for _, w, d in parts)
    return round(total, 3), [name for name, w, d in parts if d * w >= 0.04]


def pairwise(scenarios: List[Dict[str, Any]], layout: Dict[str, Any]) -> List[Dict[str, Any]]:
    sigs = [signature(s, layout) for s in scenarios]
    out = []
    for i in range(len(scenarios)):
        for j in range(i + 1, len(scenarios)):
            d, ways = distance(sigs[i], sigs[j])
            out.append({"a": i, "b": j, "distance": d, "differs_in": ways, "too_similar": d < MIN_DISTANCE})
    return out


def near_duplicates(scenarios: List[Dict[str, Any]], layout: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in pairwise(scenarios, layout) if p["too_similar"]]


def repair_note(pairs: List[Dict[str, Any]], axes: List[Dict[str, Any]]) -> str:
    """What to tell the model when scenarios came back too alike."""
    bits = [f"scenarios {p['a'] + 1} and {p['b'] + 1} are almost the same story (difference score {p['distance']:.2f})" for p in pairs]
    return ("Your previous answer was too repetitive: " + "; ".join(bits) + ". Make them genuinely different possibilities: a different entry, a different number or choice of "
            "people, a different order of the key actions, or a different reading of a disputed fact. Do not just reword or change timings.")
