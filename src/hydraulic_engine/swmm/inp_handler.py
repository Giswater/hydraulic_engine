"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
import os
from typing import Any, Dict, List, Optional

from .file_handler import SwmmFileHandler
from .models import SwmmFeatureSettings, SwmmOptionsSettings, SwmmOtherSettings
from ..utils import tools_log


class SwmmInpHandler(SwmmFileHandler):
    """
    Handler for SWMM INP files.
    
    Provides functionality to read, parse, and write SWMM INP files
    using the swmm-api library.
    
    Example usage:
        handler = SwmmInpHandler()
        handler.read("model.inp")
        
        # Get sections
        junctions = handler.get_junctions()
        conduits = handler.get_conduits()
        
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
            self.file_object.write_file(path)
            tools_log.log_info(f"Successfully wrote INP file: {path}")
            return True

        except Exception as e:
            self.error_msg = str(e)
            tools_log.log_error(f"Error writing INP file: {e}")
            return False

    def validate_inp(self) -> Dict[str, Any]:
        """
        Validate an INP file without running full simulation.
        
        Uses swmm-api for parsing validation.
        
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
            inp = self.file_object

            # Get basic info
            validation["info"]["title"] = getattr(inp.TITLE, 'title', 'N/A') if hasattr(inp, 'TITLE') else 'N/A'
            validation["info"]["junctions"] = len(inp.JUNCTIONS) if hasattr(inp, 'JUNCTIONS') and inp.JUNCTIONS else 0
            validation["info"]["conduits"] = len(inp.CONDUITS) if hasattr(inp, 'CONDUITS') and inp.CONDUITS else 0
            validation["info"]["outfalls"] = len(inp.OUTFALLS) if hasattr(inp, 'OUTFALLS') and inp.OUTFALLS else 0
            validation["info"]["subcatchments"] = len(inp.SUBCATCHMENTS) if hasattr(inp, 'SUBCATCHMENTS') and inp.SUBCATCHMENTS else 0
            validation["info"]["storage"] = len(inp.STORAGE) if hasattr(inp, 'STORAGE') and inp.STORAGE else 0
            validation["info"]["pumps"] = len(inp.PUMPS) if hasattr(inp, 'PUMPS') and inp.PUMPS else 0
            validation["info"]["orifices"] = len(inp.ORIFICES) if hasattr(inp, 'ORIFICES') and inp.ORIFICES else 0
            validation["info"]["weirs"] = len(inp.WEIRS) if hasattr(inp, 'WEIRS') and inp.WEIRS else 0

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
        feature_settings: Optional[SwmmFeatureSettings] = None,
        options_settings: Optional[SwmmOptionsSettings] = None,
        other_settings: Optional[SwmmOtherSettings] = None,
    ) -> None:
        """
        Update INP file with provided settings.
        Only updates fields that are not None.
        
        :param feature_settings: Feature settings to update
        :param options_settings: Options settings to update
        :param other_settings: Other settings to update
        """

        # Update feature settings
        if feature_settings:
            self._update_features(feature_settings)

        # Update options settings
        if options_settings:
            self._update_options(options_settings)

        # Update other settings
        if other_settings:
            self._update_other_settings(other_settings)

    def _update_features(self, feature_settings: SwmmFeatureSettings) -> None:
        """Update INP features from feature settings."""
        # Iterate through all feature setting attributes
        for section_name in dir(feature_settings):
            if section_name.startswith('_'):
                continue

            features_dict = getattr(feature_settings, section_name, None)
            if features_dict is None:
                continue

            # Convert attribute name to uppercase section name (e.g., 'conduits' -> 'CONDUITS')
            section_name = section_name.upper()

            # Check if the section exists in the INP file
            if not hasattr(self.file_object, section_name):
                continue

            inp_section = getattr(self.file_object, section_name)
            if inp_section is None:
                continue

            # Update each feature in the section
            for feature_name, feature_obj in features_dict.items():
                if feature_name in inp_section:
                    self._update_object_attributes(inp_section[feature_name], feature_obj)

                    # Handle cross-section updates for link objects
                    # Cross-sections are stored in XSECTIONS but accessed via link.cross_section
                    if hasattr(feature_obj, 'cross_section') and feature_obj.cross_section is not None:
                        self._update_cross_section(feature_name, feature_obj.cross_section)

    def _update_options(self, options_settings: SwmmOptionsSettings) -> None:
        """Update INP options from options settings."""
        if not hasattr(self.file_object, 'OPTIONS'):
            return

        options = self.file_object.OPTIONS

        # Update all option attributes that are not None
        for attr_name in dir(options_settings):
            if attr_name.startswith('_'):
                continue

            value = getattr(options_settings, attr_name, None)
            if value is None:
                continue

            # Convert enum to value if needed
            if hasattr(value, 'value'):
                value = value.value

            # Convert attribute name to uppercase (e.g., 'flow_units' -> 'FLOW_UNITS')
            option_name = attr_name.upper()

            if option_name in options:
                options[option_name] = value

    def _update_other_settings(self, other_settings: SwmmOtherSettings) -> None:
        """Update INP other settings (curves, timeseries, patterns)."""
        # Iterate through all other setting attributes
        for attr_name in dir(other_settings):
            if attr_name.startswith('_'):
                continue

            setting_dict = getattr(other_settings, attr_name, None)
            if setting_dict is None:
                continue

            # Convert attribute name to uppercase section name (e.g., 'curves' -> 'CURVES')
            section_name = attr_name.upper()

            # Check if the section exists in the INP file
            if not hasattr(self.file_object, section_name):
                continue

            inp_section = getattr(self.file_object, section_name)
            if inp_section is None:
                continue

            # Update each item in the section
            for item_name, item_obj in setting_dict.items():
                if item_name in inp_section:
                    self._update_object_attributes(inp_section[item_name], item_obj)

    def _update_object_attributes(self, target_obj, source_obj) -> None:
        """
        Update target object attributes from source object.
        Only updates attributes that are not None in source object.
        
        :param target_obj: Object to update (from swmm-api)
        :param source_obj: Object with new values (from models)
        """
        for attr_name in dir(source_obj):
            if attr_name.startswith('_'):
                continue

            value = getattr(source_obj, attr_name, None)
            if value is not None:
                # Convert enum to value if needed
                if hasattr(value, 'value'):
                    value = value.value

                # Since field names match swmm-api exactly, use them directly
                if hasattr(target_obj, attr_name):
                    setattr(target_obj, attr_name, value)

    def _update_cross_section(self, link_name: str, cross_section_obj) -> None:
        """
        Update cross-section in XSECTIONS section for a given link.
        
        :param link_name: Name of the link (conduit, pump, etc.)
        :param cross_section_obj: SwmmCrossSection object with new values
        """
        # Check if XSECTIONS section exists
        if not hasattr(self.file_object, 'XSECTIONS'):
            return

        xsections = self.file_object.XSECTIONS
        if xsections is None:
            return

        # Check if cross-section exists for this link
        if link_name in xsections:
            self._update_object_attributes(xsections[link_name], cross_section_obj)

    # =========================================================================
    # Section Getters
    # =========================================================================

    def get_title(self) -> Optional[str]:
        """Get model title."""
        if not self.file_object:
            return None
        return getattr(self.file_object.TITLE, 'title', None) if hasattr(self.file_object, 'TITLE') else None

    def get_options(self) -> Optional[Dict[str, Any]]:
        """Get OPTIONS section as dictionary."""
        if not self.file_object or not hasattr(self.file_object, 'OPTIONS'):
            return None
        try:
            return {k: v for k, v in vars(self.file_object.OPTIONS).items() if not k.startswith('_')}
        except Exception:
            return None

    def get_junctions(self) -> Optional[Dict[str, Any]]:
        """
        Get JUNCTIONS section.
        
        :return: Dictionary of junctions {id: junction_data}
        """
        if not self.file_object or not hasattr(self.file_object, 'JUNCTIONS'):
            return None
        return dict(self.file_object.JUNCTIONS)

    def get_outfalls(self) -> Optional[Dict[str, Any]]:
        """Get OUTFALLS section."""
        if not self.file_object or not hasattr(self.file_object, 'OUTFALLS'):
            return None
        return dict(self.file_object.OUTFALLS)

    def get_storage(self) -> Optional[Dict[str, Any]]:
        """Get STORAGE section."""
        if not self.file_object or not hasattr(self.file_object, 'STORAGE'):
            return None
        return dict(self.file_object.STORAGE)

    def get_dividers(self) -> Optional[Dict[str, Any]]:
        """Get DIVIDERS section."""
        if not self.file_object or not hasattr(self.file_object, 'DIVIDERS'):
            return None
        return dict(self.file_object.DIVIDERS)

    def get_conduits(self) -> Optional[Dict[str, Any]]:
        """Get CONDUITS section."""
        if not self.file_object or not hasattr(self.file_object, 'CONDUITS'):
            return None
        return dict(self.file_object.CONDUITS)

    def get_pumps(self) -> Optional[Dict[str, Any]]:
        """Get PUMPS section."""
        if not self.file_object or not hasattr(self.file_object, 'PUMPS'):
            return None
        return dict(self.file_object.PUMPS)

    def get_orifices(self) -> Optional[Dict[str, Any]]:
        """Get ORIFICES section."""
        if not self.file_object or not hasattr(self.file_object, 'ORIFICES'):
            return None
        return dict(self.file_object.ORIFICES)

    def get_weirs(self) -> Optional[Dict[str, Any]]:
        """Get WEIRS section."""
        if not self.file_object or not hasattr(self.file_object, 'WEIRS'):
            return None
        return dict(self.file_object.WEIRS)

    def get_outlets(self) -> Optional[Dict[str, Any]]:
        """Get OUTLETS section."""
        if not self.file_object or not hasattr(self.file_object, 'OUTLETS'):
            return None
        return dict(self.file_object.OUTLETS)

    def get_subcatchments(self) -> Optional[Dict[str, Any]]:
        """Get SUBCATCHMENTS section."""
        if not self.file_object or not hasattr(self.file_object, 'SUBCATCHMENTS'):
            return None
        return dict(self.file_object.SUBCATCHMENTS)

    def get_subareas(self) -> Optional[Dict[str, Any]]:
        """Get SUBAREAS section."""
        if not self.file_object or not hasattr(self.file_object, 'SUBAREAS'):
            return None
        return dict(self.file_object.SUBAREAS)

    def get_infiltration(self) -> Optional[Dict[str, Any]]:
        """Get INFILTRATION section."""
        if not self.file_object or not hasattr(self.file_object, 'INFILTRATION'):
            return None
        return dict(self.file_object.INFILTRATION)

    def get_coordinates(self) -> Optional[Dict[str, tuple]]:
        """Get COORDINATES section."""
        if not self.file_object or not hasattr(self.file_object, 'COORDINATES'):
            return None
        return dict(self.file_object.COORDINATES)

    def get_vertices(self) -> Optional[Dict[str, List[tuple]]]:
        """Get VERTICES section (link vertices)."""
        if not self.file_object or not hasattr(self.file_object, 'VERTICES'):
            return None
        return dict(self.file_object.VERTICES)

    def get_polygons(self) -> Optional[Dict[str, List[tuple]]]:
        """Get POLYGONS section (subcatchment polygons)."""
        if not self.file_object or not hasattr(self.file_object, 'POLYGONS'):
            return None
        return dict(self.file_object.POLYGONS)

    def get_xsections(self) -> Optional[Dict[str, Any]]:
        """Get XSECTIONS section."""
        if not self.file_object or not hasattr(self.file_object, 'XSECTIONS'):
            return None
        return dict(self.file_object.XSECTIONS)

    def get_transects(self) -> Optional[Dict[str, Any]]:
        """Get TRANSECTS section."""
        if not self.file_object or not hasattr(self.file_object, 'TRANSECTS'):
            return None
        return dict(self.file_object.TRANSECTS)

    def get_curves(self) -> Optional[Dict[str, Any]]:
        """Get CURVES section."""
        if not self.file_object or not hasattr(self.file_object, 'CURVES'):
            return None
        return dict(self.file_object.CURVES)

    def get_timeseries(self) -> Optional[Dict[str, Any]]:
        """Get TIMESERIES section."""
        if not self.file_object or not hasattr(self.file_object, 'TIMESERIES'):
            return None
        return dict(self.file_object.TIMESERIES)

    def get_patterns(self) -> Optional[Dict[str, Any]]:
        """Get PATTERNS section."""
        if not self.file_object or not hasattr(self.file_object, 'PATTERNS'):
            return None
        return dict(self.file_object.PATTERNS)

    def get_raingages(self) -> Optional[Dict[str, Any]]:
        """Get RAINGAGES section."""
        if not self.file_object or not hasattr(self.file_object, 'RAINGAGES'):
            return None
        return dict(self.file_object.RAINGAGES)

    def get_inflows(self) -> Optional[Dict[str, Any]]:
        """Get INFLOWS section."""
        if not self.file_object or not hasattr(self.file_object, 'INFLOWS'):
            return None
        return dict(self.file_object.INFLOWS)

    def get_dwf(self) -> Optional[Dict[str, Any]]:
        """Get DWF (Dry Weather Flow) section."""
        if not self.file_object or not hasattr(self.file_object, 'DWF'):
            return None
        return dict(self.file_object.DWF)

    # =========================================================================
    # Summary and Statistics
    # =========================================================================

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the INP file contents.
        
        :return: Dictionary with counts of each element type
        """
        summary = {
            "file": self.file_path,
            "loaded": self.is_loaded(),
            "title": self.get_title(),
            "counts": {}
        }

        if not self.file_object:
            return summary

        sections = [
            ("junctions", "JUNCTIONS"),
            ("outfalls", "OUTFALLS"),
            ("storage", "STORAGE"),
            ("dividers", "DIVIDERS"),
            ("conduits", "CONDUITS"),
            ("pumps", "PUMPS"),
            ("orifices", "ORIFICES"),
            ("weirs", "WEIRS"),
            ("outlets", "OUTLETS"),
            ("subcatchments", "SUBCATCHMENTS"),
            ("raingages", "RAINGAGES"),
            ("curves", "CURVES"),
            ("timeseries", "TIMESERIES"),
            ("patterns", "PATTERNS"),
        ]

        for name, attr in sections:
            if hasattr(self.file_object, attr):
                section = getattr(self.file_object, attr)
                summary["counts"][name] = len(section) if section else 0
            else:
                summary["counts"][name] = 0

        return summary

    # =========================================================================
    # Raw INP Access
    # =========================================================================

    def get_raw_inp(self) -> Any:
        """
        Get the raw swmm_api SwmmInput object.
        
        :return: SwmmInput object or None
        """
        return self.file_object

    def get_section(self, section_name: str) -> Optional[Any]:
        """
        Get any section by name.
        
        :param section_name: Section name (e.g., 'JUNCTIONS', 'CONDUITS')
        :return: Section data or None
        """
        if not self.file_object:
            return None
        return getattr(self.file_object, section_name.upper(), None)
