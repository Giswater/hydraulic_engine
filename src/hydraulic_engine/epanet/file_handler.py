"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
import os
import tempfile
import wntr

from wntr.epanet.io import BinFile
from typing import Optional
from abc import ABC, abstractmethod
from pathlib import Path

from ..utils import tools_log


class EpanetFileHandler:
    """
    Handler for EPANET files.
    
    Provides functionality to read and parse EPANET files.     
    """

    def __init__(self):
        self.file_path: Optional[str] = None
        self.file_object = None
        self.error_msg: Optional[str] = None
        self._temp_files: list[Path] = []

    def load_file(self, file_path: str) -> bool:
        """
        Read and parse a result file.
        
        :param file_path: Path to file
        :return: True if successful
        """
        if not os.path.isfile(file_path):
            self.error_msg = f"File not found: {file_path}"
            tools_log.log_error(self.error_msg)
            return False

        try:
            self.file_path = file_path
            if file_path.endswith(".bin"):
                try:
                    bin_file = BinFile()
                    bin_file.read(file_path)
                except:
                    self.error_msg = f"Error reading {file_path}"
                    tools_log.log_error(self.error_msg)
                if bin_file.results is not None:
                    self.file_object = bin_file.results
                else:
                    self.error_msg = f"No results found in {file_path}"
                    tools_log.log_error(self.error_msg)
                    return False
            elif file_path.endswith(".rpt"):
                pass
            elif file_path.endswith(".inp"):
                self.file_object = wntr.network.WaterNetworkModel(file_path)
            else:
                self.error_msg = f"Unsupported file type: {file_path}"
                tools_log.log_error(self.error_msg)
                return False
            tools_log.log_info(f"Successfully read file: {file_path}")
            return True

        except Exception as e:
            self.error_msg = str(e)
            tools_log.log_error(f"Error reading file: {e}")
            return False

    def is_loaded(self) -> bool:
        """Check if a file is loaded."""
        return self.file_object is not None

    def get_file_path(self, output_path: Optional[str], extension: str) -> Path:
        """Return output path or create a temporary file with given extension."""
        if output_path:
            return Path(output_path)

        if not extension.startswith("."):
            extension = f".{extension}"

        tmp = tempfile.NamedTemporaryFile(
            suffix=extension,
            delete=False
        )
        tmp.close()

        path = Path(tmp.name)
        self._temp_files.append(path)
        return path

    def cleanup(self):
        """Cleanup temporary files."""
        for p in self._temp_files:
            p.unlink(missing_ok=True)
        self._temp_files.clear()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit context manager."""
        self.cleanup()

class EpanetResultHandler(ABC):
    """
    Handler for EPANET result files.
    
    Defines the exporting methods for result files.
    """

    @abstractmethod
    def export_to_database(self) -> bool:
        pass

    @abstractmethod
    def export_to_frost(self) -> bool:
        pass
