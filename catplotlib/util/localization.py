import os
import sys
import gettext
import locale
import logging

locale_dir = os.path.join(sys.prefix, "Tools", "catplotlib", "locales")
gettext.install("catplotlib", locale_dir)

def switch(region):
    try:
        gettext.translation("catplotlib", locale_dir, [region, "en"]).install()
        locale.setlocale(locale.LC_ALL, region)
    except:
        logging.error(f"Failed to switch locale to {region}")
        pass
