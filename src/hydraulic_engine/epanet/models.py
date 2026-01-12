"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-

from typing import Optional
from enum import Enum
from dataclasses import dataclass

# region Base Classes


@dataclass
class EpanetBaseObject:
    """
    Base class for all EPANET objects.
    
    WNTR attr: tag
    EPANET INP: [TAGS] section
    """
    tag: Optional[str] = None


# endregion

# region Feature Settings

# region Enums


class EpanetLinkStatus(Enum):
    """
    Status of EPANET link.
    
    WNTR: LinkStatus enum
    EPANET INP: Status column in [PIPES], or [STATUS] section for all links
    """
    OPEN = "Open"      # WNTR uses capitalized values
    CLOSED = "Closed"
    CV = "CV"          # Check valve (pipes only)
    ACTIVE = "Active"  # For valves


class EpanetValveType(Enum):
    """
    Type of EPANET valve.
    
    WNTR: valve_type attribute
    EPANET INP: Type column in [VALVES]
    """
    PRV = "PRV"  # Pressure Reducing Valve
    PSV = "PSV"  # Pressure Sustaining Valve
    PBV = "PBV"  # Pressure Breaker Valve
    FCV = "FCV"  # Flow Control Valve
    TCV = "TCV"  # Throttle Control Valve
    GPV = "GPV"  # General Purpose Valve


class EpanetMixingModel(Enum):
    """
    Mixing model for EPANET tanks.
    
    WNTR: mixing_model attribute (uses MixType enum)
    EPANET INP: [MIXING] section
    """
    MIXED = "MIXED"   # Complete mixing (default)
    TWOCOMP = "2COMP" # Two-compartment
    FIFO = "FIFO"     # First-in-first-out (plug flow)
    LIFO = "LIFO"     # Last-in-first-out (stacked)


# endregion

# region Node Objects


@dataclass
class EpanetNode(EpanetBaseObject):
    """
    Base class for EPANET nodes.
    
    Common attributes for all node types.
    """
    # WNTR: elevation | EPANET INP: Elev in [JUNCTIONS], [TANKS]
    elevation: Optional[float] = None

    # WNTR: initial_quality | EPANET INP: [QUALITY] section
    initial_quality: Optional[float] = None

    # WNTR: coordinates (x, y) | EPANET INP: [COORDINATES] section
    coordinates: Optional[tuple[float, float]] = None


@dataclass
class EpanetDemand():
    """
    EPANET demand.
    
    WNTR: demand | EPANET INP: Demand in [JUNCTIONS]
    """
    base_demand: float = 0.0
    pattern_name: Optional[str] = None
    category: Optional[str] = None


@dataclass
class EpanetJunction(EpanetNode):
    """
    EPANET junction node.
    
    WNTR class: wntr.network.elements.Junction
    EPANET INP: [JUNCTIONS] section
    
    Attributes match WNTR's Junction class.
    Note: base_demand and demand_pattern require special handling in WNTR
    as they are stored in demand_timeseries_list.
    """
    # WNTR: demand_timeseries_list | EPANET INP: Demand in [JUNCTIONS]
    demand_list: Optional[list[EpanetDemand]] = None

    # WNTR: emitter_coefficient | EPANET INP: Coefficient in [EMITTERS]
    emitter_coefficient: Optional[float] = None

    # WNTR: pressure_exponent | EPANET INP: EMITTER EXPONENT in [OPTIONS] (global default)
    pressure_exponent: Optional[float] = None


@dataclass
class EpanetReservoir(EpanetNode):
    """
    EPANET reservoir node (infinite source/sink).
    
    WNTR class: wntr.network.elements.Reservoir
    EPANET INP: [RESERVOIRS] section
    """
    # WNTR: base_head | EPANET INP: Head in [RESERVOIRS]
    base_head: Optional[float] = None

    # WNTR: head_pattern_name | EPANET INP: Pattern in [RESERVOIRS]
    head_pattern_name: Optional[str] = None


