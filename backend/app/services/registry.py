"""Shared service container.

The recovered video modules are self-contained. This container keeps the
extension point used by the protocol without forcing unrelated services.
"""

from __future__ import annotations


class Services:
    def __init__(self, ctx):
        self.ctx = ctx

    def rebuild(self) -> None:
        return None
