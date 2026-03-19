# -*- coding: utf-8 -*-
import json
import re
import html
import urllib.request
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ==== EXPANDED SOURCE LIST ====
SOURCES = [
    # CORE (already working)
    {
        "name": "Sound of Vinyl",
        "source_type": "trusted_store",
        "url": "https://thesoundofvinyl.us/collections/exclusive"
    },
    {
        "name": "uDiscover Music",
        "source_type": "trusted_store",
        "url": "https://shop.udiscovermusic.com/collections/vinyl"
    },

    # BIG BOX
    {
        "name": "Walmart",
        "source_type": "big_box",
        "url": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481_4104_1044819"
    },
    {
        "name": "Best Buy",
        "source_type": "big_box",
        "url": "https://www.bestbuy.com/site/searchpage.jsp?st=vinyl"
    },
    {
        "name": "Target",
        "source_type": "big_box",
        "url": "https://www.target.com/c/vinyl-records-music-movies-books/-/N-yz7nt"
    },

    # MARKETPLACES
    {
        "name": "Amazon",
        "source_type": "marketplace",
        "url": "https://www.amazon.com/s?k=vinyl+records"
    },
    {
        "name": "Merchbar",
        "source_type": "marketplace",
        "url": "https://www.merchbar.com/vinyl-records"
    },

    # STRONG VINYL STORES
    {
        "name": "Deep Discount",
        "source_type": "trusted_store",
        "url": "https://www.deepdiscount.com/music/vinyl"
    },
    {
        "name": "Acoustic Sounds",
        "source_type": "audiophile_store",
        "url": "https://store.acousticsounds.com/index.cfm?get=results&searchtext=vinyl"
    },
    {
        "name": "Music Direct",
        "source_type": "audiophile_store",
        "url": "https://www.musicdirect.com/music/vinyl/"
    },

    # INDIE / CULTURE STORES
    {
        "name": "Newbury Comics",
        "source_type": "indie_store",
        "url": "https://www.newburycomics.com/collections/exclusive-vinyl"
    },
    {
        "name": "Urban Outfitters",
        "source_type": "lifestyle_store",
        "url": "https://www.urbanoutfitters.com/vinyl-records"
    },
    {
        "name": "Barnes & Noble",
        "source_type": "big_box",
        "url": "https://www.barnesandnoble.com/b/music/vinyl/_/N-2sci"
    },

    # REAL VINYL HEAD STORES
    {
        "name": "Rough Trade",
        "source_type": "indie_store",
        "url": "https://www.roughtrade.com/en-us/collections/all-vinyl"
    },
    {
        "name": "Tower Records",
        "source_type": "indie_store",
        "url": "https://towerrecords.com/collections/vinyl-lp"
    },
    {
        "name": "Turntable Lab",
        "source_type": "indie_store",
        "url": "https://www.turntablelab.com/collections/vinyl-records"
    },
    {
        "name": "Fat Beats",
        "source_type": "indie_store",
        "url": "https://www.fatbeats.com/collections/vinyl"
    },

    # YOUR LABEL STACK (🔥 important for your niche)
    {
        "name": "Fearless Records",
        "source_type": "label_store",
        "url": "https://fearlessrecords.com/collections/music"
    },
    {
        "name": "Rise Records",
        "source_type": "label_store",
        "url": "https://riserecords.com/collections/music"
    },
    {
        "name": "Pure Noise Records",
        "source_type": "label_store",
        "url": "https://purenoise.merchnow.com/collections/music"
    },
    {
        "name": "Hopeless Records",
        "source_type": "label_store",
        "url": "https://hopelessrecords.myshopify.com/collections/music"
    },
    {
        "name": "Sumerian Records",
        "source_type": "label_store",
        "url": "https://sumerianrecords.com/collections/music"
    },

    # BONUS INDIE
    {
        "name": "Ride Records",
        "source_type": "indie_store",
        "url": "https://riderecords.com/collections/all"
    },
    {
        "name": "Vinyl Junkies",
        "source_type": "indie_store",
        "url": "https://vinyljunkies.net/collections/all"
    }
]

# ==== EVERYTHING BELOW IS YOUR ORIGINAL CODE (UNCHANGED) ====
POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp"
]

BANNED_KEYWORDS = [
    "christmas", "xmas", "holiday", "jingle", "santa",
    "let it snow", "wonderful christmastime", "war is over",
    "dean martin", "jackson 5", "bobby helms"
]

# (KEEP ALL YOUR EXISTING FUNCTIONS EXACTLY AS THEY ARE BELOW)
# DO NOT CHANGE ANYTHING ELSE
