"""
This file is part of Hydraulic Engine
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
import wntr

from typing import Dict, List, Optional
from datetime import datetime, timezone
from pyproj import Transformer
from datetime import timedelta

from .file_handler import EpanetResultHandler, EpanetFileHandler
from ..utils import tools_log
from ..utils.tools_api import get_api_client, HeFrostClient
from ..utils import tools_sensorthings


class EpanetBinHandler(EpanetFileHandler, EpanetResultHandler):
    """
    Handler for EPANET BIN (binary) files.
    
    Provides functionality to read and parse EPANET simulation output.

    Note: This module uses private helper functions (_prepare_*) 
    for data preparation tasks. These are not part of the public API.
    
    Example usage:
        handler = EpanetBinHandler()
        handler.load_file("results.bin")
        handler.export_to_frost(inp_handler=inp_handler, result_id="test1")
    """

    def export_to_database(self) -> bool:
        """Export simulation results to database."""
        # TODO: Implement export to database
        tools_log.log_warning("Export to database not yet implemented")
        return False


# region Export to FROST-Server

    def export_to_frost(
            self,
            inp_handler: wntr.network.WaterNetworkModel,
            result_id: str,
            batch_size: int = 50,
            max_workers: int = 4,
            crs_from: int = 25831,
            crs_to: int = 4326,
            start_time: Optional[datetime] = None,
            client: Optional[HeFrostClient] = None
        ) -> bool:
        """
        Export simulation results to FROST-Server (SensorThings API).
        
        Creates Things for nodes and links, Datastreams for each output variable, and Observations for the time series data.
        
        :param inp_handler: INP handler to get coordinates
        :param result_id: ID of the result
        :param batch_size: Number of operations per batch request (default: 200)
        :param crs_from: Source CRS code (default: 25831 - ETRS89 / UTM zone 31N)
        :param crs_to: Target CRS code (default: 4326 - WGS84)
        :param network_type: Type of network (default: "EPANET")
        :param start_time: Simulation start time (default: None, uses current time + start_clocktime)
        :param max_workers: Number of concurrent batch requests (default: 4)
        """
        if client is None:
            client = get_api_client()

        if not client or not isinstance(client, HeFrostClient):
            tools_log.log_error("No FROST client available")
            return False

        if not self.is_loaded():
            tools_log.log_error("No OUT file loaded")
            return False

        # Delete all existing entities. Note: This is only used for testing purposes.
        # if delete_all:
        #     tools_log.log_info("Deleting all existing entities...")
        #     tools_sensorthings.delete_all_entities(
        #         batch_size=batch_size,
        #         max_workers=max_workers,
        #         client=client
        #     )
        #     tools_log.log_info("Cleanup completed.")

        # Check if INP file is loaded
        if not inp_handler.is_loaded():
            tools_log.log_error("No INP file loaded")
            return False

        # Determine simulation start time
        if start_time is None:
            start_time = datetime.now(timezone.utc) + timedelta(seconds=inp_handler.file_object.options.time.start_clocktime)
        tools_log.log_info(f"Simulation start time: {start_time.isoformat()}")

        # Pre-fetch existing entities (optimized: 2 API calls instead of N)
        tools_log.log_info("Fetching existing entities from server...")
        things_cache = tools_sensorthings.get_all_things_with_locations(client)
        obs_props_cache = tools_sensorthings.get_all_observed_properties(client)
        tools_log.log_info(f"Found {len(things_cache)} existing Things and {len(obs_props_cache)} ObservedProperties")

        # Get or create ObservedProperties (only creates missing ones)
        property_ids = tools_sensorthings.get_or_create_observed_properties(
            obs_props_cache=obs_props_cache,
            engine='epanet',
            client=client
        )

        # Create new Sensor for this simulation run
        sensor_ids = tools_sensorthings.create_simulation_sensor(
            result_id=result_id,
            network_type='EPANET',
            inp_file=inp_handler.file_path,
            client=client
        )

        # Set up coordinate transformer
        transformer = Transformer.from_crs(crs_from, crs_to, always_xy=True)

        # Track feature IDs from the INP file
        inp_feature_ids = set()

        # Prepare node and link data
        tools_log.log_info("Preparing nodes...")
        nodes_data = _prepare_nodes_data(inp_handler.file_object)
        tools_log.log_info(f"Found {len(nodes_data)} nodes")

        node_things = _prepare_nodes_things_data(
            nodes_data, inp_handler.file_object, self.file_object, sensor_ids, property_ids,
            transformer, start_time, inp_feature_ids
        )

        tools_log.log_info("Preparing links...")
        links_data = _prepare_links_data(inp_handler.file_object)
        tools_log.log_info(f"Found {len(links_data)} links")

        link_things = _prepare_links_things_data(
            links_data, self.file_object, sensor_ids, property_ids,
            inp_handler.file_object, transformer, start_time, inp_feature_ids
        )

        # Combine all Things and process in batches
        all_things = node_things + link_things
        tools_log.log_info(
            f"Processing {len(all_things)} Things using batch requests "
            f"(batch_size={batch_size}, max_workers={max_workers})..."
        )
        tools_sensorthings.process_things_batch(
            all_things,
            things_cache,
            batch_size=batch_size,
            max_workers=max_workers,
            client=client
        )

        # Mark Things not in INP as obsolete
        tools_log.log_info("Checking for obsolete Things...")
        tools_sensorthings.mark_obsolete_things(
            things_cache,
            inp_feature_ids,
            batch_size=batch_size,
            max_workers=max_workers,
            client=client
        )

        tools_log.log_info("Processing completed!")
        return True

# endregion

# region Helper functions

def _prepare_nodes_data(wn: wntr.network.WaterNetworkModel) -> List[Dict]:
    """Extract node data from WNTR water network model."""
    nodes_data = []
    for node_name, node in wn.nodes():
        node_type = tools_sensorthings.get_epanet_node_type(node)

        # Get coordinates
        coords = node.coordinates
        if coords is None or len(coords) < 2:
            tools_log.log_warning(f"Node {node_name} has no coordinates, skipping")
            continue

        nodes_data.append({
            'id': node_name,
            'type': node_type,
            'coordinates': (coords[0], coords[1])
        })

    return nodes_data


def _prepare_nodes_things_data(
    nodes_data: List[Dict], wn: wntr.network.WaterNetworkModel, results: wntr.sim.SimulationResults, sensor_ids: Dict[str, str],
    property_ids: Dict[str, str], transformer: Transformer, start_time: datetime,
    inp_feature_ids: set
) -> List[Dict]:
    """Prepare Thing data for nodes (no HTTP calls)."""
    things_data = []
    for node_data in nodes_data:
        node_id = node_data['id']
        node_type = node_data['type']
        coordinates = node_data['coordinates']

        # Track this feature ID
        inp_feature_ids.add(node_id)

        # Transform coordinates
        lon, lat = transformer.transform(coordinates[0], coordinates[1])
        location = {"type": "Point", "coordinates": [lon, lat]}

        # Create Datastreams with Observations for each property
        datastreams = []
        for prop in tools_sensorthings.EPANET_NODE_PROPERTIES:
            prop_config = tools_sensorthings.EPANET_OBSERVED_PROPERTIES[prop]
            try:
                if prop in results.node:
                    values = results.node[prop][node_id]
                else:
                    continue

                observations = []
                current_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

                for timestamp, value in values.items():
                    observations.append({
                        "phenomenonTime": (start_time + timedelta(seconds=timestamp)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "result": float(value),
                        "resultTime": current_time
                    })

                datastream = {
                    "name": f"{prop_config['name']} at {node_id}",
                    "description": f"The {prop_config['name'].lower()} at EPANET {node_type} {node_id}",
                    "unitOfMeasurement": prop_config['unit'],
                    "observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement",
                    "Sensor": {"@iot.id": sensor_ids['simulated']},
                    "ObservedProperty": {"@iot.id": property_ids[prop]},
                    "Observations": observations
                }
                datastreams.append(datastream)

            except Exception as e:
                tools_log.log_warning(f"Could not process {prop} for {node_id}: {e}")

        thing_data = {
            "name": node_id,
            "description": f"EPANET {node_type} {node_id}",
            "Locations": [{
                "name": f"{node_id} Location",
                "description": f"Location of EPANET {node_type} {node_id}",
                "encodingType": "application/geo+json",
                "location": location
            }],
            "Datastreams": datastreams,
            "properties": {
                "node_type": node_type
            }
        }
        things_data.append(thing_data)

    return things_data


def _prepare_links_data(wn: wntr.network.WaterNetworkModel) -> List[Dict]:
    """Extract link data from WNTR water network model."""
    links_data = []

    for link_name, link in wn.links():
        link_type = tools_sensorthings.get_epanet_link_type(link)

        links_data.append({
            'id': link_name,
            'type': link_type
        })

    return links_data


def _prepare_links_things_data(
    links_data: List[Dict], results: wntr.sim.SimulationResults, sensor_ids: Dict[str, str],
    property_ids: Dict[str, str], wn: wntr.network.WaterNetworkModel, transformer: Transformer, start_time: datetime,
    inp_feature_ids: set
) -> List[Dict]:
    """Prepare Thing data for links (no HTTP calls)."""
    things_data = []
    for link_data in links_data:
        link_id = link_data['id']
        link_type = link_data['type']

        # Track this feature ID
        inp_feature_ids.add(link_id)

        link = wn.get_link(link_id)
        vertices = _get_geometry_from_link(link)

        transformed_vertices = []
        for x, y in vertices:
            lon, lat = transformer.transform(x, y)
            transformed_vertices.append([lon, lat])

        datastreams = []
        for prop in tools_sensorthings.EPANET_LINK_PROPERTIES:
            prop_config = tools_sensorthings.EPANET_OBSERVED_PROPERTIES[prop]
            try:
                if prop in results.link:
                    values = results.link[prop][link_id]
                else:
                    continue

                observations = []
                current_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

                for timestamp, value in values.items():
                    observations.append({
                        "phenomenonTime": (start_time + timedelta(seconds=timestamp)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "result": float(value),
                        "resultTime": current_time
                    })

                datastream = {
                    "name": f"{prop_config['name']} at {link_id}",
                    "description": f"The {prop_config['name'].lower()} at EPANET {link_type} {link_id}",
                    "unitOfMeasurement": prop_config['unit'],
                    "observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement",
                    "Sensor": {"@iot.id": sensor_ids['simulated']},
                    "ObservedProperty": {"@iot.id": property_ids[prop]},
                    "Observations": observations
                }
                datastreams.append(datastream)

            except Exception as e:
                tools_log.log_warning(f"Could not process {prop} for {link_id}: {e}")

        thing_data = {
            "name": link_id,
            "description": f"EPANET {link_type} {link_id}",
            "Locations": [{
                "name": f"{link_id} Location",
                "description": f"Location of EPANET {link_type} {link_id}",
                "encodingType": "application/geo+json",
                "location": {
                    "type": "LineString",
                    "coordinates": transformed_vertices
                }
            }],
            "Datastreams": datastreams,
            "properties": {
                "link_type": link_type
            }
        }
        things_data.append(thing_data)

    return things_data


def _get_geometry_from_link(link: wntr.network.Link) -> list[tuple[float, float]]:
    """Get geometry coordinates for a link including vertices."""
    start_node = link.start_node
    end_node = link.end_node

    # Check if nodes have coordinates
    if start_node.coordinates is None or len(start_node.coordinates) < 2:
        return []
    if end_node.coordinates is None or len(end_node.coordinates) < 2:
        return []

    start_coords = (start_node.coordinates[0], start_node.coordinates[1])
    end_coords = (end_node.coordinates[0], end_node.coordinates[1])

    # Get vertices if they exist (link has vertices property)
    vertices = []
    if hasattr(link, 'vertices') and link.vertices is not None:
        # WNTR stores vertices as a list of (x, y) tuples or lists
        for v in link.vertices:
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                vertices.append((float(v[0]), float(v[1])))

    # Combine start node, vertices, and end node
    coordinates = []
    coordinates.append(start_coords)
    coordinates.extend(vertices)
    coordinates.append(end_coords)

    return coordinates

# endregion