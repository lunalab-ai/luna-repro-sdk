"""Publish explicitly selected research results; no execution or implicit collection."""

from .client import Page, PublishError, Section, load_bundle, publish_bundle, sync
from . import source

__version__ = "0.2.1"


def page(project, title, **kwargs):
    """Create a result page. Set LUNA_REPRO_ENDPOINT/TOKEN once per session."""
    return Page(project, title, **kwargs)


__all__ = ["Page", "Section", "PublishError", "page", "load_bundle", "publish_bundle", "sync", "source"]
