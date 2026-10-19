"""Why a crop-statistics publisher's data could not be fetched or read (the reviewed yield sources — FAOSTAT,
Eurostat, USDA FAS, USDA NASS, Statistics Canada), in customer words: a code of the message catalogue (agri.feed.*)
with its values. The error's text is the code's label, so a failed refresh's note (services.data.feeds) and every
screen that shows it read customer words; the technical cause goes to the log.

A publisher that could not be reached, or answered 502 / 503 / 504 (RFC 9110 §15.6.3-15.6.5), raises the unreachable
kind: the provider's side, never a fault in our adapter (E215, services.data.feeds.source_unreachable). Any other
answer is a PublisherError and stays ours to look at."""
from __future__ import annotations

import logging
from functools import lru_cache

from core import messages

log = logging.getLogger(__name__)


class PublisherError(RuntimeError):
    def __init__(self, code: str, **params) -> None:
        self.code, self.params = code, params
        super().__init__(messages.label(code, **params))


@lru_cache(maxsize=1)
def unreachable_kind() -> type[PublisherError]:
    """The unreachable kind, made on first use: services.data.feeds loads the yield sources (and so these adapters)
    while it is itself loading, before its SourceUnreachable exists — this module cannot import it at load time."""
    from services.data.feeds import SourceUnreachable

    class PublisherUnreachable(PublisherError, SourceUnreachable):
        """The publisher could not be reached, or answered with an outage status — its side, not ours."""
    return PublisherUnreachable


def unreachable(source: str, cause: BaseException) -> PublisherError:
    """No connection, or a timeout. Only the cause's class goes to the log: its text may carry a URL with a key
    in it."""
    log.warning("%s could not be reached (%s)", source, type(cause).__name__)
    return unreachable_kind()("agri.feed.unreachable", source=source)


def answered(source: str, status: int, what: str) -> PublisherError:
    """The error for a publisher's answer other than its data: an outage status is the provider's side."""
    from services.data.feeds import OUTAGE_STATUS
    log.warning("%s answered %s to %s", source, status, what)
    if status in OUTAGE_STATUS:
        return unreachable_kind()("agri.feed.unavailable", source=source, status=status)
    return PublisherError("agri.feed.refused", source=source, status=status)


def no_key(source: str, setting: str) -> PublisherError:
    """The publisher's access key is not configured: the setting's name goes to the log, for the operator."""
    log.error("%s is not set — %s cannot be fetched", setting, source)
    return PublisherError("agri.feed.no_key", source=source)
