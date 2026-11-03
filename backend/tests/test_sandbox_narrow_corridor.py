"""A 1 m door must stay 1 m wide in the wall of a 1.5 m corridor; the usual margin is only reduced where the wall is too short for it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import sandbox_geometry as sg  # noqa: E402


def layout(corridor_len_w=1.5):
    return sg.build_layout({
        "rooms": [
            {"id": "corridor", "width_m": 9, "length_m": corridor_len_w},
            {"id": "store", "width_m": 3, "length_m": 3, "attach": {"to": "corridor", "wall": "east", "align_frac": 0.5}},
            {"id": "lobby", "width_m": 3, "length_m": 3, "attach": {"to": "corridor", "wall": "west", "align_frac": 0.5}},
        ],
        "connections": [{"id": "store_door", "room_a": "corridor", "room_b": "store", "width_m": 1.0, "position_frac": 0.5, "state": "unknown"},
                        {"id": "lobby_open", "room_a": "corridor", "room_b": "lobby", "width_m": 1.5, "position_frac": 0.5, "state": "open"}],
        "entry_points": [{"id": "front", "room": "lobby", "wall": "west", "position_frac": 0.5, "width_m": 1.0, "state": "unknown"}],
    }, set())


def test_doors_in_a_short_shared_wall_are_not_squeezed_to_half_a_metre():
    lay = layout()
    ops = {o["id"]: o for o in lay["openings"]}
    assert ops["store_door"]["width_m"] >= 0.99 and ops["store_door"]["passable"]
    assert ops["lobby_open"]["width_m"] >= 0.99 and ops["lobby_open"]["passable"]


def test_a_person_can_now_walk_from_outside_to_the_store():
    lay = layout()
    assert not [w for w in lay["warnings"] if "too narrow" in w]


def test_long_walls_keep_the_full_margin_as_before():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 10, "length_m": 10}, {"id": "b", "width_m": 10, "length_m": 10, "attach": {"to": "a", "wall": "east"}}],
                           "connections": [{"id": "d", "room_a": "a", "room_b": "b", "width_m": 1.0, "position_frac": 0.0, "state": "open"}]}, set())
    d = next(o for o in lay["openings"] if o["id"] == "d")
    assert d["width_m"] == 1.0 and d["gap_center_m"] >= -5 + 0.5 + 0.5 - 1e-6      # still keeps 0.5 m of solid wall beside it
