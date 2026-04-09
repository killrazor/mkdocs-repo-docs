"""mkdocs-repo-docs: Auto-discover and serve markdown files from anywhere in your repo."""

try:
    from mkdocs_repo_docs._version import version as __version__
except ImportError:
    __version__ = "0.0.0"
