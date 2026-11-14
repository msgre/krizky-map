"""Tests for krizky_map.plugin — hook wiring, config resolution, asset copy."""

import json

from krizky_map.plugin import MapPlugin, _label_field, _panel_config, _resolve_tile

# ---------------------------------------------------------------------------
# _resolve_tile
# ---------------------------------------------------------------------------


def test_resolve_tile_default_osm():
    tile = _resolve_tile({})
    assert "openstreetmap.org" in tile["url"]
    assert tile["max_zoom"] == 19


def test_resolve_tile_osm_hot():
    tile = _resolve_tile({"tile": {"provider": "osm-hot"}})
    assert "tile.openstreetmap.fr" in tile["url"]


def test_resolve_tile_cartodb():
    tile = _resolve_tile({"tile": {"provider": "cartodb-positron"}})
    assert "basemaps.cartocdn.com" in tile["url"]
    assert "light_all" in tile["url"]


def test_resolve_tile_custom_overrides():
    """User can supply own url/attribution/subdomains."""
    tile = _resolve_tile(
        {
            "tile": {
                "provider": "custom",
                "url": "https://tiles.example.com/{z}/{x}/{y}.png",
                "attribution": "MyMap",
                "subdomains": [],
            }
        }
    )
    assert tile["url"].startswith("https://tiles.example.com")
    assert tile["attribution"] == "MyMap"


def test_resolve_tile_partial_override_preserves_preset():
    """Overriding just attribution keeps preset URL."""
    tile = _resolve_tile({"tile": {"provider": "osm", "attribution": "Custom"}})
    assert "openstreetmap.org" in tile["url"]
    assert tile["attribution"] == "Custom"


# ---------------------------------------------------------------------------
# inject_head / inject_body_end — page.map opt-in
# ---------------------------------------------------------------------------


def _config(map_extra=None):
    site = {
        "map": {
            "leaflet": {"js": "/assets/leaflet/leaflet.js", "css": "/assets/leaflet/leaflet.css"},
            "markercluster": {
                "js": "/assets/leaflet/markercluster.js",
                "css": "/assets/leaflet/MarkerCluster.css",
            },
        }
    }
    if map_extra:
        site["map"].update(map_extra)
    return {"site": site}


def test_inject_head_none_when_page_has_no_map():
    plugin = MapPlugin()
    assert plugin.inject_head(page_cfg={}, config=_config()) is None
    assert plugin.inject_head(page_cfg={"map": False}, config=_config()) is None


def test_inject_head_emits_css_and_preconnect_when_map_true():
    plugin = MapPlugin()
    html = plugin.inject_head(page_cfg={"map": True}, config=_config())
    assert '<link rel="preconnect"' in html
    assert "leaflet.css" in html
    assert "MarkerCluster.css" in html
    assert "/krizky-map/map.css" in html


def test_inject_body_end_emits_scripts_when_map_true():
    plugin = MapPlugin()
    html = plugin.inject_body_end(page_cfg={"map": True}, config=_config())
    assert "leaflet.js" in html
    assert "markercluster.js" in html
    assert "/krizky-map/map.js" in html


def test_inject_body_end_none_without_leaflet_config():
    """No leaflet.js → plugin warns and returns None (map can't work)."""
    plugin = MapPlugin()
    cfg = {"site": {"map": {}}}
    assert plugin.inject_body_end(page_cfg={"map": True}, config=cfg) is None


# ---------------------------------------------------------------------------
# after_page_written — writes geojson for non-detail pages
# ---------------------------------------------------------------------------


def test_after_page_written_generates_geojson(tmp_path):
    plugin = MapPlugin()
    records = [
        {"slug": "a", "nazev": "A", "latitude": 49.5, "longitude": 17.9},
        {"slug": "b", "nazev": "B", "latitude": 50.0, "longitude": 18.0},
    ]
    plugin.after_page_written(
        page_cfg={"map": True},
        html_path="/vsechna-mista.html",
        output_dir=tmp_path,
        records=records,
        config=_config(),
    )
    dst = tmp_path / "maps" / "vsechna-mista.geojson"
    assert dst.exists()
    fc = json.loads(dst.read_text(encoding="utf-8"))
    assert len(fc["features"]) == 2