@dataclass
class EpanetTank(EpanetNode):
    """
    EPANET tank node (storage).
    
    WNTR class: wntr.network.elements.Tank
    EPANET INP: [TANKS] section
    """
    # WNTR: init_level | EPANET INP: InitLevel in [TANKS]
    init_level: Optional[float] = None

    # WNTR: min_level | EPANET INP: MinLevel in [TANKS]
    min_level: Optional[float] = None

    # WNTR: max_level | EPANET INP: MaxLevel in [TANKS]
    max_level: Optional[float] = None

    # WNTR: diameter | EPANET INP: Diameter in [TANKS]
    diameter: Optional[float] = None

    # WNTR: min_vol | EPANET INP: MinVol in [TANKS]
    min_vol: Optional[float] = None

    # WNTR: vol_curve_name | EPANET INP: VolCurve in [TANKS]
    vol_curve_name: Optional[str] = None

    # WNTR: overflow | EPANET INP: Overflow in [TANKS] (EPANET 2.2+)
    overflow: Optional[bool] = None

    # WNTR: mixing_model | EPANET INP: [MIXING] section
    mixing_model: Optional[EpanetMixingModel] = None

    # WNTR: mixing_fraction | EPANET INP: [MIXING] section
    mixing_fraction: Optional[float] = None

    # WNTR: bulk_coeff | EPANET INP: TANK tank_id coeff in [REACTIONS]
    bulk_coeff: Optional[float] = None


# endregion

# region Link Objects


@dataclass
class EpanetLink(EpanetBaseObject):
    """
    Base class for EPANET links.
    
    Common attributes for all link types.
    """
    # WNTR: start_node_name | EPANET INP: Node1 column
    start_node_name: Optional[str] = None

    # WNTR: end_node_name | EPANET INP: Node2 column
    end_node_name: Optional[str] = None

    # WNTR: initial_status | EPANET INP: Status in [STATUS] section
    initial_status: Optional[EpanetLinkStatus] = None

    # WNTR: vertices | EPANET INP: [VERTICES] section
    vertices: Optional[list[tuple[float, float]]] = None


@dataclass
class EpanetPipe(EpanetLink):
    """
    EPANET pipe link.
    
    WNTR class: wntr.network.elements.Pipe
    EPANET INP: [PIPES] section
    """
    # WNTR: length | EPANET INP: Length in [PIPES]
    length: Optional[float] = None

    # WNTR: diameter | EPANET INP: Diameter in [PIPES]
    diameter: Optional[float] = None

    # WNTR: roughness | EPANET INP: Roughness in [PIPES]
    roughness: Optional[float] = None

    # WNTR: minor_loss | EPANET INP: MinorLoss in [PIPES]
    minor_loss: Optional[float] = None

    # WNTR: bulk_coeff | EPANET INP: BULK pipe_id coeff in [REACTIONS]
    bulk_coeff: Optional[float] = None

    # WNTR: wall_coeff | EPANET INP: WALL pipe_id coeff in [REACTIONS]
    wall_coeff: Optional[float] = None

    # WNTR: cv | EPANET INP: CV status in [PIPES] or [STATUS] section
    cv: Optional[bool] = None


@dataclass
class EpanetPump(EpanetLink):
    """
    EPANET pump link.
    
    WNTR class: wntr.network.elements.Pump (HeadPump or PowerPump)
    EPANET INP: [PUMPS] section
    """

    # WNTR: pump_curve_name | EPANET INP: HEAD curve_id in [PUMPS]
    pump_curve_name: Optional[str] = None

    # WNTR: power | EPANET INP: POWER value in [PUMPS]
    power: Optional[float] = None

    # WNTR: base_speed | EPANET INP: SPEED value in [PUMPS]
    base_speed: Optional[float] = None

    # WNTR: speed_pattern_name | EPANET INP: PATTERN pattern_id in [PUMPS]
    speed_pattern_name: Optional[str] = None

    # WNTR: initial_setting | EPANET INP: [STATUS] section
    initial_setting: Optional[float] = None

    # WNTR: energy_price | EPANET INP: PUMP pump_id PRICE in [ENERGY]
    energy_price: Optional[float] = None

    # WNTR: efficiency (curve name) | EPANET INP: PUMP pump_id EFFIC curve_id in [ENERGY]
    efficiency_curve_name: Optional[str] = None


