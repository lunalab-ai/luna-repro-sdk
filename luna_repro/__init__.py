"""Publish explicitly selected research results; no execution or implicit collection."""

from .client import Page, PublishError, Section, load_bundle, publish_bundle, sync
from . import source
from .session import configure, clear
from .connection import connect
from .selection import select, publish, Selection
from .capture import capture

__version__ = "0.3.0"


def page(project, title, **kwargs):
    """Create a result page. Set LUNA_REPRO_ENDPOINT/TOKEN once per session."""
    return Page(project, title, **kwargs)


__all__ = ["Page", "Section", "PublishError", "page", "load_bundle", "publish_bundle", "sync", "source", "configure", "clear", "connect", "select", "publish", "Selection", "capture"]