def test_after_page_written_respects_page_fields(tmp_path):
    plugin = MapPlugin()
    records = [{"slug": "a", "nazev": "A", "hidden": "X", "latitude": 49.5, "longitude": 17.9}]
    plugin.after_page_written(
        page_cfg={"map": {"fields": ["nazev"]}},
        html_path="/x.html",
        output_dir=tmp_path,
        records=records,
        config=_config(),
    )
    props = json.loads((tmp_path / "maps" / "x.geojson").read_text())["features"][0]["properties"]
    assert set(props.keys()) == {"slug", "nazev"}
    assert "hidden" not in props


def test_after_page_written_adds_category_field_to_properties(tmp_path):
    """When markers.category_field is set, it's implicitly added to props."""
    plugin = MapPlugin()
    records = [
        {
            "slug": "a",
            "nazev": "A",
            "kategorie_slug": "kriz",
            "kategorie": "Kříž",
            "latitude": 49.5,
            "longitude": 17.9,
        }
    ]
    plugin.after_page_written(
        page_cfg={"map": {"fields": ["nazev"]}},
        html_path="/x.html",
        output_dir=tmp_path,
        records=records,
        config=_config({"markers": {"category_field": "kategorie_slug"}}),
    )
    props = json.loads((tmp_path / "maps" / "x.geojson").read_text())["features"][0]["properties"]
    assert props["kategorie_slug"] == "kriz"
    # Label field ("kategorie") is auto-derived from "kategorie_slug" and added too.
    assert props["kategorie"] == "Kříž"


def test_after_page_written_adds_subtitle_field_to_properties(tmp_path):
    """popup.subtitle_field is auto-included in geojson properties."""
    plugin = MapPlugin()
    records = [
        {"slug": "a", "nazev": "A", "umisteni": "Krhová", "latitude": 49.5, "longitude": 17.9}
    ]
    plugin.after_page_written(
        page_cfg={"map": {"fields": ["nazev"]}},
        html_path="/x.html",
        output_dir=tmp_path,
        records=records,
        config=_config({"popup": {"subtitle_field": "umisteni"}}),
    )
    props = json.loads((tmp_path / "maps" / "x.geojson").read_text())["features"][0]["properties"]
    assert props["umisteni"] == "Krhová"


def test_runtime_map_config_exposes_subtitle_field():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({"popup": {"subtitle_field": "umisteni"}})
    assert cfg["popup"]["subtitle_field"] == "umisteni"


def test_runtime_map_config_subtitle_defaults_to_none():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({})
    assert cfg["popup"]["subtitle_field"] is None


# ---------------------------------------------------------------------------
# panel.thumbnail (map_full side panel photo)
# ---------------------------------------------------------------------------


def test_panel_config_defaults():
    cfg = _panel_config({})
    assert cfg == {
        "thumbnail_field": None,
        "thumbnail_size": "thumb",
        "thumbnail_format": "jpg",
        "thumbnail_pad": 3,
    }


def test_panel_config_user_overrides():
    cfg = _panel_config(
        {
            "thumbnail_field": "id_radku",
            "thumbnail_size": "medium",
            "thumbnail_format": "webp",
            "thumbnail_pad": 4,
        }
    )
    assert cfg["thumbnail_field"] == "id_radku"
    assert cfg["thumbnail_size"] == "medium"
    assert cfg["thumbnail_format"] == "webp"
    assert cfg["thumbnail_pad"] == 4


def test_runtime_map_config_exposes_panel_and_photos_base_url(tmp_path):
    plugin = MapPlugin()
    # Simulate prepare_jinja2_environment side effect (photos base url resolved).
    plugin._photos_base_url = "https://photos.example.com"
    cfg = plugin._runtime_map_config({"panel": {"thumbnail_field": "id_radku"}})
    assert cfg["panel"]["thumbnail_field"] == "id_radku"
    assert cfg["photos_base_url"] == "https://photos.example.com"


def test_after_page_written_adds_thumbnail_field_to_properties(tmp_path):
    """panel.thumbnail_field is auto-included in geojson properties."""
    plugin = MapPlugin()
    records = [{"slug": "a", "nazev": "A", "id_radku": 7, "latitude": 49.5, "longitude": 17.9}]
    plugin.after_page_written(
        page_cfg={"map": {"fields": ["nazev"]}},
        html_path="/x.html",
        output_dir=tmp_path,
        records=records,
        config=_config({"panel": {"thumbnail_field": "id_radku"}}),
    )
    props = json.loads((tmp_path / "maps" / "x.geojson").read_text())["features"][0]["properties"]
    assert props["id_radku"] == 7


