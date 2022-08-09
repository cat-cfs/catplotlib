from catplotlib.util import localization
from aenum import Enum

def _(message): return message

class Units(Enum):
                 # PerHa  UnitsPerTc  Label
    Blank        = False, 1,          ""
    Age          = True,  1,          ""
    Tc           = False, 1,          "tC"
    Ktc          = False, 1e-3,       "KtC"
    Mtc          = False, 1e-6,       "MtC"
    TcFlux       = False, 1,          _("tC/yr")
    KtcFlux      = False, 1e-3,       _("KtC/yr")
    MtcFlux      = False, 1e-6,       _("MtC/yr")
    TcPerHa      = True,  1,          "tC/ha"
    KtcPerHa     = True,  1e-3,       "KtC/ha"
    MtcPerHa     = True,  1e-6,       "MtC/ha"
    TcPerHaFlux  = True,  1,          _("tC/ha/yr")
    KtcPerHaFlux = True,  1e-3,       _("KtC/ha/yr")
    MtcPerHaFlux = True,  1e-6,       _("MtC/ha/yr")

del _
