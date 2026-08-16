"""Sanity render of _map.html macros."""

from __future__ import annotations

import json

import pytest
from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from krizky_map.geojson import build_feature_collection, bounds_from_feature_collection
from krizky_map.plugin import _PLUGIN_TEMPLATES, MapPlugin


@pytest.fixture()
def env():
    e = Environment(loader=ChoiceLoader([FileSystemLoader(str(_PLUGIN_TEMPLATES))]), autoescape=True)
    plugin = MapPlugin()
    map_cfg = {
        "markers": {"category_field": "kategorie_slug", "icon_prefix": "i-kategorie-"},
        "popup": {"subtitle_field": "umisteni"},
    }
    e.globals["map_config"] = plugin._runtime_map_config(map_cfg)
    e.globals["map_bounds"] = lambda rs: bounds_from_feature_collection(build_feature_collection(rs or [], None))
    e.globals["page_urls"] = {"vsechna_mista": "/vsechna-mista.html", "mapa": "/mapa.html"}
    e.globals["page_name"] = "vsechna_mista"
    return e


# ---------------------------------------------------------------------------
# map_detail
# ---------------------------------------------------------------------------

def test_map_detail_renders_data_attrs(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "Kříž u Muzika",'
        '                "kategorie_slug": "kriz", "umisteni": "Krhová"}) }}'
    )
    out = tmpl.render()
    assert 'data-map-mode="detail"' in out
    assert 'data-map-lat="49.5"' in out
    assert 'data-map-lng="17.9"' in out
    assert 'data-map-name="Kříž u Muzika"' in out
    # category = slug (icon lookup); subtitle = display text under title in popup.
    assert 'data-map-category="kriz"' in out
    assert 'data-map-subtitle="Krhová"' in out
    assert 'style="height:360px"' in out


def test_map_detail_subtitle_absent_when_field_missing(env):
    """Bez subtitle field v recordu je data-map-subtitle prázdný."""
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "X", "kategorie_slug": "kriz"}) }}'
    )
    out = tmpl.render()
    assert 'data-map-subtitle=""' in out


def test_map_detail_explicit_subtitle(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "X"},'
        '              category="kriz", subtitle="Vlastní popisek") }}'
    )
    out = tmpl.render()
    assert 'data-map-category="kriz"' in out
    assert 'data-map-subtitle="Vlastní popisek"' in out


def test_map_detail_missing_coords_renders_nothing(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '[[[{{ map_detail({"latitude": none, "longitude": none, "nazev": "X"}) }}]]]'
    )
    out = tmpl.render()
    assert out.strip() == '[[[]]]'


def test_map_detail_category_override(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "X"}, category="socha") }}'
    )
    assert 'data-map-category="socha"' in tmpl.render()


def test_map_detail_custom_height_and_zoom(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "X"}, height="500px", zoom=17) }}'
    )
    out = tmpl.render()
    assert 'style="height:500px"' in out
    assert 'data-map-zoom="17"' in out


# ---------------------------------------------------------------------------
# map_list
# ---------------------------------------------------------------------------

def test_map_list_renders_empty_src_and_bounds(env):
    """Bez explicitního `src` je data-map-src prázdný — JS ho odvodí z location."""
    tmpl = env.from_string(
        '{% from "_map.html" import map_list %}'
        '{{ map_list(records) }}'
    )
    records = [
        {"slug": "a", "latitude": 49.5, "longitude": 17.9},
        {"slug": "b", "latitude": 50.0, "longitude": 18.0},
    ]
    out = tmpl.render(records=records)
    assert 'data-map-mode="list"' in out
    assert 'data-map-src=""' in out
    # bounds must be encoded as JSON array with autoescape (&#34; is escaped ")
    assert '[[49.5,' in out.replace('&#34;', '"').replace('&quot;', '"')


def test_map_list_no_records_no_bounds(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_list %}'
        '{{ map_list([]) }}'
    )
    out = tmpl.render()
    assert 'data-map-mode="list"' in out
    assert 'data-map-bounds=""' in out


def test_map_list_explicit_src(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_list %}'
        '{{ map_list([], src="/custom/path.geojson") }}'
    )
    assert 'data-map-src="/custom/path.geojson"' in tmpl.render()


def test_map_list_cluster_off(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_list %}'
        '{{ map_list([], cluster=false) }}'
    )
    assert 'data-map-cluster="0"' in tmpl.render()


# ---------------------------------------------------------------------------
# map_full
# ---------------------------------------------------------------------------

def test_map_full_renders_wrap_and_panel(env):
    env.globals["page_name"] = "mapa"
    tmpl = env.from_string(
        '{% from "_map.html" import map_full %}'
        '{{ map_full(records) }}'
    )
    records = [{"slug": "a", "latitude": 49.5, "longitude": 17.9}]
    out = tmpl.render(records=records)
    assert 'krizky-map-full-wrap' in out
    assert 'data-map-mode="full"' in out
    assert 'data-map-src=""' in out
    assert 'krizky-map-panel' in out
    assert 'data-map-locate' in out
    assert 'data-map-count' in out


def test_map_full_locate_off(env):
    env.globals["page_name"] = "mapa"
    tmpl = env.from_string(
        '{% from "_map.html" import map_full %}'
        '{{ map_full([], locate_button=false) }}'
    )
    out = tmpl.render()
    assert 'data-map-locate' not in out


def test_map_full_custom_panel_labels(env):
    env.globals["page_name"] = "mapa"
    tmpl = env.from_string(
        '{% from "_map.html" import map_full %}'
        '{{ map_full([], panel_label="Přehled", panel_hint="Klikni na pin.") }}'
    )
    out = tmpl.render()
    assert 'Přehled' in out
    assert 'Klikni na pin.' in out


# ---------------------------------------------------------------------------
# noscript fallback
# ---------------------------------------------------------------------------

def test_noscript_fallback_present(env):
    tmpl = env.from_string(
        '{% from "_map.html" import map_detail %}'
        '{{ map_detail({"latitude": 49.5, "longitude": 17.9, "nazev": "X"}) }}'
    )
    out = tmpl.render()
    assert '<noscript>' in out
    assert 'JavaScript' in out
