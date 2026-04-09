# mkdocs-repo-docs

A [MkDocs](https://www.mkdocs.org/) plugin that auto-discovers markdown files scattered throughout your repository and includes them in your documentation site.

## The Problem

You have documentation files next to your code -- `README.md` files in component directories, API docs alongside source files, architecture notes in config directories. But MkDocs only serves files from its `docs/` directory.

You could copy files manually or symlink them, but they'd go stale. You could set `docs_dir: .` to make the whole repo the docs root, but MkDocs fights you on that (especially with dotfile directories like `.github/` or `.gitea/`).

## The Solution

This plugin stages discovered markdown files into `docs/_repo/` at build time, mirroring their repo structure. MkDocs sees them as normal docs pages. The staging directory is rebuilt from scratch on every build, so it always reflects the current state of the repo.

```
your-repo/
  .github/workflows/README.md    --> docs/_repo/github/workflows/README.md
  src/api/README.md               --> docs/_repo/src/api/README.md
  CONTRIBUTING.md                 --> docs/_repo/CONTRIBUTING.md
  docs/
    index.md                      (your hand-written docs)
    _repo/                        (auto-generated, gitignored)
```

## Installation

```bash
pip install mkdocs-repo-docs
```

## Quick Start

Add to your `mkdocs.yml`:

```yaml
plugins:
  - search
  - repo-docs:
      root_files:
        - README.md
        - CONTRIBUTING.md
      include:
        - src
        - .github
```

Add `docs/_repo/` to your `.gitignore`:

```
docs/_repo/
```

That's it. Any `.md` file in the listed directories will appear in a **Discovered Docs** nav section automatically.

## Configuration example

```yaml
plugins:
  - repo-docs:
      # Files at repo root to include
      root_files:
        - README.md
        - CONTRIBUTING.md
        - CHANGELOG.md

      # Directories to scan for .md files
      include:
        - src
        - .github
        - lib

      # Directories to skip entirely
      exclude:
        - vendor
        - node_modules
        - tmp
        - docs

      # Specific files to skip
      exclude_files:
        - src/internal/NOTES.md

      # Rename directories in the nav (also used for staging path)
      rename_dirs:
        .github: github
        src/components: ui-components

      # Rename files
      rename_files:
        CONTRIBUTING.md: contributing.md

      # Footer appended to every discovered page
      # {source_path} is replaced with the original file's repo-relative path
      footer: "---\n> *Source: [`{source_path}`](https://github.com/you/repo/blob/main/{source_path})*"

      # Nav section name
      nav_section: "Discovered Docs"

      # Position in nav (0-based index, -1 = append to end)
      nav_position: -1

      # Auto-refresh browser on rebuild (local dev only)
      live_reload: false
```

### Options Reference

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `include` | list | `[]` | Directories to scan for markdown files |
| `exclude` | list | `['vendor', 'node_modules', ...]` | Directory prefixes to skip |
| `exclude_files` | list | `[]` | Specific file paths to skip |
| `root_files` | list | `[]` | Files at repo root to include |
| `rename_dirs` | dict | `{}` | Map directory paths to new names |
| `rename_files` | dict | `{}` | Map filenames or paths to new names |
| `footer` | string | `''` | Text appended to every page (`{source_path}` placeholder available) |
| `nav_section` | string | `'Discovered Docs'` | Name of the auto-generated nav section |
| `nav_position` | int | `-1` | Where to insert the section (-1 = end) |
| `live_reload` | bool | `false` | Inject JS that auto-refreshes on rebuild |

## Referencing Discovered Pages in Nav

You can reference staged files in your explicit `nav:` using the `_repo/` prefix:

```yaml
nav:
  - Home: index.md
  - Architecture:
    - Overview: architecture/overview.md
    - Project Context: _repo/CONTRIBUTING.md
  - API:
    - REST API: _repo/src/api/README.md
```

Any discovered files NOT listed in `nav:` appear in the auto-generated **Discovered Docs** section.

## Dotfile Directories

MkDocs excludes directories starting with `.` by default. This plugin automatically strips leading dots during staging:

- `.github/workflows/README.md` becomes `_repo/github/workflows/README.md`
- `.gitea/docker/README.md` becomes `_repo/gitea/docker/README.md`

You can also use `rename_dirs` for explicit control:

```yaml
rename_dirs:
  .github: github-ci
```

## Live Reload

For local development, enable `live_reload: true`. This injects a small JavaScript snippet into every page that polls a build timestamp file (`_build_ts`) every 3 seconds. When the timestamp changes (after a rebuild), the browser reloads automatically.

The JS:
- Uses `XMLHttpRequest` (no fetch/promise overhead)
- Pauses polling when the tab is hidden (`visibilitychange` API)
- No memory accumulation; safe for long-running sessions
- Only active when `live_reload: true`

Pair with a file watcher that triggers `mkdocs build` on changes for a full auto-reload workflow. See the [example serve script](examples/serve.sh).

## How It Works

1. **`on_config` hook**: Before MkDocs collects files, the plugin walks the configured directories, applies renames, and copies `.md` files into `docs/_repo/`
2. **MkDocs file collection**: MkDocs discovers the staged files normally (they're real files in `docs/`)
3. **`on_nav` hook**: Any staged files not in the explicit `nav:` are grouped by directory and added to a "Discovered Docs" section
4. **`on_post_build` hook**: Writes a `_build_ts` timestamp file for live reload
5. **`on_page_content` hook**: Injects live reload JS if enabled

## Requirements

- Python >= 3.8
- MkDocs >= 1.4
- Works with MkDocs Material theme (recommended) and the default theme

## License

MIT