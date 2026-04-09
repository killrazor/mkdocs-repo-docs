"""
MkDocs plugin: repo-docs

Auto-discovers markdown files throughout a repository and stages them into the
MkDocs docs directory so they can be built and served normally. Files are copied
into docs/_repo/ (which should be gitignored) mirroring the repo structure.

This solves a common problem: documentation files scattered throughout a codebase
(README.md files next to source code, docs in component directories, etc.) that
MkDocs can't normally reach because they live outside docs_dir.

Features:
    - Auto-discovers .md files across the entire repo
    - Handles dotfile directories (.gitea/, .github/) that MkDocs normally excludes
    - Directory and file renaming for clean nav presentation
    - Configurable exclusions (directories and individual files)
    - Footer injection with {source_path} placeholder for linking back to source
    - Configurable nav section positioning
    - Live reload for local development (polls for content changes)

Works with both `mkdocs serve` and `mkdocs build`.
"""

import os
import shutil
import time
import logging

from mkdocs.plugins import BasePlugin
from mkdocs.config import config_options
from mkdocs.structure.files import InclusionLevel
from mkdocs.structure.pages import Page
from mkdocs.structure.nav import Section

log = logging.getLogger('mkdocs.plugins.repo_docs')

STAGING_DIR = '_repo'


class RepoDocsPlugin(BasePlugin):
    """MkDocs plugin that discovers and stages repo markdown files."""

    config_scheme = (
        ('include', config_options.Type(list, default=[])),
        ('exclude', config_options.Type(list, default=[
            'vendor', 'node_modules', 'tmp', 'logs', 'ssl', 'docs',
        ])),
        ('exclude_files', config_options.Type(list, default=[])),
        ('root_files', config_options.Type(list, default=[])),
        ('rename_dirs', config_options.Type(dict, default={})),
        ('rename_files', config_options.Type(dict, default={})),
        ('footer', config_options.Type(str, default='')),
        ('nav_section', config_options.Type(str, default='Discovered Docs')),
        ('nav_position', config_options.Type(int, default=-1)),
        ('live_reload', config_options.Type(bool, default=False)),
    )

    def on_config(self, config, **kwargs):
        """Stage repo markdown files into docs/_repo/ before MkDocs collects files."""
        docs_dir = config['docs_dir']
        repo_root = os.path.dirname(os.path.abspath(docs_dir))
        staging = os.path.join(docs_dir, STAGING_DIR)

        # Clean previous staging
        if os.path.exists(staging):
            shutil.rmtree(staging)

        # Normalize config values
        exclude_prefixes = tuple(
            d.replace('\\', '/').rstrip('/') + '/' for d in self.config['exclude']
        )
        exclude_files = set(
            f.replace('\\', '/') for f in self.config['exclude_files']
        )
        rename_dirs = {
            k.replace('\\', '/').rstrip('/'): v
            for k, v in self.config['rename_dirs'].items()
        }
        rename_files = {
            k.replace('\\', '/'): v
            for k, v in self.config['rename_files'].items()
        }

        staged_count = 0

        # 1. Root files
        for filename in self.config['root_files']:
            src = os.path.join(repo_root, filename)
            if not os.path.isfile(src):
                continue
            if filename.replace('\\', '/') in exclude_files:
                continue

            dest_name = rename_files.get(filename, filename)
            dest = os.path.join(staging, dest_name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            self._copy_with_footer(src, dest, filename)
            staged_count += 1

        # 2. Included directories
        for include_dir in self.config['include']:
            dir_path = os.path.join(repo_root, include_dir)
            if not os.path.isdir(dir_path):
                continue

            for root, dirs, filenames in os.walk(dir_path):
                rel_root = os.path.relpath(root, repo_root).replace('\\', '/')

                # Prune excluded dirs
                dirs[:] = [
                    d for d in dirs
                    if not (rel_root + '/' + d + '/').lstrip('./').startswith(exclude_prefixes)
                    and d != '__pycache__'
                    and d != '.git'
                ]

                for filename in filenames:
                    if not filename.lower().endswith('.md'):
                        continue

                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, repo_root).replace('\\', '/')

                    # Check dir exclusions
                    if any(rel_path.startswith(p) for p in exclude_prefixes):
                        continue

                    # Check file exclusions
                    if rel_path in exclude_files:
                        continue

                    # Apply directory renames (longest match first)
                    dest_rel = self._apply_dir_renames(rel_path, rename_dirs)

                    # Apply file renames (by full path or just filename)
                    dest_rel = self._apply_file_renames(dest_rel, rel_path, rename_files)

                    dest = os.path.join(staging, dest_rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    self._copy_with_footer(full_path, dest, rel_path)
                    staged_count += 1

        log.info('repo-docs: staged %d files into %s/', staged_count, STAGING_DIR)
        return config

    def _apply_dir_renames(self, rel_path, rename_dirs):
        """
        Apply directory renames. Checks longest paths first so
        'site/mdcounter/API' matches before 'site/mdcounter'.
        Also auto-strips leading dots from directory names
        (MkDocs excludes dotfile directories by default).
        """
        for old_dir in sorted(rename_dirs.keys(), key=len, reverse=True):
            old_prefix = old_dir + '/'
            if rel_path.startswith(old_prefix):
                new_dir = rename_dirs[old_dir]
                rel_path = new_dir + '/' + rel_path[len(old_prefix):]
                break
            elif rel_path == old_dir:
                rel_path = rename_dirs[old_dir]
                break

        # Auto-strip leading dots from any remaining directory components
        parts = rel_path.split('/')
        cleaned = []
        for part in parts:
            if part.startswith('.') and len(part) > 1 and '/' in rel_path:
                cleaned.append(part[1:])
            else:
                cleaned.append(part)
        return '/'.join(cleaned)

    def _apply_file_renames(self, dest_rel, orig_rel, rename_files):
        """Apply file renames. Checks full path first, then just the filename."""
        if orig_rel in rename_files:
            dirname = os.path.dirname(dest_rel)
            return os.path.join(dirname, rename_files[orig_rel]).replace('\\', '/')

        filename = os.path.basename(dest_rel)
        if filename in rename_files:
            dirname = os.path.dirname(dest_rel)
            return os.path.join(dirname, rename_files[filename]).replace('\\', '/')

        return dest_rel

    def _copy_with_footer(self, src, dest, rel_path=''):
        """Copy a markdown file, optionally appending a footer.

        The footer string supports {source_path} placeholder which is replaced
        with the original file's repo-relative path.
        """
        content = open(src, 'r', encoding='utf-8', errors='replace').read()
        if self.config['footer']:
            footer = self.config['footer'].replace('\\n', '\n')
            footer = footer.replace('{source_path}', rel_path)
            content = content.rstrip() + '\n\n' + footer + '\n'
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(content)

    def on_nav(self, nav, *, config, files, **kwargs):
        """Add discovered repo files to nav under a dedicated section."""
        nav_pages = set()
        self._collect_nav_pages(nav.items, nav_pages)

        # Find staged repo pages not in explicit nav
        repo_files = []
        for f in files:
            if (f.src_uri.startswith(STAGING_DIR + '/')
                    and f.is_documentation_page()
                    and f.src_uri not in nav_pages
                    and f.inclusion != InclusionLevel.EXCLUDED):
                repo_files.append(f)

        if not repo_files:
            return nav

        # Group by first directory after _repo/
        groups = {}
        for f in repo_files:
            parts = f.src_uri.split('/')
            if len(parts) > 2:
                group = parts[1]
            else:
                group = 'Root'
            groups.setdefault(group, []).append(f)

        # Build nav sections
        section_items = []

        # Root files first
        if 'Root' in groups:
            for f in sorted(groups.pop('Root'), key=lambda f: f.src_uri):
                title = self._file_title(f)
                section_items.append(Page(title, f, config))

        # Then grouped by directory
        for group_name in sorted(groups.keys()):
            group_files = sorted(groups[group_name], key=lambda f: f.src_uri)
            sub_items = []
            for f in group_files:
                title = self._file_title(f)
                sub_items.append(Page(title, f, config))
            if sub_items:
                section_items.append(
                    Section(self._format_name(group_name), sub_items)
                )

        if section_items:
            section = Section(self.config['nav_section'], section_items)
            pos = self.config['nav_position']
            if pos == -1:
                nav.items.append(section)
            elif 0 <= pos <= len(nav.items):
                nav.items.insert(pos, section)
            else:
                nav.items.append(section)
            log.info('repo-docs: added %d items to "%s" nav section at position %s',
                     len(section_items), self.config['nav_section'],
                     'end' if pos == -1 else str(pos))

        return nav

    # --- Live reload support ---

    def on_post_build(self, *, config, **kwargs):
        """Write a build timestamp file so the live reload JS can detect changes."""
        if not self.config['live_reload']:
            return
        site_dir = config['site_dir']
        ts_file = os.path.join(site_dir, '_build_ts')
        with open(ts_file, 'w') as f:
            f.write(str(int(time.time() * 1000)))

    def on_page_content(self, html, *, page, config, files, **kwargs):
        """Inject live reload script into every page."""
        if not self.config['live_reload']:
            return html

        if not hasattr(self, '_reload_script'):
            js_path = os.path.join(os.path.dirname(__file__), 'live_reload.js')
            try:
                with open(js_path, 'r') as f:
                    self._reload_script = '\n<script>\n' + f.read() + '\n</script>'
            except FileNotFoundError:
                log.warning('repo-docs: live_reload.js not found at %s', js_path)
                self._reload_script = ''

        return html + self._reload_script

    # --- Helpers ---

    def _collect_nav_pages(self, items, pages):
        for item in items:
            if hasattr(item, 'file') and item.file:
                pages.add(item.file.src_uri)
            if hasattr(item, 'children') and item.children:
                self._collect_nav_pages(item.children, pages)

    def _file_title(self, f):
        """Generate a readable title from a file path."""
        name = os.path.splitext(os.path.basename(f.src_uri))[0]
        if name.lower() == 'readme':
            parts = f.src_uri.split('/')
            if len(parts) >= 3:
                name = parts[-2]
        return name.replace('-', ' ').replace('_', ' ').title()

    def _format_name(self, name):
        """Format a directory name for nav display."""
        if name.startswith('.'):
            name = name[1:]
        return name.replace('-', ' ').replace('_', ' ').title()
