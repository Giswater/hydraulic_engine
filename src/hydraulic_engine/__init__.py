"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("hydraulic-engine")
except PackageNotFoundError:
    __version__ = "0.2.0"

__author__ = "BGEO"
__email__ = "info@bgeo.es"

from .config import config
from . import swmm
from . import epanet
from .utils import (
    ExportDataSource,
    create_pg_connection,
    create_gpkg_connection,
    create_sqlite_connection,
    get_connection,
    close_connection,
    create_frost_connection,
    get_api_client,
    close_api_client,
)

__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "config",
    "swmm",
    "epanet",
    "ExportDataSource",
    "create_pg_connection",
    "create_gpkg_connection",
    "create_sqlite_connection",
    "get_connection",
    "close_connection",
    "create_frost_connection",
    "get_api_client",
    "close_api_client",
]
