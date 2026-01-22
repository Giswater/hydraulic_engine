"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.

EPANET module - Water distribution system modeling functionality.
"""
# -*- coding: utf-8 -*-
from .runner import EpanetRunner, EpanetRunResult
from .inp_handler import EpanetInpHandler
from .bin_handler import EpanetBinHandler

# Model classes
from .models import (
    # Base
    EpanetBaseObject,
    # Enums - Features
    EpanetLinkStatus,
    EpanetValveType,
    EpanetMixingModel,
    # Enums - Options
    EpanetFlowUnits,
    EpanetHeadlossFormula,
    EpanetQualityType,
    EpanetDemandModel,
    EpanetStatistic,
    EpanetUnbalanced,
    # Enums - Other
    EpanetCurveType,
    # Extra classes
    EpanetDemand,
    # Node classes
    EpanetNode,
    EpanetJunction,
    EpanetReservoir,
    EpanetTank,
    # Link classes
    EpanetLink,
    EpanetPipe,
    EpanetPump,
    EpanetValve,
    # Other classes
    EpanetPattern,
    EpanetCurve,
    # Option classes (mirroring WNTR structure)
    EpanetHydraulicOptions,
    EpanetQualityOptions,
    EpanetTimeOptions,
    EpanetEnergyOptions,
    EpanetReactionOptions,
    # Settings classes
    EpanetFeatureSettings,
    EpanetOptionsSettings,
    EpanetOtherSettings,
)

__all__ = [
    # Handlers and Runner
    "EpanetRunner",
    "EpanetRunResult",
    "EpanetInpHandler",
    "EpanetBinHandler",
    # Base
    "EpanetBaseObject",
    # Enums - Features
    "EpanetLinkStatus",
    "EpanetValveType",
    "EpanetMixingModel",
    # Enums - Options
    "EpanetFlowUnits",
    "EpanetHeadlossFormula",
    "EpanetQualityType",
    "EpanetDemandModel",
    "EpanetStatistic",
    "EpanetUnbalanced",
    # Enums - Other
    "EpanetCurveType",
    # Extra classes
    "EpanetDemand",
    # Node classes
    "EpanetNode",
    "EpanetJunction",
    "EpanetReservoir",
    "EpanetTank",
    # Link classes
    "EpanetLink",
    "EpanetPipe",
    "EpanetPump",
    "EpanetValve",
    # Other classes
    "EpanetPattern",
    "EpanetCurve",
    # Option classes (mirroring WNTR structure)
    "EpanetHydraulicOptions",
    "EpanetQualityOptions",
    "EpanetTimeOptions",
    "EpanetEnergyOptions",
    "EpanetReactionOptions",
    # Settings classes
    "EpanetFeatureSettings",
    "EpanetOptionsSettings",
    "EpanetOtherSettings",
]
