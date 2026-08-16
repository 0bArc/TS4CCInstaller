# Contributing

Thanks for helping with **CC Installer - TSR Community Manager**. Short notes so patches stay easy to review.

## Before you start

- Read [README.md](./README.md) and [LICENSE](./LICENSE) (MIT).
- This is an unofficial tool. Do not add features that steal paid / VIP content, bypass paywalls, or redistribute TSR assets.
- Prefer small PRs over large mixed changes.

## Dev setup (Windows)

```sh
python -m venv ./env/
env\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

Clipboard CLI (legacy):

```sh
python src/main.py --cli
```

Build the one-file exe:

```sh
build_exe.bat
```

App data while developing may still live under `%APPDATA%\CCInstaller` (or the legacy `%APPDATA%\TSRCommunityModManager` folder). Keep secrets, sessions, and personal Mods paths out of commits (see `.gitignore`).

## Project layout

| Path | Role |
| - | - |
| `src/main.py` | Entry point |
| `src/webapp.py` | Flask app + pywebview window |
| `src/TSRCatalog.py` | Browse / item page parsing |
| `src/TSRDownload.py` / `TSRSession.py` | Downloads + session |
| `src/static/` | Front-end JS / CSS / icon |
| `src/templates/` | Jinja templates |
| `CCInstaller.spec` | PyInstaller one-file build |

## Code style

- Match the style already in the file you edit.
- Python: [Black](https://github.com/psf/black)-friendly formatting; keep changes focused.
- Front-end: dark, minimal UI. Avoid decorative “AI chrome,” em dashes in copy, and drive-by refactors.
- Do not commit `dist/`, `build/`, `env/`, caches, logs, or local `session` files.

## Pull requests

1. Fork / branch from the default branch.
2. Describe **what** changed and **why**.
3. Note how you tested (e.g. `python src/main.py`, browse + download, exe build if you touched packaging).
4. Keep commits readable; squash noise if the history is messy.

Issues and PRs for bugs, UX polish, packaging, and docs are welcome. Feature ideas that conflict with site ToS or paid content will be closed.

## Questions

Open an issue if something in setup or packaging is unclear. Prefer a minimal repro over a long dump.
