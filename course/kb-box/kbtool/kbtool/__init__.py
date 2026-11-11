"""kbtool — the bookkeeping side of the kb plugin: scan, extract, split, SQLite build, query.

stdlib only (PDF optionally via pypdf). No network calls: the host model makes the judgments using
the plugin's prompts, the code keeps the books (SPEC §3, §8 S5).
"""
__version__ = "0.4.0"
SCHEMA_VERSION = 1