@dataclass
class EpanetValve(EpanetLink):
    """
    EPANET valve link.
    
    WNTR class: wntr.network.elements.Valve (PRV, PSV, PBV, FCV, TCV, GPV)
    EPANET INP: [VALVES] section
    """
    # WNTR: diameter | EPANET INP: Diameter in [VALVES]
    diameter: Optional[float] = None

    # WNTR: valve_type | EPANET INP: Type in [VALVES]
    valve_type: Optional[EpanetValveType] = None

    # WNTR: initial_setting | EPANET INP: Setting in [VALVES]
    initial_setting: Optional[float] = None

    # WNTR: minor_loss | EPANET INP: MinorLoss in [VALVES]
    minor_loss: Optional[float] = None


# endregion


@dataclass
class EpanetFeatureSettings:
    """
    Settings for EPANET network features.
    
    Contains dictionaries mapping element names to their modification objects.
    Only elements that are present and have non-None attributes will be modified.
    """
    # Nodes
    junctions: Optional[dict[str, EpanetJunction]] = None
    reservoirs: Optional[dict[str, EpanetReservoir]] = None
    tanks: Optional[dict[str, EpanetTank]] = None

    # Links
    pipes: Optional[dict[str, EpanetPipe]] = None
    pumps: Optional[dict[str, EpanetPump]] = None
    valves: Optional[dict[str, EpanetValve]] = None


# endregion

# region Options Settings

# region Enums


class EpanetFlowUnits(Enum):
    """
    Flow units for EPANET simulation.
    
    WNTR: options.hydraulic.inpfile_units
    EPANET INP: UNITS in [OPTIONS]
    """
    # US Customary units
    CFS = "CFS"    # cubic feet per second
    GPM = "GPM"    # gallons per minute
    MGD = "MGD"    # million gallons per day
    IMGD = "IMGD"  # Imperial MGD
    AFD = "AFD"    # acre-feet per day
    # SI units
    LPS = "LPS"    # liters per second
    LPM = "LPM"    # liters per minute
    MLD = "MLD"    # million liters per day
    CMH = "CMH"    # cubic meters per hour
    CMD = "CMD"    # cubic meters per day


class EpanetHeadlossFormula(Enum):
    """
    Headloss formula for EPANET simulation.
    
    WNTR: options.hydraulic.headloss
    EPANET INP: HEADLOSS in [OPTIONS]
    """
    H_W = "H-W"  # Hazen-Williams (default)
    D_W = "D-W"  # Darcy-Weisbach
    C_M = "C-M"  # Chezy-Manning


class EpanetUnbalanced(Enum):
    """
    Unbalanced mode for EPANET simulation.
    
    WNTR: options.hydraulic.unbalanced
    EPANET INP: UNBALANCED in [OPTIONS]
    """
    STOP = "Stop"
    CONTINUE = "Continue"


class EpanetQualityType(Enum):
    """
    Water quality analysis type for EPANET simulation.
    
    WNTR: options.quality.parameter (for type)
    EPANET INP: QUALITY in [OPTIONS]
    """
    NONE = "None"        # No water quality analysis
    CHEMICAL = "Chemical"  # Chemical constituent
    AGE = "Age"          # Water age
    TRACE = "Trace"      # Source tracing


class EpanetDemandModel(Enum):
    """
    Demand model for EPANET 2.2+.
    
    WNTR: options.hydraulic.demand_model
    EPANET INP: DEMAND MODEL in [OPTIONS]
    """
    DDA = "DDA"  # Demand-driven analysis (default)
    PDA = "PDA"  # Pressure-driven analysis


class EpanetStatistic(Enum):
    """
    Statistic option for time series results.
    
    WNTR: options.time.statistic
    EPANET INP: STATISTIC in [TIMES]
    """
    NONE = "None"
    AVERAGE = "Average"
    MINIMUM = "Minimum"
    MAXIMUM = "Maximum"
    RANGE = "Range"


# endregion

# region Option Classes (mirroring WNTR structure)


