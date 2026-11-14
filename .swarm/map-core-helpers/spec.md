# Specifikace: map-core-helpers

- **Repo:** `krizky-map`
- **Zdroj:** konsolidace do core, rozhodnuto 2026-11-13. Core v běhu `plugin-helpers` (`/Users/msgre/projects/muzeum/krizky/.swarm/plugin-helpers/spec.md`) přidal hook `copy_plugin_assets` a modul `krizky.plugin_helpers` s funkcemi `register_plugin_templates`, `replace_tree` a `resolve_path`. Core má verzi 0.2.0.
- **Předpoklad:** běh `plugin-helpers` je sloučený v `main` repa `msgre/krizky`.

## Cíl

Plugin přestane opakovat kód, který převzal core: registraci šablon, kopírování assetů s vlastním hlídáním opakování a převod cest z configu. Chování pro uživatele zůstane stejné, až na dvě změny popsané v části 3.

## 1. Závislost na core 0.2

- `pyproject.toml`: `krizky>=0.2`.
- `uv lock --upgrade-package krizky`, aby `uv.lock` obsahoval core s `plugin_helpers`.

**Akceptace:** `uv.lock` obsahuje `krizky` ve verzi 0.2.0 nebo vyšší a `from krizky.plugin_helpers import register_plugin_templates, replace_tree, resolve_path` v testech projde.

## 2. Registrace šablon

- `prepare_jinja2_environment` volá `register_plugin_templates(env, _PLUGIN_TEMPLATES)` místo vlastní manipulace s `ChoiceLoader`. Zbytek hooku (`map_config`, `map_bounds`, URL masky a overlayů) zůstává.
- Import `ChoiceLoader` a `FileSystemLoader` zmizí, pokud ho už nic nepotřebuje.

**Akceptace:** stávající testy registrace šablon projdou, v `plugin.py` není `ChoiceLoader`.

## 3. Kopírování assetů přes hook `copy_plugin_assets`

- Nový `@hookimpl copy_plugin_assets(self, output_dir, config, config_dir)`:
  - `replace_tree(_PLUGIN_ASSETS / "krizky-map", output_dir / "krizky-map")`,
  - potom zkopíruje masku (`mask.geojson`) a overlaye (`overlay-<i>.geojson`) stejně jako dnes, cesty převede přes `resolve_path(..., config_dir)`. Chybějící zdrojový soubor se dál tiše přeskočí.
- `after_page_written` už nic nekopíruje, jen zapisuje GeoJSON.
- Odstranit `_copy_assets`, `_assets_copied` a `_resolve_source_path`. `_register_data_urls` použije `resolve_path` s `config_dir` uloženým v `prepare_jinja2_environment`.

**Změny chování (záměrné):**
- Assety se zkopírují v každém buildu, i když žádná stránka mapu nepoužívá. Do HTML se dál vkládají jen na stránkách s `map:`.
- `output/krizky-map/` se při každém buildu vytvoří znovu, takže v něm nezůstanou staré soubory (například overlay odebraný z configu).

**Akceptace (testy):**
- `copy_plugin_assets` zkopíruje `map.js` a `map.css` do `output_dir/krizky-map/`.
- Zkopíruje masku a overlaye z cest relativních ke `config_dir`. Chybějící soubor nevyhodí výjimku.
- Soubor, který v `output_dir/krizky-map/` zůstal z dřívějška, po volání zmizí.
- `after_page_written` nevytvoří `output_dir/krizky-map/`.
- Test `test_assets_copied_only_once` se odstraní nebo nahradí, hlídání opakování zajišťuje core.

## 4. Dokumentace (docs-sync)

- `README.md`: seznam hooků (pokud je) doplnit o `copy_plugin_assets`, popis `map: true` upravit tak, aby neříkal, že zapíná kopírování assetů, a zmínit, že assety jsou ve výstupu vždy.

**Akceptace:** `scripts/verify` projde.

## Mimo rozsah

- Oddělení JS a statiky v mapě (`krizky/TODO.md`): samostatný běh později.
- Čtení `sources.photos.base_url` z configu photos.
