import os
import sys
import gettext

locale_dir = os.path.join(sys.prefix, "Tools", "catplotlib", "locales")
gettext.install("catplotlib", locale_dir)

def switch(locale):
    gettext.translation("catplotlib", locale_dir, [locale, "en"]).install()
