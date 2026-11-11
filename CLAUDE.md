# krizky-map

Plugin pro [krizky](https://github.com/msgre/krizky), statický generátor webů. Přidává mapy nad Leaflet: `map_detail`, `map_list` a `map_full`. Python část generuje GeoJSON a makra pro šablony, JS část (`krizky_map/assets/krizky-map/`) vykresluje mapu v prohlížeči a reaguje na filtry z `krizky-filters`. Lokální checkout core je v `/Users/msgre/projects/muzeum/krizky`.

## Ověření: jediná brána „hotovo“

```bash
scripts/verify
```

Skript spustí `uv sync`, `ruff check`, `ruff format --check`, `pytest`, ESLint, Prettier a JS testy (`tests/js/*.test.mjs`), pokud existují. Na obrazovku vypíše jen souhrn, celé výstupy jsou v `.verify-logs/`. Hotovo je až tehdy, když skončí s exit 0. Pokud selže, oprav příčinu. Pravidla v `pyproject.toml`, `eslint.config.mjs` ani v samotném skriptu kvůli tomu neměň.

Opravy lintu a formátu: `uv run ruff check --fix .`, `uv run ruff format .`, `npx --no-install eslint --fix .`, `npx --no-install prettier --write 'krizky_map/assets/**/*.{js,css}'`.

## Pravidla projektu

Guidelines jsou společné pro core i všechny pluginy a leží v `/Users/msgre/projects/muzeum/krizky/docs/guidelines/`. Před změnou si přečti ty, které se jí týkají:

- `python.md`: styl, logging, testy. `from __future__ import annotations` je zakázaný, hlídá to ruff (TID251).
- `javascript.md`: IIFE + `'use strict'`, `const`, bez `console.log`.
- `cross-language.md`: stejné pojmenování v Pythonu a JS. Konfigurační klíče a struktury se jmenují stejně na obou stranách.
- `docs-sync.md`: když se změní chování nebo konfigurace, aktualizuj i `README.md`.
- `security.md`

Při testech JS zkoušej jen čisté funkce přes `node --test`. Kód závislý na DOM a na Leafletu zatím netestujeme a stávající kód kvůli testům nepřepisuj.

## Git

- Do `main` nikdy necommituj ani nepushuj. Práce jde přes větve `swarm/<heslo>` a PR.
- Commity jsou česky, s volitelným prefixem `feat:`, `fix:` nebo `refactor:`.

## Swarm

- Log běhu: `/Users/msgre/projects/muzeum/krizky/work/<YYYY-MM-DD>-<NN>-<heslo>.md`. `NN` začíná každý den od `01` (podívej se, co už v adresáři je).
- Po zapsání logu přidej řádek do tabulky „Stav fází“ v `/Users/msgre/projects/muzeum/krizky/work/OVERVIEW.md` se stavem a odkazem na log.
- Do core repa nic necommituj. Logy a `OVERVIEW.md` tam spravuje uživatel.