@dataclass
class EpanetHydraulicOptions:
    """
    Hydraulic simulation options.
    
    WNTR: wn.options.hydraulic
    EPANET INP: [OPTIONS] section
    
    Attribute names match WNTR's HydraulicOptions class exactly.
    """
    # WNTR: inpfile_units | EPANET INP: UNITS
    inpfile_units: Optional[EpanetFlowUnits] = None

    # WNTR: headloss | EPANET INP: HEADLOSS
    headloss: Optional[EpanetHeadlossFormula] = None

    # WNTR: specific_gravity | EPANET INP: SPECIFIC GRAVITY
    specific_gravity: Optional[float] = None

    # WNTR: viscosity | EPANET INP: VISCOSITY
    viscosity: Optional[float] = None

    # WNTR: trials | EPANET INP: TRIALS
    trials: Optional[int] = None

    # WNTR: accuracy | EPANET INP: ACCURACY
    accuracy: Optional[float] = None

    # WNTR: unbalanced | EPANET INP: UNBALANCED (STOP/CONTINUE)
    unbalanced: Optional[EpanetUnbalanced] = None

    # WNTR: pattern | EPANET INP: PATTERN (default pattern)
    pattern: Optional[str] = None

    # WNTR: demand_multiplier | EPANET INP: DEMAND MULTIPLIER
    demand_multiplier: Optional[float] = None

    # WNTR: emitter_exponent | EPANET INP: EMITTER EXPONENT
    emitter_exponent: Optional[float] = None

    # EPANET 2.2+ options
    # WNTR: demand_model | EPANET INP: DEMAND MODEL
    demand_model: Optional[EpanetDemandModel] = None

    # WNTR: minimum_pressure | EPANET INP: MINIMUM PRESSURE
    minimum_pressure: Optional[float] = None

    # WNTR: required_pressure | EPANET INP: REQUIRED PRESSURE
    required_pressure: Optional[float] = None

    # WNTR: pressure_exponent | EPANET INP: PRESSURE EXPONENT
    pressure_exponent: Optional[float] = None

    # WNTR: checkfreq | EPANET INP: CHECKFREQ
    checkfreq: Optional[float] = None

    # WNTR: maxcheck | EPANET INP: MAXCHECK
    maxcheck: Optional[float] = None

    # WNTR: damplimit | EPANET INP: DAMPLIMIT
    damplimit: Optional[float] = None


@dataclass
class EpanetQualityOptions:
    """
    Quality simulation options.
    
    WNTR: wn.options.quality
    EPANET INP: [OPTIONS] and [REACTIONS] sections
    """
    # WNTR: mode | EPANET INP: QUALITY keyword in [OPTIONS]
    mode: Optional[EpanetQualityType] = None

    # WNTR: parameter | EPANET INP: chemical name or trace node in QUALITY
    parameter: Optional[str] = None

    # WNTR: diffusivity | EPANET INP: DIFFUSIVITY
    diffusivity: Optional[float] = None

    # WNTR: tolerance | EPANET INP: TOLERANCE
    tolerance: Optional[float] = None


@dataclass
class EpanetTimeOptions:
    """
    Time simulation options.
    
    WNTR: wn.options.time
    EPANET INP: [TIMES] section
    
    Note: WNTR stores time values in seconds.
    """
    # WNTR: duration | EPANET INP: DURATION
    duration: Optional[int] = None

    # WNTR: hydraulic_timestep | EPANET INP: HYDRAULIC TIMESTEP
    hydraulic_timestep: Optional[int] = None

    # WNTR: quality_timestep | EPANET INP: QUALITY TIMESTEP
    quality_timestep: Optional[int] = None

    # WNTR: pattern_timestep | EPANET INP: PATTERN TIMESTEP
    pattern_timestep: Optional[int] = None

    # WNTR: pattern_start | EPANET INP: PATTERN START
    pattern_start: Optional[int] = None

    # WNTR: report_timestep | EPANET INP: REPORT TIMESTEP
    report_timestep: Optional[int] = None

    # WNTR: report_start | EPANET INP: REPORT START
    report_start: Optional[int] = None

    # WNTR: start_clocktime | EPANET INP: START CLOCKTIME (seconds from midnight)
    start_clocktime: Optional[int] = None

    # WNTR: statistic | EPANET INP: STATISTIC
    statistic: Optional[EpanetStatistic] = None