def test_after_page_written_respects_explicit_label_field(tmp_path):
    """User can override auto-derive with markers.category_label_field."""
    plugin = MapPlugin()
    records = [
        {
            "slug": "a",
            "nazev": "A",
            "typ_slug": "kriz",
            "typ_display": "Křížek",
            "latitude": 49.5,
            "longitude": 17.9,
        }
    ]
    plugin.after_page_written(
        page_cfg={"map": True},
        html_path="/x.html",
        output_dir=tmp_path,
        records=records,
        config=_config(
            {
                "markers": {
                    "category_field": "typ_slug",
                    "category_label_field": "typ_display",
                }
            }
        ),
    )
    props = json.loads((tmp_path / "maps" / "x.geojson").read_text())["features"][0]["properties"]
    assert props["typ_slug"] == "kriz"
    assert props["typ_display"] == "Křížek"


# ---------------------------------------------------------------------------
# _label_field auto-derive
# ---------------------------------------------------------------------------


def test_label_field_trims_slug_suffix():
    assert _label_field({"category_field": "kategorie_slug"}) == "kategorie"
    assert _label_field({"category_field": "typ_slug"}) == "typ"


def test_label_field_explicit_wins():
    assert (
        _label_field(
            {
                "category_field": "kategorie_slug",
                "category_label_field": "kategorie_nazev",
            }
        )
        == "kategorie_nazev"
    )


def test_label_field_without_suffix_returns_same():
    assert _label_field({"category_field": "kategorie"}) == "kategorie"


def test_label_field_none_when_nothing_configured():
    assert _label_field({}) is None


def test_runtime_map_config_exposes_label_field(tmp_path):
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({"markers": {"category_field": "kategorie_slug"}})
    assert cfg["markers"]["category_label_field"] == "kategorie"


def test_runtime_map_config_active_color_default_none():
    plugin = MapPlugin()
    assert plugin._runtime_map_config({})["markers"]["active_color"] is None


def test_runtime_map_config_exposes_active_color():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({"markers": {"color": "#5E0000", "active_color": "#850000"}})
    assert cfg["markers"]["color"] == "#5E0000"
    assert cfg["markers"]["active_color"] == "#850000"


# ---------------------------------------------------------------------------
# fit_on_filter
# ---------------------------------------------------------------------------


def test_fit_on_filter_default_false():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({})
    assert cfg["fit_on_filter"] is False


def test_fit_on_filter_true_when_enabled():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({"fit_on_filter": True})
    assert cfg["fit_on_filter"] is True


def test_fit_on_filter_coerces_truthy_to_bool():
    """User can accidentally write `fit_on_filter: yes` (YAML) — coerce to bool."""
    plugin = MapPlugin()
    assert plugin._runtime_map_config({"fit_on_filter": 1})["fit_on_filter"] is True
    assert plugin._runtime_map_config({"fit_on_filter": ""})["fit_on_filter"] is False


def test_fit_padding_default_symmetric():
    plugin = MapPlugin()
    assert plugin._runtime_map_config({})["fit_padding"] == [30, 30, 30, 30]


def test_fit_padding_asymmetric_override():
    plugin = MapPlugin()
    cfg = plugin._runtime_map_config({"fit_padding": [30, 30, 120, 30]})
    assert cfg["fit_padding"] == [30, 30, 120, 30]


def test_after_page_written_skips_detail_pages(tmp_path):
    """Detail pages get data inlined into data-* attrs, no geojson needed."""
    plugin = MapPlugin()
    plugin.after_page_written(
        page_cfg={"map": True, "detail": True},
        html_path="/a.html",
        output_dir=tmp_path,
        records=[{"slug": "a", "latitude": 49.5, "longitude": 17.9}],
        config=_config(),
    )
    assert not (tmp_path / "maps").exists()


def test_core_plugin_helpers_importable():
    from krizky.plugin_helpers import register_plugin_templates, replace_tree, resolve_path

    assert callable(register_plugin_templates)
    assert callable(replace_tree)
    assert callable(resolve_path)


