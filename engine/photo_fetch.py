"""
Server-side fetch-and-inline for the /astro/chart.svg header photo.

WHY THIS HAS TO HAPPEN SERVER-SIDE, NOT AS A PLAIN <image href="URL">:
when an SVG document is used as the source of an HTML <img> element (as
ours is - the MediaWiki Lua module embeds it via <img src="...chart.svg">),
browsers render it in a restricted "SVG-as-image" context. Per the
relevant part of the HTML/SVG security model, an SVG loaded this way is
NOT permitted to load its own external resources - so an <image
xlink:href="https://external-host/photo.jpg"> inside it simply never
loads, even though the exact same SVG document opened directly in a
browser tab (navigated to, not embedded via <img>) loads that external
image just fine. This is exactly the symptom the project owner hit:
"opens fine in a new tab, but not from inside the embedded picture."

There is no fix on the SVG-authoring side for this - it's a deliberate
browser restriction, not a bug. The standard workaround (used by
essentially every tool that needs an external image inside an
img-embedded SVG) is to fetch the image ourselves and inline it as a
data: URI, since a data: URI isn't an external resource fetch at all -
it's already-embedded data, so the "SVG-as-image" restriction doesn't
apply to it.

CONFIRMED WORKING this way (data: URI, fetched here) against a live
render. Worth an honest note though: the project owner also manually
edited a served SVG's <image href="..."> in browser devtools to point at
a plain external URL (https://sociowiki.sphynkx.org.ua/images_sociowiki/
7/7c/Koroleva_natasha.jpg) and reported that the photo displayed that way
too - which is a real observation that doesn't fully square with the
restriction as documented on MDN's "SVG as an image" page (external
resources "cannot be loaded, though they can be used if inlined through
data: URLs" - no origin/CORS carve-out mentioned). Possible explanations
neither confirmed nor ruled out: the devtools edit may have been tested
in a context that wasn't actually the same "SVG-as-image-via-<img>"
restricted mode (e.g. inspecting/editing the already-parsed live DOM
rather than a fresh <img> load), or browser behavior may be less
consistent here than the MDN page suggests. Given the data: URI approach
is confirmed working end-to-end and doesn't depend on resolving this
discrepancy, it's staying as the primary implementation - but if a future
issue points back here, this note is why a plain external URL isn't
assumed safe to switch to without testing.

SSRF CAUTION: this makes the server fetch a URL on the caller's behalf.
See config.PHOTO_ALLOWED_PREFIXES - fetching is refused (returns None,
logged) unless photo_url starts with one of the configured prefixes.
Fails CLOSED (nothing fetched) with an empty prefix list, which is the
default - see config.py for how to allow-list your own wiki's file host.
"""

import base64
import logging
import mimetypes
import urllib.request
from typing import Optional

from . import config

logger = logging.getLogger("astromcp")


def fetch_photo_as_data_uri(url: Optional[str]) -> Optional[str]:
    """
    Returns a 'data:<mime>;base64,<...>' URI for the given absolute URL,
    or None if url is falsy, not allow-listed, or the fetch fails/exceeds
    the configured size limit for any reason - this is always a
    best-effort enhancement, never something that should break the chart
    render.
    """
    if not url:
        return None

    if not config.PHOTO_ALLOWED_PREFIXES:
        logger.info("photo_url given but ASTROMCP_PHOTO_ALLOWED_PREFIXES is empty - skipping (fails closed)")
        return None
    if not any(url.startswith(prefix) for prefix in config.PHOTO_ALLOWED_PREFIXES):
        logger.warning(f"photo_url '{url}' does not match any ASTROMCP_PHOTO_ALLOWED_PREFIXES entry - refusing to fetch")
        return None

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "astromcp-chart-renderer/1"})
        with urllib.request.urlopen(req, timeout=config.PHOTO_FETCH_TIMEOUT_SECONDS) as resp:
            content_type = resp.headers.get_content_type() or mimetypes.guess_type(url)[0] or "image/jpeg"
            data = resp.read(config.PHOTO_FETCH_MAX_BYTES + 1)
            if len(data) > config.PHOTO_FETCH_MAX_BYTES:
                logger.warning(f"photo_url '{url}' exceeds ASTROMCP_PHOTO_FETCH_MAX_BYTES - skipping")
                return None
    except Exception as e:
        logger.warning(f"failed to fetch photo_url '{url}': {e}")
        return None

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"
