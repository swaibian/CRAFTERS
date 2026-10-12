"""SWE4 tests: CommandCatalog generic middle layer.

Ranking (exact id > id substring > label/id token > fuzzy) on the real
engine-registry shapes; "rotate"/"black and white"/"blend"/"duplicate"
queries; suggest() nearest-id hints; render() hint lines; tolerant
normalization of unknown/missing fields; params_from_message schema-driven
inference. No phrase→command-id knowledge anywhere — every expectation is
driven by the fixture registry entries themselves.
"""

from __future__ import annotations

import pytest

from controller.commands import (
    SHORT_PARAMS_LIMIT,
    CommandCatalog,
    keywords,
    params_from_message,
)

#: Engine-registry-shaped fixture (labels/menu/params mirror the real
#: photocraft `cmd!` registrations; blend modes are PARAM VALUES of one
#: layer command, never separate ids).
REGISTRY = [
    {
        "id": "image.imageRotation.90cw",
        "label": "90° Clockwise",
        "menu": ["Image", "Image Rotation"],
        "shortcut": None,
        "params": "{}",
        "enabled": True,
    },
    {
        "id": "image.imageRotation.90ccw",
        "label": "90° Counter Clockwise",
        "menu": ["Image", "Image Rotation"],
        "shortcut": None,
        "params": "{}",
        "enabled": True,
    },
    {
        "id": "image.imageRotation.180",
        "label": "180°",
        "menu": ["Image", "Image Rotation"],
        "shortcut": None,
        "params": "{}",
        "enabled": True,
    },
    {
        "id": "image.adjustments.desaturate",
        "label": "Desaturate",
        "menu": ["Image", "Adjustments"],
        "shortcut": "Cmd+Shift+U",
        "params": "{}",
        "enabled": True,
    },
    {
        "id": "image.adjustments.blackWhite",
        "label": "Black & White…",
        "menu": ["Image", "Adjustments"],
        "shortcut": "Cmd+Alt+Shift+B",
        "params": '{"reds":-200..300=40,"tint":bool=false,"tintColor":"#rrggbb"}',
        "enabled": True,
    },
    {
        "id": "layer.duplicate",
        "label": "Duplicate Layer…",
        "menu": ["Layer"],
        "shortcut": None,
        "params": '{"layer":id?} (no layer: every selected layer)',
        "enabled": True,
    },
    {
        "id": "layer.setProps",
        "label": "Layer Properties",
        "menu": ["Layer"],
        "shortcut": None,
        "params": (
            '{"layer":id?,"opacity":0..1?,"blend":"Normal|Multiply|Screen|'
            'Overlay|Darken|Lighten"?,"clipped":bool?}'
        ),
        "enabled": True,
    },
    {
        "id": "layer.layerStyle.blendingOptions",
        "label": "Blending Options…",
        "menu": ["Layer", "Layer Style"],
        "shortcut": None,
        "params": ('{"blend":"Normal|Multiply|Screen|Overlay|Soft Light|Hard Light"?}'),
        "enabled": True,
    },
    {
        "id": "filter.blur.gaussianBlur",
        "label": "Gaussian Blur…",
        "menu": ["Filter", "Blur"],
        "shortcut": None,
        "params": '{"radius":0.5..5000 px=1}',
        "enabled": False,
    },
]


def make_catalog():
    """Fresh catalog over the fixture registry."""
    return CommandCatalog([dict(entry) for entry in REGISTRY])


# --- search ranking ----------------------------------------------------------


def test_search_rotate_finds_rotation_ids():
    ids = [e["id"] for e in make_catalog().search("rotate")]
    assert ids
    assert all(i.startswith("image.imageRotation.") for i in ids[:3])
    assert "image.imageRotation.90cw" in ids


def test_search_rotation_id_substring_ranks_first():
    ids = [e["id"] for e in make_catalog().search("rotation")]
    assert ids[:3] == [
        "image.imageRotation.180",
        "image.imageRotation.90cw",
        "image.imageRotation.90ccw",
    ]


def test_search_black_and_white_matches_desaturation_family():
    catalog = make_catalog()
    ids = [e["id"] for e in catalog.search("black and white")]
    assert ids[0] == "image.adjustments.blackWhite"
    assert set(ids) & {"image.adjustments.desaturate", "image.adjustments.blackWhite"}
    assert catalog.search("desaturate")[0]["id"] == "image.adjustments.desaturate"