def test_copy_plugin_assets_copies_js_and_css(tmp_path):
    plugin = MapPlugin()
    plugin.copy_plugin_assets(output_dir=tmp_path, config=_config(), config_dir=tmp_path)
    assert (tmp_path / "krizky-map" / "map.js").exists()
    assert (tmp_path / "krizky-map" / "map.css").exists()


def test_copy_plugin_assets_copies_mask_and_overlays(tmp_path):
    plugin = MapPlugin()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "valassko.geojson").write_text('{"type":"Feature"}', encoding="utf-8")
    (tmp_path / "data" / "kostely.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
    )
    cfg = _config(
        {
            "mask": {"polygon": "data/valassko.geojson"},
            "overlays": [{"source": "data/kostely.geojson", "style": {"type": "circle"}}],
        }
    )
    plugin._config_dir = tmp_path
    plugin._register_data_urls(cfg["site"]["map"])
    out = tmp_path / "output"
    plugin.copy_plugin_assets(output_dir=out, config=cfg, config_dir=tmp_path)
    assert (out / "krizky-map" / "mask.geojson").exists()
    assert (out / "krizky-map" / "overlay-0.geojson").exists()
    assert cfg["site"]["map"]["mask"]["_public_url"] == "/krizky-map/mask.geojson"
    assert cfg["site"]["map"]["overlays"][0]["_public_url"] == "/krizky-map/overlay-0.geojson"


def test_copy_plugin_assets_skips_missing_source(tmp_path):
    plugin = MapPlugin()
    cfg = _config(
        {
            "mask": {"polygon": "data/missing.geojson"},
            "overlays": [{"source": "data/missing-overlay.geojson"}],
        }
    )
    plugin.copy_plugin_assets(output_dir=tmp_path, config=cfg, config_dir=tmp_path)
    assert (tmp_path / "krizky-map" / "map.js").exists()
    assert not (tmp_path / "krizky-map" / "mask.geojson").exists()
    assert not (tmp_path / "krizky-map" / "overlay-0.geojson").exists()


def test_copy_plugin_assets_works_without_config_dir(tmp_path):
    plugin = MapPlugin()
    plugin.copy_plugin_assets(output_dir=tmp_path, config=_config(), config_dir=None)
    assert (tmp_path / "krizky-map" / "map.js").exists()


def test_copy_plugin_assets_removes_stale_files(tmp_path):
    stale = tmp_path / "krizky-map" / "overlay-5.geojson"
    stale.parent.mkdir()
    stale.write_text("{}", encoding="utf-8")
    MapPlugin().copy_plugin_assets(output_dir=tmp_path, config=_config(), config_dir=tmp_path)
    assert not stale.exists()
    assert (tmp_path / "krizky-map" / "map.js").exists()


def test_after_page_written_does_not_copy_assets(tmp_path):
    MapPlugin().after_page_written(
        page_cfg={"map": True},
        html_path="/x.html",
        output_dir=tmp_path,
        records=[],
        config=_config(),
    )
    assert not (tmp_path / "krizky-map").exists()


def test_prepare_jinja2_environment_registers_templates_once(tmp_path):
    from jinja2 import ChoiceLoader, Environment, FileSystemLoader

    from krizky_map.plugin import _PLUGIN_TEMPLATES

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    env = Environment(loader=ChoiceLoader([FileSystemLoader(str(a)), FileSystemLoader(str(b))]))
    plugin = MapPlugin()
    plugin.prepare_jinja2_environment(env, _config(), tmp_path)
    plugin.prepare_jinja2_environment(env, _config(), tmp_path)
    loaders = env.loader.loaders
    matches = [
        i
        for i, ldr in enumerate(loaders)
        if isinstance(ldr, FileSystemLoader) and str(_PLUGIN_TEMPLATES) in ldr.searchpath
    ]
    assert matches == [1]
    assert len(loaders) == 3
    assert "map_config" in env.globals


def test_register_data_urls_before_first_render(tmp_path):
    """map_config exposes mask.url on the first template render (pre-copy)."""
    plugin = MapPlugin()
    plugin._config_dir = tmp_path
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "valassko.geojson").write_text("{}", encoding="utf-8")
    map_cfg = {"mask": {"polygon": "data/valassko.geojson"}}
    plugin._register_data_urls(map_cfg)
    exposed = plugin._runtime_map_config(map_cfg)
    assert exposed["mask"]["url"] == "/krizky-map/mask.geojson"
