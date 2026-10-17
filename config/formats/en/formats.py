"""House date style for every date the app prints without an explicit filter.

Django's default English style ("Oct. 15, 2026") differed from the explicit
formats used in templates. One style everywhere: "15 Oct 2026".
"""

DATE_FORMAT = "j M Y"
DATETIME_FORMAT = "j M Y, H:i"
SHORT_DATE_FORMAT = "j M Y"
SHORT_DATETIME_FORMAT = "j M Y, H:i"