def test_search_blend_and_multiply_find_the_blend_commands():
    catalog = make_catalog()
    blend_ids = [e["id"] for e in catalog.search("blend")]
    assert set(blend_ids[:2]) == {
        "layer.setProps",
        "layer.layerStyle.blendingOptions",
    }
    multiply_ids = [e["id"] for e in catalog.search("multiply")]
    assert multiply_ids[0] == "layer.setProps"
    assert set(multiply_ids[:2]) == {
        "layer.setProps",
        "layer.layerStyle.blendingOptions",
    }


def test_search_duplicate_layer():
    assert make_catalog().search("duplicate")[0]["id"] == "layer.duplicate"
    assert make_catalog().search("duplicate layer")[0]["id"] == "layer.duplicate"


def test_search_exact_id_beats_everything():
    assert make_catalog().search("layer.duplicate")[0]["id"] == "layer.duplicate"
    assert (
        make_catalog().search("image.adjustments.blackWhite")[0]["id"]
        == "image.adjustments.blackWhite"
    )


def test_search_returns_compact_entries():
    entry = make_catalog().search("desaturate")[0]
    assert set(entry) == {"id", "label", "enabled", "params"}
    assert entry["label"] == "Desaturate"
    assert entry["enabled"] is True


def test_search_empty_query_and_no_match():
    catalog = make_catalog()
    assert catalog.search("") == []
    assert catalog.search("the picture please") == []
    assert catalog.search("zzzzqqqq") == []


# --- ranking against the REAL app registry dump -------------------------------


def _real_catalog():
    """Catalog over docs/live-command-registry.json (skip when absent)."""
    import json
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "docs"
        / ("live-command-registry.json")
    )
    if not path.exists():
        pytest.skip("no live registry dump")
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw["commands"] if isinstance(raw, dict) and "commands" in raw else raw
    return CommandCatalog(entries)


def test_search_subjective_photo_request_finds_named_tool():
    """'The faces are too bright… change the curves to reduce highlights'
    must surface the Curves command first — filler words ('think',
    'guess', 'a bit') must not drag in unrelated entries."""
    catalog = _real_catalog()
    hits = catalog.search(
        "I think the faces are too bright. I guess we need to change "
        "the curves a bit to reduce highlights."
    )
    assert hits, "subjective request must still match something"
    assert hits[0]["id"] == "image.adjustments.curves"


def test_search_named_tool_beats_params_text_coincidences():
    """A tool NAMED in the query outranks entries that merely mention the
    word in their params schema (e.g. 'curves' inside Camera Raw's doc)."""
    catalog = _real_catalog()
    ids = [e["id"] for e in catalog.search("change the curves a bit")]
    assert ids[0] == "image.adjustments.curves"
    if "filter.cameraRaw" in ids:
        assert ids.index("image.adjustments.curves") < ids.index("filter.cameraRaw")


def test_search_bright_prefers_brightness_over_right():
    """Prefix quality beats 1-edit noise: 'bright' → brightnessContrast,
    not rightEdges ('bright'↔'right' is one edit)."""
    catalog = _real_catalog()
    ids = [e["id"] for e in catalog.search("too bright")]
    assert "image.adjustments.brightnessContrast" in ids
    if "layer.align.rightEdges" in ids:
        assert ids.index("image.adjustments.brightnessContrast") < ids.index(
            "layer.align.rightEdges"
        )


def test_search_reduce_highlights_suggests_tone_tools():
    """'reduce highlights' → Shadows/Highlights family, not noise tools."""
    catalog = _real_catalog()
    ids = [e["id"] for e in catalog.search("reduce highlights")][:5]
    assert any(
        i in ids
        for i in (
            "image.adjustments.shadowsHighlights",
            "image.adjustments.curves",
            "filter.cameraRaw",
        )
    )


def test_search_huge_params_doc_is_shortened_but_verbatim_when_small():
    catalog = CommandCatalog(
        [{"id": "x.y", "label": "Xy", "params": "z" * (SHORT_PARAMS_LIMIT + 50)}]
    )
    entry = catalog.search("xy")[0]
    assert len(entry["params"]) <= SHORT_PARAMS_LIMIT
    assert entry["params"].endswith("…")
    small = make_catalog().search("desaturate")[0]
    assert small["params"] == "{}"