@dataclass
class EpanetEnergyOptions:
    """
    Energy simulation options.
    
    WNTR: wn.options.energy
    EPANET INP: [ENERGY] section
    """
    # WNTR: global_efficiency | EPANET INP: GLOBAL EFFICIENCY
    global_efficiency: Optional[float] = None

    # WNTR: global_price | EPANET INP: GLOBAL PRICE
    global_price: Optional[float] = None

    # WNTR: global_pattern | EPANET INP: GLOBAL PATTERN
    global_pattern: Optional[str] = None

    # WNTR: demand_charge | EPANET INP: DEMAND CHARGE
    demand_charge: Optional[float] = None


@dataclass
class EpanetReactionOptions:
    """
    Reaction simulation options.
    
    WNTR: wn.options.reaction
    EPANET INP: [REACTIONS] section
    """
    # WNTR: bulk_order | EPANET INP: ORDER BULK
    bulk_order: Optional[float] = None

    # WNTR: tank_order | EPANET INP: ORDER TANK
    tank_order: Optional[float] = None

    # WNTR: wall_order | EPANET INP: ORDER WALL
    wall_order: Optional[float] = None

    # WNTR: global_bulk | EPANET INP: GLOBAL BULK
    global_bulk: Optional[float] = None

    # WNTR: global_wall | EPANET INP: GLOBAL WALL
    global_wall: Optional[float] = None

    # WNTR: limiting_potential | EPANET INP: LIMITING POTENTIAL
    limiting_potential: Optional[float] = None

    # WNTR: roughness_correlation | EPANET INP: ROUGHNESS CORRELATION
    roughness_correlation: Optional[float] = None


# endregion


@dataclass
class EpanetOptionsSettings:
    """
    Settings for EPANET simulation options.
    
    Structure mirrors WNTR's WaterNetworkModel.options to avoid mapping.
    Each attribute corresponds to a WNTR options sub-object.
    """
    hydraulic: Optional[EpanetHydraulicOptions] = None
    quality: Optional[EpanetQualityOptions] = None
    time: Optional[EpanetTimeOptions] = None
    energy: Optional[EpanetEnergyOptions] = None
    reaction: Optional[EpanetReactionOptions] = None


# endregion

# region Other Settings

# region Enums


class EpanetCurveType(Enum):
    """
    Type of EPANET curve.
    
    WNTR: curve_type attribute on Curve object
    EPANET INP: ;TYPE comment in [CURVES] section
    """
    PUMP = "PUMP"            # Pump curve (head vs flow) - also known as HEAD
    EFFICIENCY = "EFFICIENCY"  # Pump efficiency curve
    VOLUME = "VOLUME"        # Tank volume curve
    HEADLOSS = "HEADLOSS"    # GPV headloss curve


# endregion

# region Objects


@dataclass
class EpanetPattern(EpanetBaseObject):
    """
    EPANET time pattern.
    
    WNTR class: wntr.network.elements.Pattern
    EPANET INP: [PATTERNS] section
    
    Note: When modifying, the entire multipliers list is replaced.
    """
    # WNTR: multipliers | EPANET INP: multiplier values in [PATTERNS]
    multipliers: Optional[list[float]] = None


@dataclass
class EpanetCurve(EpanetBaseObject):
    """
    EPANET data curve.
    
    WNTR class: wntr.network.elements.Curve
    EPANET INP: [CURVES] section
    
    Note: When modifying, the entire points list is replaced.
    """
    # WNTR: curve_type | EPANET INP: ;TYPE comment in [CURVES]
    curve_type: Optional[EpanetCurveType] = None

    # WNTR: points | EPANET INP: X-Value, Y-Value pairs in [CURVES]
    points: Optional[list[tuple[float, float]]] = None


# endregion


@dataclass
class EpanetOtherSettings:
    """
    Other settings for EPANET INP file.
    
    Contains patterns and curves.
    Note: Controls are not included because WNTR handles them differently
    and modifying existing controls requires more complex logic.
    """
    patterns: Optional[dict[str, EpanetPattern]] = None
    curves: Optional[dict[str, EpanetCurve]] = None


# endregion
