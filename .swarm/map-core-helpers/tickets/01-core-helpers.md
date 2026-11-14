---
id: "01"
slug: core-helpers
title: Přechod na core 0.2 (plugin_helpers a hook copy_plugin_assets)
status: done
depends_on: []
files:
  - pyproject.toml
  - uv.lock
  - krizky_map/plugin.py
  - tests/test_plugin.py
  - README.md
attempts: 1
pr: "2"
---

## Cíl
Plugin přestane duplikovat kód, který teď nabízí core 0.2: registraci šablon (`register_plugin_templates`), kopírování assetů s vlastním hlídáním opakování (hook `copy_plugin_assets` + `replace_tree`) a převod cest z configu (`resolve_path`). Celá specifikace `.swarm/map-core-helpers/spec.md` (části 1–4) je jeden tiket, protože všechny části mění stejné soubory (`plugin.py`, `tests/test_plugin.py`) a část 1 je předpokladem ostatních.

## Akceptační kritéria
- `pyproject.toml` má `krizky>=0.2`. `uv.lock` obsahuje balík `krizky` ve verzi 0.2.0 nebo vyšší (vzniklo přes `uv lock --upgrade-package krizky`). Core `origin/main` repa `msgre/krizky` už `krizky/plugin_helpers.py` i hook `copy_plugin_assets` obsahuje.
- `prepare_jinja2_environment` volá `register_plugin_templates(env, _PLUGIN_TEMPLATES)`. Zbytek hooku (`map_config`, `map_bounds`, registrace URL masky a overlayů, `photos_base_url`) zůstává beze změny.
- `git grep -n ChoiceLoader -- krizky_map/plugin.py` nic nenajde. Import `FileSystemLoader` z `plugin.py` také zmizí (nic jiného ho nepoužívá).
- Nový `@hookimpl def copy_plugin_assets(self, output_dir, config, config_dir)`:
  - nejdřív `replace_tree(_PLUGIN_ASSETS / "krizky-map", Path(output_dir) / "krizky-map")`,
  - pak zkopíruje masku `site.map.mask.polygon` do `krizky-map/mask.geojson` a overlaye `site.map.overlays[i].source` do `krizky-map/overlay-<i>.geojson`; cesty převádí `resolve_path(..., config_dir)` (parametr hooku). Chybějící zdrojový soubor se tiše přeskočí.
- `after_page_written` nic nekopíruje, jen zapisuje GeoJSON (logika polí a přeskočení detailu beze změny).
- `git grep -n -e _copy_assets -e _assets_copied -e _resolve_source_path -- ':!.swarm'` nic nenajde.
- `_register_data_urls` používá `resolve_path(..., self._config_dir)`, kde `self._config_dir` se ukládá v `prepare_jinja2_environment`.
- Docstring třídy `MapPlugin` (seznam hooků) obsahuje `copy_plugin_assets` a u `after_page_written` už nezmiňuje kopírování.
- `README.md`: komentář u `map: true` neříká, že zapíná kopírování assetů (zapíná vložení CSS/JS do stránky a generování GeoJSON). Někde v sekci Konfigurace nebo Chování je zmínka, že `output/krizky-map/` (map.js, map.css, maska, overlaye) je ve výstupu vždy a při každém buildu se vytvoří znovu.
- `scripts/verify` skončí s exit 0.

## Testy
Nejdřív (TDD, v `tests/test_plugin.py`) napiš testy, které na současném kódu selžou:
1. `test_core_plugin_helpers_importable`: `from krizky.plugin_helpers import register_plugin_templates, replace_tree, resolve_path` projde (ověří bump závislosti).
2. `test_copy_plugin_assets_copies_js_and_css`: po `plugin.copy_plugin_assets(output_dir=tmp_path, config=_config(), config_dir=tmp_path)` existují `tmp_path/krizky-map/map.js` a `map.css`.
3. `test_copy_plugin_assets_copies_mask_and_overlays`: maska a overlay s cestami relativními ke `config_dir` (např. `data/valassko.geojson`) skončí jako `mask.geojson` a `overlay-0.geojson`.
4. `test_copy_plugin_assets_skips_missing_source`: maska/overlay ukazující na neexistující soubor nevyhodí výjimku a cílový soubor nevznikne.
5. `test_copy_plugin_assets_removes_stale_files`: soubor předem vytvořený v `output_dir/krizky-map/` (např. `overlay-5.geojson`) po volání zmizí.
6. `test_after_page_written_does_not_copy_assets`: `after_page_written` se stránkou `map: True` nevytvoří `output_dir/krizky-map/`.
7. `test_prepare_jinja2_environment_registers_templates_once`: `Environment(loader=ChoiceLoader([FileSystemLoader(a), FileSystemLoader(b)]))`, dvakrát zavolaný `prepare_jinja2_environment(env, config, config_dir)` vloží loader se `_PLUGIN_TEMPLATES` právě jednou, na index 1, a nastaví `env.globals["map_config"]`.

Pak uprav stávající testy: `test_after_page_written_copies_assets`, `test_after_page_written_copies_mask_polygon` a `test_after_page_written_copies_overlays` převeď na `copy_plugin_assets` (nebo je nahraď testy 2 a 3). `test_assets_copied_only_once` odstraň, protože opakování hlídá core. `test_register_data_urls_before_first_render` musí dál projít.

## Poznámky
- Guidelines: `/Users/msgre/projects/muzeum/krizky/docs/guidelines/python.md` (žádné `from __future__ import annotations`, logging přes `_log`), `docs-sync.md`.
- API core (`krizky/plugin_helpers.py` v `origin/main`): `register_plugin_templates(env, templates_dir)` vkládá na index 1 a je idempotentní; `replace_tree(source, target)` smaže cíl a zkopíruje strom; `resolve_path(path, config_dir)` vrací `None` pro `None`/`""`, jinak absolutní `Path` (relativní vůči `config_dir`, pak `.resolve()`).
- `resolve_path` vyžaduje `config_dir`, zatímco dnešní `_resolve_source_path` při `self._config_dir is None` vracel cestu beze změny. V `_register_data_urls` proto řeš `None` (např. předej `self._config_dir or Path.cwd()`), aby testy volající `_register_data_urls` bez `prepare_jinja2_environment` nespadly. Stejně tak `copy_plugin_assets` by neměl spadnout, když `config_dir` je `None`.
- Kopírování masky a overlayů musí proběhnout až po `replace_tree`, jinak je smaže.
- `_PLUGIN_ASSETS / "krizky-map"` obsahuje jen `map.js` a `map.css`; nic dalšího do ní nepřidávej.
- `uv lock --upgrade-package krizky` stáhne core z gitu (`tool.uv.sources`), potřebuje síť. `uv.lock` neupravuj ručně.
- `_config()` je helper v `tests/test_plugin.py`, použij ho.
- Mimo rozsah: oddělení JS a statiky, čtení `sources.photos.base_url`.

## Otázky
