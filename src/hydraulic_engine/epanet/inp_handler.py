"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.

EPANET INP Handler
------------------
Handles reading, modifying, and writing EPANET INP files using WNTR.

The update mechanism uses a dynamic approach that:
1. Iterates through settings dataclass attributes
2. For each non-None attribute, finds the corresponding WNTR object
3. Updates only the attributes that are set (not None)

This approach matches the SWMM handler pattern and avoids explicit mapping
by using WNTR attribute names directly in the model classes.
"""
# -*- coding: utf-8 -*-
import os
import wntr

from typing import Any, Dict, Optional
from dataclasses import fields, is_dataclass
from .file_handler import EpanetFileHandler
from .models import (
    EpanetFeatureSettings,
    EpanetOptionsSettings,
    EpanetOtherSettings,
)
from ..utils import tools_log


# Configuration for feature types mapping to WNTR methods
# Format: feature_type -> (name_list_attr, getter_method)
_FEATURE_CONFIG = {
    'junctions': ('junction_name_list', 'get_node'),
    'reservoirs': ('reservoir_name_list', 'get_node'),
    'tanks': ('tank_name_list', 'get_node'),
    'pipes': ('pipe_name_list', 'get_link'),
    'pumps': ('pump_name_list', 'get_link'),
    'valves': ('valve_name_list', 'get_link'),
}

# Configuration for other settings mapping to WNTR methods
# Format: other_type -> (name_list_attr, getter_method)
_OTHER_CONFIG = {
    'patterns': ('pattern_name_list', 'get_pattern'),
    'curves': ('curve_name_list', 'get_curve'),
}

# Attributes that require special handling (not direct assignment)
_SPECIAL_ATTRS = {'demand_list'}

# Attributes to skip (internal/computed, not settable)
_SKIP_ATTRS = {'node_type', 'link_type'}


class EpanetInpHandler(EpanetFileHandler):
    """
    Handler for EPANET INP files.

    Provides functionality to read, parse, and write EPANET INP files
    using the WNTR library.

    Example usage:
        handler = EpanetInpHandler()
        handler.load_file("model.inp")
        
        # Get sections
        junctions = handler.get_junctions()
        pipes = handler.get_pipes()
        
        # Modify and save
        handler.write("modified_model.inp")
    """

    def write(self, output_path: Optional[str] = None) -> bool:
        """
        Write INP file to disk.
        
        :param output_path: Output path (uses original path if not provided)
        :return: True if successful
        """
        if self.file_object is None:
            self.error_msg = "No INP file loaded"
            return False

        try:
            path = output_path or self.file_path
            wntr.network.write_inpfile(self.file_object, path)
            tools_log.log_info(f"Successfully wrote INP file: {path}")
            return True
        except Exception as e:
            self.error_msg = str(e)
            tools_log.log_error(f"Error writing INP file: {e}")
            return False

    def validate_inp(self) -> Dict[str, Any]:
        """
        Validate an INP file without running simulation.
        
        :return: Validation result dictionary
        """
        validation = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "info": {}
        }

        if not os.path.isfile(self.file_path):
            validation["errors"].append(f"File not found: {self.file_path}")
            return validation

        try:
            wn = wntr.network.WaterNetworkModel(self.file_path)

            # Get basic info
            validation["info"]["name"] = wn.name
            validation["info"]["junctions"] = wn.num_junctions
            validation["info"]["tanks"] = wn.num_tanks
            validation["info"]["reservoirs"] = wn.num_reservoirs
            validation["info"]["pipes"] = wn.num_pipes
            validation["info"]["pumps"] = wn.num_pumps
            validation["info"]["valves"] = wn.num_valves

            validation["valid"] = True
            tools_log.log_info(f"INP validation successful: {self.file_path}")

        except Exception as e:
            validation["errors"].append(str(e))
            tools_log.log_error(f"INP validation failed: {e}")

        return validation

    # =========================================================================
    # Update INP file from settings
    # =========================================================================

    def update_inp_from_settings(
        self,
        feature_settings: Optional[EpanetFeatureSettings] = None,
        options_settings: Optional[EpanetOptionsSettings] = None,
        other_settings: Optional[EpanetOtherSettings] = None,
    ) -> None:
        """
        Update INP file with provided settings.
        Only updates fields that are not None.
        
        :param feature_settings: Feature settings to update (junctions, pipes, etc.)
        :param options_settings: Options settings to update (simulation parameters)
        :param other_settings: Other settings to update (patterns, curves)
        """
        if not self.file_object:
            tools_log.log_error("No INP file loaded for updating")
            return

        if feature_settings:
            self._update_features(feature_settings)

        if options_settings:
            self._update_options(options_settings)

        if other_settings:
            self._update_other_settings(other_settings)

    def _update_features(self, feature_settings: EpanetFeatureSettings) -> None:
        """
        Update INP features from feature settings.
        
        Dynamically iterates through feature types and updates each element.
        """
        wn = self.file_object

        for feature_type, config in _FEATURE_CONFIG.items():
            features_dict = getattr(feature_settings, feature_type, None)
            if features_dict is None:
                continue

            name_list_attr, getter_method = config
            name_list = getattr(wn, name_list_attr)
            getter = getattr(wn, getter_method)

            for element_name, model_obj in features_dict.items():
                if element_name not in name_list:
                    tools_log.log_warning(
                        f"{feature_type[:-1].title()} '{element_name}' not found in network"
                    )
                    continue

                wntr_obj = getter(element_name)
                self._update_object_attributes(wntr_obj, model_obj)

    def _update_object_attributes(
        self, target_obj, source_obj
    ) -> None:
        """
        Update target WNTR object attributes from source model object.
        Only updates attributes that are not None in source object.
        
        :param target_obj: WNTR object to update
        :param source_obj: Model object with new values
        """
        # Use dataclass fields if available, otherwise use dir()
        if is_dataclass(source_obj):
            attr_names = [f.name for f in fields(source_obj)]
        else:
            attr_names = [a for a in dir(source_obj) if not a.startswith('_')]

        for attr_name in attr_names:
            if attr_name in _SKIP_ATTRS:
                continue

            value = getattr(source_obj, attr_name, None)
            if value is None:
                continue

            # Handle special attributes
            if attr_name in _SPECIAL_ATTRS:
                self._handle_special_attribute(target_obj, attr_name, value)
                continue

            # Convert enum to value if needed
            if hasattr(value, 'value'):
                value = value.value

            # Attribute names match WNTR directly - set if it exists on target
            if hasattr(target_obj, attr_name):
                try:
                    setattr(target_obj, attr_name, value)
                except AttributeError:
                    # Some attributes may be read-only
                    tools_log.log_warning(
                        f"Cannot set attribute '{attr_name}' on {type(target_obj).__name__}"
                    )

    def _handle_special_attribute(
        self, target_obj, attr_name: str, value
    ) -> None:
        """
        Handle special attributes that require custom logic.
        
        :param target_obj: WNTR object to update
        :param attr_name: Attribute name from model
        :param value: Value to set
        """

        if attr_name == 'demand_list':
            # WNTR handles demands through demand_timeseries_list
            if hasattr(target_obj, 'demand_timeseries_list'):
                target_obj.demand_timeseries_list.clear()
                for demand in value:
                    target_obj.add_demand(demand.base_demand, pattern_name=demand.pattern_name, category=demand.category)

    def _update_options(self, options_settings: EpanetOptionsSettings) -> None:
        """
        Update INP options from options settings.
        
        Options are organized in sections that mirror WNTR's options structure.
        """
        wn = self.file_object
        options = wn.options

        # Get dataclass fields for options settings
        if is_dataclass(options_settings):
            section_names = [f.name for f in fields(options_settings)]
        else:
            section_names = [a for a in dir(options_settings) if not a.startswith('_')]

        for section_name in section_names:
            section_settings = getattr(options_settings, section_name, None)
            if section_settings is None:
                continue

            wntr_section = getattr(options, section_name, None)
            if wntr_section is None:
                continue

            # Get fields for this section
            if is_dataclass(section_settings):
                attr_names = [f.name for f in fields(section_settings)]
            else:
                attr_names = [a for a in dir(section_settings) if not a.startswith('_')]

            for attr_name in attr_names:
                value = getattr(section_settings, attr_name, None)
                if value is None:
                    continue

                # Convert enum to value if needed
                if hasattr(value, 'value'):
                    value = value.value

                # Set attribute if it exists on WNTR section
                if hasattr(wntr_section, attr_name):
                    try:
                        setattr(wntr_section, attr_name, value)
                    except AttributeError:
                        tools_log.log_warning(
                            f"Cannot set option '{attr_name}' on {section_name}"
                        )

    def _update_other_settings(self, other_settings: EpanetOtherSettings) -> None:
        """
        Update INP other settings (patterns, curves).
        
        For list attributes (multipliers, points), the entire list is replaced.
        """
        wn = self.file_object

        for other_type, config in _OTHER_CONFIG.items():
            other_dict = getattr(other_settings, other_type, None)
            if other_dict is None:
                continue

            name_list_attr, getter_method = config
            name_list = getattr(wn, name_list_attr)
            getter = getattr(wn, getter_method)

            for element_name, model_obj in other_dict.items():
                if element_name not in name_list:
                    tools_log.log_warning(
                        f"{other_type[:-1].title()} '{element_name}' not found in network"
                    )
                    continue

                wntr_obj = getter(element_name)
                self._update_object_attributes(wntr_obj, model_obj)

    # =========================================================================
    # Section Getters
    # =========================================================================

    def get_title(self) -> Optional[str]:
        """Get model title/name."""
        if self.file_object:
            return self.file_object.name
        return None

    def get_junctions(self) -> Optional[Dict[str, Any]]:
        """Get JUNCTIONS section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_node(name)
                for name in self.file_object.junction_name_list}

    def get_reservoirs(self) -> Optional[Dict[str, Any]]:
        """Get RESERVOIRS section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_node(name)
                for name in self.file_object.reservoir_name_list}

    def get_tanks(self) -> Optional[Dict[str, Any]]:
        """Get TANKS section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_node(name)
                for name in self.file_object.tank_name_list}

    def get_pipes(self) -> Optional[Dict[str, Any]]:
        """Get PIPES section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_link(name)
                for name in self.file_object.pipe_name_list}

    def get_pumps(self) -> Optional[Dict[str, Any]]:
        """Get PUMPS section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_link(name)
                for name in self.file_object.pump_name_list}

    def get_valves(self) -> Optional[Dict[str, Any]]:
        """Get VALVES section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_link(name)
                for name in self.file_object.valve_name_list}

    def get_patterns(self) -> Optional[Dict[str, Any]]:
        """Get PATTERNS section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_pattern(name)
                for name in self.file_object.pattern_name_list}

    def get_curves(self) -> Optional[Dict[str, Any]]:
        """Get CURVES section as dictionary."""
        if not self.file_object:
            return None
        return {name: self.file_object.get_curve(name)
                for name in self.file_object.curve_name_list}

    def get_controls(self) -> Optional[Dict[str, Any]]:
        """Get CONTROLS section as dictionary."""
        if not self.file_object:
            return None
        return dict(self.file_object.controls)

    def get_options(self) -> Optional[Any]:
        """Get OPTIONS object."""
        if self.file_object:
            return self.file_object.options
        return None

    # =========================================================================
    # Count Methods
    # =========================================================================

    def get_junctions_count(self) -> int:
        """Get the count of junctions."""
        if self.file_object:
            return self.file_object.num_junctions
        return 0

    def get_reservoirs_count(self) -> int:
        """Get the count of reservoirs."""
        if self.file_object:
            return self.file_object.num_reservoirs
        return 0

    def get_tanks_count(self) -> int:
        """Get the count of tanks."""
        if self.file_object:
            return self.file_object.num_tanks
        return 0

    def get_pipes_count(self) -> int:
        """Get the count of pipes."""
        if self.file_object:
            return self.file_object.num_pipes
        return 0

    def get_pumps_count(self) -> int:
        """Get the count of pumps."""
        if self.file_object:
            return self.file_object.num_pumps
        return 0

    def get_valves_count(self) -> int:
        """Get the count of valves."""
        if self.file_object:
            return self.file_object.num_valves
        return 0

    def get_patterns_count(self) -> int:
        """Get the count of patterns."""
        if self.file_object:
            return len(self.file_object.pattern_name_list)
        return 0

    def get_curves_count(self) -> int:
        """Get the count of curves."""
        if self.file_object:
            return len(self.file_object.curve_name_list)
        return 0

    # =========================================================================
    # Summary
    # =========================================================================

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the INP file contents.
        
        :return: Dictionary with counts of each element type
        """
        return {
            "file": self.file_path,
            "loaded": self.is_loaded(),
            "title": self.get_title(),
            "counts": {
                "junctions": self.get_junctions_count(),
                "reservoirs": self.get_reservoirs_count(),
                "tanks": self.get_tanks_count(),
                "pipes": self.get_pipes_count(),
                "pumps": self.get_pumps_count(),
                "valves": self.get_valves_count(),
                "patterns": self.get_patterns_count(),
                "curves": self.get_curves_count(),
            }
        }