# --- suggest -----------------------------------------------------------------


def test_suggest_nearest_ids():
    catalog = make_catalog()
    assert catalog.suggest("image.adjustments.desatur")[0] == (
        "image.adjustments.desaturate"
    )
    assert catalog.suggest("layer.setProp")[0] == "layer.setProps"
    assert catalog.suggest("image.imageRotation.90cw")[0] == (
        "image.imageRotation.90cw"
    )


def test_suggest_limit_and_no_signal():
    catalog = make_catalog()
    hints = catalog.suggest("image.imageRotation.90cc", limit=2)
    assert len(hints) == 2
    assert hints[0] == "image.imageRotation.90ccw"
    assert catalog.suggest("") == []
    assert catalog.suggest("zzzzzzzzzzzz") == []


# --- render ------------------------------------------------------------------


def test_render_shape_and_disabled_marker():
    catalog = make_catalog()
    desat = next(e for e in REGISTRY if e["id"] == "image.adjustments.desaturate")
    assert catalog.render(desat) == "image.adjustments.desaturate — Desaturate ({})"
    blur = next(e for e in REGISTRY if e["id"] == "filter.blur.gaussianBlur")
    line = catalog.render(blur)
    assert line.startswith('filter.blur.gaussianBlur — Gaussian Blur… ({"radius"')
    assert line.endswith(" [disabled]")


def test_render_truncates_huge_params():
    line = CommandCatalog.render(
        {"id": "a.b", "label": "Ab", "params": "{" + "x" * 500 + "}"}
    )
    assert line.startswith("a.b — Ab ({")
    assert line.endswith("…)")
    assert len(line) < 200


def test_render_list_joins_lines():
    text = CommandCatalog.render_list(REGISTRY[:2])
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("image.imageRotation.90cw — 90° Clockwise")


# --- tolerant normalization --------------------------------------------------


def test_tolerant_of_unknown_fields_and_alt_spellings():
    catalog = CommandCatalog(
        [
            {
                "command": "x.y",
                "name": "Xy",
                "menu_path": "A / B",
                "parameters": {"k": 1},
                "available": False,
                "junk": object(),
            },
            {"id": "", "label": "no id"},
            "not-a-dict",
            {"id": "a.b", "title": "Ab", "menu": "Menu", "params": "{}"},
        ]
    )
    assert len(catalog) == 2
    found = catalog.search("xy")
    assert found and found[0]["id"] == "x.y"
    assert found[0]["enabled"] is False
    line = catalog.render({"command": "x.y", "name": "Xy", "available": False})
    assert line.endswith("[disabled]")
    plain = catalog.render({"id": "a.b", "title": "Ab", "params": "{}"})
    assert "[disabled]" not in plain


def test_accepts_wrapped_engine_commands_reply():
    for envelope in ({"commands": REGISTRY}, {"value": REGISTRY}, REGISTRY):
        catalog = CommandCatalog(envelope)
        assert catalog.search("duplicate")[0]["id"] == "layer.duplicate"


# --- keywords + params_from_message -----------------------------------------


def test_keywords_drop_stopwords_keep_layer():
    assert keywords("make the picture black & white") == ["black", "white"]
    assert keywords("please duplicate the layer") == ["duplicate", "layer"]
    assert keywords("do it") == []


def test_params_from_message_enum_and_numbers():
    assert params_from_message(
        '{"blend":"Normal|Multiply|Screen"}', "set blend mode to multiply"
    ) == {"blend": "Multiply"}
    assert params_from_message(
        '{"mode":"Soft Light|Hard Light"}', "use soft light please"
    ) == {"mode": "Soft Light"}
    assert params_from_message(
        '{"opacity":0..1?,"fill":0..1?}', "set opacity to 50"
    ) == {"opacity": 50}
    assert params_from_message('{"radius":0.5..5000 px=1}', "blur radius 3") == {
        "radius": 3
    }
    assert params_from_message("{}", "multiply") == {}
    assert params_from_message('{"layer":id?}', "duplicate layer") == {}
