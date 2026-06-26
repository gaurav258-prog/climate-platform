from enum import Enum


class HazardType(str, Enum):
    FLOOD = "flood"
    HEAT_ACUTE = "heat_acute"
    HEAT_CHRONIC = "heat_chronic"
    WILDFIRE = "wildfire"
    DROUGHT = "drought"
    STORM = "storm"
    SEISMIC = "seismic"


class RiskScenario(str, Enum):
    BASELINE = "baseline"
    ORDERLY_1_5C = "orderly_1_5c"
    DISORDERLY_2C = "disorderly_2c"
    HOT_HOUSE_3_5C = "hot_house_3_5c"


class RiskBucket(str, Enum):
    L = "L"
    M = "M"
    H = "H"
    VH = "VH"


class RiskNature(str, Enum):
    ACUTE = "acute"
    CHRONIC = "chronic"


class TimeHorizon(str, Enum):
    CURRENT = "current"
    Y2030 = "2030"
    Y2050 = "2050"
    Y2100 = "2100"
