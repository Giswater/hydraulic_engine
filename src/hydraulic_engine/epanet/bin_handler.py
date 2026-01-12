"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pyproj import Transformer
from swmm_api.output_file import read_out_file, SwmmOutput
from swmm_api.input_file import SwmmInput, read_inp_file
from swmm_api.input_file.section_labels import COORDINATES, VERTICES

from .file_handler import EpanetResultHandler, EpanetFileHandler
from ..utils import tools_log
from ..utils.tools_api import get_api_client, HeFrostClient
from ..utils import tools_sensorthings


class EpanetBinHandler(EpanetFileHandler, EpanetResultHandler):
    """
    Handler for EPANET BIN (binary) files.
    
    Provides functionality to read and parse EPANET simulation output.
    
    Example usage:
        handler = EpanetBinHandler()
        handler.load_file("results.bin")
    """

    def export_to_database(self) -> bool:
        """Export simulation results to database."""
        # TODO: Implement export to database
        tools_log.log_warning("Export to database not yet implemented")
        return False


# region Export to FROST-Server

    def export_to_frost(self, inp_file: str, result_id: str, delete_all: bool = False, batch_size: int = 100,
                        crs_from: int = 25831, crs_to: int = 4326) -> bool:
        pass


# endregion