"""Pokemon Center (UK shipping) restock check.

NOTE: Pokemon Center's storefront is heavily JavaScript-driven and sits behind
bot protection. A plain HTTP fetch may return a near-empty shell or a challenge
page, in which case stock can't be read reliably. For production use this adapter
should be backed by Playwright (headless browser) -- the structure here is the
right shape; swap the fetch in `check()` for a rendered-DOM fetch when you wire
Playwright in. See README "Hard stores".

This subclass reuses the generic marker logic but ships Pokemon-Center-tuned
defaults.
"""

from .generic_html import GenericHtmlStore


class PokemonCenterUK(GenericHtmlStore):
    adapter = "pokemoncenter_uk"

    DEFAULT_MARKERS = [
        "out of stock",
        "sold out",
        "coming soon",
        "notify me",
        "currently unavailable",
    ]

    def check(self, product):
        # Apply tuned markers unless the user overrode them in config.
        self.settings.setdefault("oos_markers", self.DEFAULT_MARKERS)
        return super().check(product)
