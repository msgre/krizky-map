"""Tests for krizky_map.geojson — build_feature_collection + bounds + write."""

from __future__ import annotations

import json

import pytest

from krizky_map.geojson import (
    DEFAULT_FIELDS,
    bounds_from_feature_collection,
    build_feature_collection,
    write_geojson,
)


# ---------------------------------------------------------------------------
# build_feature_collection
# ---------------------------------------------------------------------------

def test_build_feature_collection_basic():
    records = [{"slug": "a", "nazev": "A", "latitude": 49.5, "longitude": 17.9}]
    fc = build_feature_collection(records, None)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    assert f["type"] == "Feature"
    assert f["geometry"] == {"type": "Point", "coordinates": [17.9, 49.5]}
    assert f["properties"]["slug"] == "a"
    assert f["properties"]["nazev"] == "A"


def test_build_feature_collection_skips_records_without_coords():
    records = [
        {"slug": "a", "latitude": 49.5, "longitude": 17.9},
        {"slug": "b", "latitude": None, "longitude": None},
        {"slug": "c", "latitude": 50.0, "longitude": 18.0},
        {"slug": "d"},
    ]
    fc = build_feature_collection(records, None)
    assert len(fc["features"]) == 2
    slugs = [f["properties"]["slug"] for f in fc["features"]]
    assert slugs == ["a", "c"]


def test_build_feature_collection_skips_non_numeric_coords():
    records = [{"slug": "a", "latitude": "bad", "longitude": "worse"}]
    fc = build_feature_collection(records, None)
    assert fc["features"] == []


def test_build_feature_collection_string_coords_parsed():
    records = [{"slug": "a", "latitude": "49.5", "longitude": "17.9"}]
    fc = build_feature_collection(records, None)
    assert fc["features"][0]["geometry"]["coordinates"] == [17.9, 49.5]


def test_build_feature_collection_fields_control_properties():
    records = [{"slug": "a", "nazev": "X", "umisteni": "Y", "hidden": "Z",
                "latitude": 49.5, "longitude": 17.9}]
    fc = build_feature_collection(records, ["nazev"])
    assert fc["features"][0]["properties"] == {"nazev": "X", "slug": "a"}


def test_build_feature_collection_always_includes_slug():
    """slug se do properties přidá i když ve fields chybí (primární klíč)."""
    records = [{"slug": "a", "nazev": "X", "latitude": 49.5, "longitude": 17.9}]
    fc = build_feature_collection(records, ["nazev"])
    assert "slug" in fc["features"][0]["properties"]


def test_build_feature_collection_default_fields_when_none():
    records = [{"slug": "a", "nazev": "X", "umisteni": "Y",
                "latitude": 49.5, "longitude": 17.9}]
    fc = build_feature_collection(records, None)
    props = fc["features"][0]["properties"]
    for k in DEFAULT_FIELDS:
        assert k in props


def test_build_feature_collection_custom_lat_lng_fields():
    records = [{"slug": "a", "lat": 49.5, "lng": 17.9}]
    fc = build_feature_collection(records, ["slug"], lat_field="lat", lng_field="lng")
    assert fc["features"][0]["geometry"]["coordinates"] == [17.9, 49.5]


def test_build_feature_collection_bbox_present():
    records = [
        {"slug": "a", "latitude": 49.5, "longitude": 17.9},
        {"slug": "b", "latitude": 50.1, "longitude": 18.2},
        {"slug": "c", "latitude": 49.2, "longitude": 17.5},
    ]
    fc = build_feature_collection(records, None)
    assert fc["bbox"] == [17.5, 49.2, 18.2, 50.1]  # [minLng, minLat, maxLng, maxLat]


def test_build_feature_collection_empty_records_no_bbox():
    fc = build_feature_collection([], None)
    assert fc["features"] == []
    assert "bbox" not in fc


# ---------------------------------------------------------------------------
# bounds_from_feature_collection
# ---------------------------------------------------------------------------

def test_bounds_from_bbox():
    fc = {"type": "FeatureCollection", "features": [], "bbox": [17.5, 49.2, 18.2, 50.1]}
    assert bounds_from_feature_collection(fc) == [[49.2, 17.5], [50.1, 18.2]]


def test_bounds_computed_when_no_bbox():
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [17.5, 49.2]}, "properties": {}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [18.2, 50.1]}, "properties": {}},
    ]}
    assert bounds_from_feature_collection(fc) == [[49.2, 17.5], [50.1, 18.2]]


def test_bounds_none_for_empty():
    assert bounds_from_feature_collection({"features": []}) is None


# ---------------------------------------------------------------------------
# write_geojson
# ---------------------------------------------------------------------------

def test_write_geojson_creates_maps_dir(tmp_path):
    fc = {"type": "FeatureCollection", "features": []}
    dst = write_geojson(fc, tmp_path, "vsechna-mista")
    assert dst == tmp_path / "maps" / "vsechna-mista.geojson"
    assert json.loads(dst.read_text(encoding="utf-8")) == fc


def test_write_geojson_compact_output(tmp_path):
    """Bez zbytečných mezer a newlines — menší output."""
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [17.9, 49.5]}, "properties": {"slug": "a"}},
    ]}
    dst = write_geojson(fc, tmp_path, "x")
    raw = dst.read_text(encoding="utf-8")
    assert "\n" not in raw
    assert ", " not in raw and ": " not in raw
