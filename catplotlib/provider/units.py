from aenum import Enum

class Units(Enum):
                 # PerHa  UnitsPerTc  Label
    Blank        = False, 1,          ""
    Age          = True,  1,          ""
    Tc           = False, 1,          "tC"
    Ktc          = False, 1e-3,       "KtC"
    Mtc          = False, 1e-6,       "MtC"
    TcFlux       = False, 1,          "tC/yr"
    KtcFlux      = False, 1e-3,       "KtC/yr"
    MtcFlux      = False, 1e-6,       "MtC/yr"
    TcPerHa      = True,  1,          "tC/ha"
    KtcPerHa     = True,  1e-3,       "KtC/ha"
    MtcPerHa     = True,  1e-6,       "MtC/ha"
    TcPerHaFlux  = True,  1,          "tC/ha/yr"
    KtcPerHaFlux = True,  1e-3,       "KtC/ha/yr"
    MtcPerHaFlux = True,  1e-6,       "MtC/ha/yr"
