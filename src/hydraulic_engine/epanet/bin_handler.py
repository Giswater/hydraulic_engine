"""
Copyright © 2026 by BGEO. All rights reserved.
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
from wntr.epanet.util import from_si

from .file_handler import EpanetResultHandler, EpanetFileHandler
from .inp_handler import EpanetInpHandler
from ..utils import tools_log
from ..utils.tools_api import get_api_client, HeFrostClient
from ..utils import tools_sensorthings
from ..utils.tools_db import HePgDao, get_connection


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
        handler.export_to_database(result_id="test1")
    """

    def export_to_database(
            self,
            result_id: str,
            inp_handler: EpanetInpHandler,
            round_decimals: int = 2,
            dao: Optional[HePgDao] = None
        ) -> bool:
        """
        Export simulation results to Giswater database.
        
        Fills the following tables:
        - rpt_node: Time series node results (demand, head, pressure, quality)
        - rpt_arc: Time series arc results (flow, velocity, headloss, etc.)
        - rpt_node_stats: Aggregated node statistics (max/min/avg)
        - rpt_arc_stats: Aggregated arc statistics (max/min/avg)
        - selector_rpt_main: Sets the current result for visualization
        - rpt_cat_result: Updates execution metadata
        
        Prerequisites:
        - The rpt_inp_node and rpt_inp_arc tables must be populated by the plugin
          (via gw_fct_pg2epa_main) before calling this method.
        
        :param result_id: The result identifier (must match rpt_cat_result.result_id)
        :param inp_handler: INP handler to get coordinates
        :param round_decimals: Number of decimal places to round the results (default: 2)
        :param dao: Database access object (optional, uses global connection if not provided)
        :return: True if export successful, False otherwise
        """
        if not self.is_loaded():
            tools_log.log_error("No binary file loaded")
            return False

        # Get database connection
        if dao is None:
            dao = get_connection()

        if dao is None or not dao.is_connected():
            tools_log.log_error("No database connection available")
            return False

        results: wntr.sim.SimulationResults = self.file_object

        try:
            tools_log.log_info(f"Starting export to database for result_id: {result_id}")

            # Step 1: Clean previous results for this result_id
            tools_log.log_info("Cleaning previous results...")
            if not _clean_previous_results(dao, result_id):
                return False

            # Step 2: Insert time series data into rpt_node
            tools_log.log_info("Inserting node results...")
            node_count = _insert_node_results(dao, results, result_id, inp_handler, round_decimals)
            tools_log.log_info(f"Inserted {node_count} node result records")

            # Step 3: Insert time series data into rpt_arc
            tools_log.log_info("Inserting arc results...")
            arc_count = _insert_arc_results(dao, results, result_id, inp_handler, round_decimals)
            tools_log.log_info(f"Inserted {arc_count} arc result records")

            # Step 4: Post-process arcs (reverse geometry for negative flows)
            tools_log.log_info("Post-processing arc results...")
            _post_process_arcs(dao, result_id)

            # Step 5: Calculate and insert node statistics
            tools_log.log_info("Calculating node statistics...")
            _insert_node_stats(dao, result_id)

            # Step 6: Calculate and insert arc statistics
            tools_log.log_info("Calculating arc statistics...")
            _insert_arc_stats(dao, result_id)

            # Step 8: Update rpt_cat_result and selectors
            tools_log.log_info("Updating result catalog and selectors...")
            _finalize_import(dao, result_id)

            # Commit all changes
            dao.commit()
            tools_log.log_info(f"Export to database completed successfully for result_id: {result_id}")
            return True

        except Exception as e:
            tools_log.log_error(f"Error exporting to database: {e}")
            dao.rollback()
            return False

    def export_to_frost(
            self,
            inp_handler: EpanetFileHandler,
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


# region Export to Database Helper Functions

def _seconds_to_time_str(seconds: int) -> str:
    """
    Convert seconds to HH:MM:SS time string format.
    
    :param seconds: Time in seconds
    :return: Time string in HH:MM:SS format
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


def _clean_previous_results(dao: HePgDao, result_id: str) -> bool:
    """
    Clean previous results for the given result_id from all rpt tables.
    
    :param dao: Database access object
    :param result_id: Result identifier
    :return: True if successful
    """
    tables_to_clean = [
        'rpt_node',
        'rpt_arc',
        'rpt_node_stats',
        'rpt_arc_stats',
        'rpt_energy_usage',
        'rpt_hydraulic_status'
    ]

    for table in tables_to_clean:
        sql = f"DELETE FROM {table} WHERE result_id = %s"
        if not dao.execute(sql, (result_id,), commit=False):
            tools_log.log_error(f"Failed to clean {table}")
            return False

    return True


def _insert_node_results(dao: HePgDao, results: wntr.sim.SimulationResults, result_id: str, inp_handler: EpanetInpHandler, round_decimals: int = 2) -> int:
    """
    Insert time series node results into rpt_node table.
    
    :param dao: Database access object
    :param results: WNTR SimulationResults object
    :param result_id: Result identifier
    :param inp_handler: INP handler to get node values
    :param round_decimals: Number of decimal places to round the results (default: 2)
    :return: Number of records inserted
    """
    count = 0

    # Get unit system
    try:
        unit_system = getattr(wntr.epanet.util.FlowUnits, inp_handler.file_object.options.hydraulic.inpfile_units)
        if unit_system is None:
            tools_log.log_error(f"Invalid unit system: {inp_handler.file_object.options.hydraulic.inpfile_units}")
            return 0
    except Exception as e:
        tools_log.log_error(f"Error getting unit system: {e}")
        return 0

    # Get available node result types
    node_data = results.node
    if node_data is None:
        return 0

    # Get all node IDs from demand (always present)
    if 'demand' not in node_data:
        tools_log.log_warning("No demand data found in results")
        return 0

    demand_df = node_data['demand']
    node_ids = demand_df.columns.tolist()
    time_steps = demand_df.index.tolist()

    # Prepare data for bulk insert
    records = []
    for time_sec in time_steps:
        time_str = _seconds_to_time_str(int(time_sec))
        for node_id in node_ids:
            top_elev = _convert_from_si(
                value=inp_handler.file_object.nodes[node_id].elevation,
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Elevation,
                round_decimals=round_decimals
            ) if getattr(inp_handler.file_object.nodes[node_id], 'elevation', None) is not None else None
            demand = _convert_from_si(
                value=demand_df.loc[time_sec, node_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Demand,
                round_decimals=round_decimals
            ) if 'demand' in node_data else None
            head = _convert_from_si(
                value=node_data['head'].loc[time_sec, node_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.HydraulicHead,
                round_decimals=round_decimals
            ) if 'head' in node_data else None
            pressure = _convert_from_si(
                value=node_data['pressure'].loc[time_sec, node_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Pressure,
                round_decimals=round_decimals
            ) if 'pressure' in node_data else None
            quality = round(float(node_data['quality'].loc[time_sec, node_id]), round_decimals) if 'quality' in node_data else None

            records.append((result_id, node_id, time_str, top_elev, demand, head, pressure, quality))

    # Bulk insert using executemany
    sql = """
        INSERT INTO rpt_node (result_id, node_id, time, top_elev, demand, head, press, quality)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        if dao.cursor:
            dao.cursor.executemany(sql, records)
            count = len(records)
    except Exception as e:
        tools_log.log_error(f"Error inserting node results: {e}")
        return 0

    return count


def _insert_arc_results(dao: HePgDao, results: wntr.sim.SimulationResults, result_id: str, inp_handler: EpanetInpHandler, round_decimals: int = 2) -> int:
    """
    Insert time series arc results into rpt_arc table.
    
    :param dao: Database access object
    :param results: WNTR SimulationResults object
    :param result_id: Result identifier
    :param inp_handler: INP handler to get link values
    :param round_decimals: Number of decimal places to round the results (default: 2)
    :return: Number of records inserted
    """
    count = 0

    # Get unit system
    try:
        unit_system = getattr(wntr.epanet.util.FlowUnits, inp_handler.file_object.options.hydraulic.inpfile_units)
        if unit_system is None:
            tools_log.log_error(f"Invalid unit system: {inp_handler.file_object.options.hydraulic.inpfile_units}")
            return 0
    except Exception as e:
        tools_log.log_error(f"Error getting unit system: {e}")
        return 0

    # Get available link result types
    link_data = results.link
    if link_data is None:
        return 0

    # Get all link IDs from flowrate (always present)
    if 'flowrate' not in link_data:
        tools_log.log_warning("No flowrate data found in results")
        return 0

    flow_df = link_data['flowrate']
    link_ids = flow_df.columns.tolist()
    time_steps = flow_df.index.tolist()

    # Prepare data for bulk insert
    records = []
    for time_sec in time_steps:
        time_str = _seconds_to_time_str(int(time_sec))
        for link_id in link_ids:
            length = _convert_from_si(
                value=inp_handler.file_object.links[link_id].length,
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Length,
                round_decimals=round_decimals
            ) if getattr(inp_handler.file_object.links[link_id], 'length', None) is not None else None
            diameter = _convert_from_si(
                value=inp_handler.file_object.links[link_id].diameter,
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.PipeDiameter,
                round_decimals=round_decimals
            ) if getattr(inp_handler.file_object.links[link_id], 'diameter', None) is not None else None
            flow = _convert_from_si(
                value=flow_df.loc[time_sec, link_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Flow,
                round_decimals=round_decimals
            ) if 'flowrate' in link_data else None
            velocity = _convert_from_si(
                value=link_data['velocity'].loc[time_sec, link_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.Velocity,
                round_decimals=round_decimals
            ) if 'velocity' in link_data else None
            headloss = _convert_from_si(
                value=link_data['headloss'].loc[time_sec, link_id],
                unit_system=unit_system,
                param=wntr.epanet.util.HydParam.HeadLoss,
                round_decimals=round_decimals
            ) if 'headloss' in link_data else None
            setting = round(float(link_data['setting'].loc[time_sec, link_id]), round_decimals) if 'setting' in link_data else None
            reaction = round(float(link_data['reaction_rate'].loc[time_sec, link_id]), round_decimals) if 'reaction_rate' in link_data else None
            ffactor = round(float(link_data['friction_factor'].loc[time_sec, link_id]), round_decimals) if 'friction_factor' in link_data else None

            # Get status as text
            status = None
            if 'status' in link_data:
                status_val = int(link_data['status'].loc[time_sec, link_id])
                status_map = {0: 'CLOSED', 1: 'OPEN', 2: 'ACTIVE'}
                status = status_map.get(status_val, str(status_val))

            records.append((result_id, link_id, time_str, length, diameter, flow, velocity, headloss, setting, reaction, ffactor, status))

    # Bulk insert using executemany
    sql = """
        INSERT INTO rpt_arc (result_id, arc_id, time, length, diameter, flow, vel, headloss, setting, reaction, ffactor, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        if dao.cursor:
            dao.cursor.executemany(sql, records)
            count = len(records)
    except Exception as e:
        tools_log.log_error(f"Error inserting arc results: {e}")
        return 0

    return count


def _post_process_arcs(dao: HePgDao, result_id: str) -> None:
    """
    Post-process arc results:
    - Reverse geometry in rpt_inp_arc where flow is negative
    - Update flow values to absolute value in rpt_arc
    
    :param dao: Database access object
    :param result_id: Result identifier
    """
    # Reverse geometries where flow is negative
    sql_reverse = """
        UPDATE rpt_inp_arc 
        SET the_geom = ST_Reverse(the_geom) 
        FROM rpt_arc 
        WHERE rpt_arc.arc_id::text = rpt_inp_arc.arc_id 
        AND rpt_arc.flow < 0 
        AND rpt_inp_arc.result_id = %s
    """
    dao.execute(sql_reverse, (result_id,), commit=False)

    # Update flow to absolute value
    sql_abs_flow = """
        UPDATE rpt_arc 
        SET flow = ABS(flow) 
        WHERE flow < 0 AND result_id = %s
    """
    dao.execute(sql_abs_flow, (result_id,), commit=False)


def _insert_node_stats(dao: HePgDao, result_id: str) -> None:
    """
    Calculate and insert node statistics into rpt_node_stats table.
    
    Statistics are calculated by aggregating rpt_node values and joining
    with rpt_inp_node for metadata and geometry.
    
    :param dao: Database access object
    :param result_id: Result identifier
    """
    sql = """
        INSERT INTO rpt_node_stats (
            node_id, result_id, node_type, sector_id, nodecat_id, top_elev,
            demand_max, demand_min, demand_avg,
            head_max, head_min, head_avg,
            press_max, press_min, press_avg,
            quality_max, quality_min, quality_avg,
            the_geom
        )
        SELECT 
            node.node_id,
            %s as result_id,
            node.node_type,
            node.sector_id,
            node.nodecat_id,
            MAX(rpt.head) as top_elev,
            MAX(rpt.demand) AS demand_max,
            MIN(rpt.demand) AS demand_min,
            AVG(rpt.demand)::numeric(12,2) AS demand_avg,
            MAX(rpt.head) AS head_max,
            MIN(rpt.head) AS head_min,
            AVG(rpt.head)::numeric(12,2) AS head_avg,
            MAX(rpt.press) AS press_max,
            MIN(rpt.press) AS press_min,
            AVG(rpt.press)::numeric(12,2) AS press_avg,
            MAX(rpt.quality) AS quality_max,
            MIN(rpt.quality) AS quality_min,
            AVG(rpt.quality)::numeric(12,2) AS quality_avg,
            node.the_geom
        FROM rpt_inp_node node
        JOIN rpt_node rpt ON rpt.node_id::text = node.node_id::text
        WHERE node.result_id = %s AND rpt.result_id = %s
        GROUP BY node.node_id, node.node_type, node.sector_id, node.nodecat_id, node.the_geom
        ORDER BY node.node_id
    """
    dao.execute(sql, (result_id, result_id, result_id), commit=False)


def _insert_arc_stats(dao: HePgDao, result_id: str) -> None:
    """
    Calculate and insert arc statistics into rpt_arc_stats table.
    
    Statistics are calculated by aggregating rpt_arc values and joining
    with rpt_inp_arc for metadata and geometry.
    
    :param dao: Database access object
    :param result_id: Result identifier
    """
    sql = """
        INSERT INTO rpt_arc_stats (
            arc_id, result_id, arc_type, sector_id, arccat_id,
            flow_max, flow_min, flow_avg,
            vel_max, vel_min, vel_avg,
            headloss_max, headloss_min,
            setting_max, setting_min,
            reaction_max, reaction_min,
            ffactor_max, ffactor_min,
            length, tot_headloss_max, tot_headloss_min,
            the_geom
        )
        SELECT 
            arc.arc_id,
            %s as result_id,
            arc.arc_type,
            arc.sector_id,
            arc.arccat_id,
            MAX(rpt.flow) AS flow_max,
            MIN(rpt.flow) AS flow_min,
            AVG(rpt.flow)::numeric(12,2) AS flow_avg,
            MAX(rpt.vel) AS vel_max,
            MIN(rpt.vel) AS vel_min,
            AVG(rpt.vel)::numeric(12,2) AS vel_avg,
            MAX(rpt.headloss) AS headloss_max,
            MIN(rpt.headloss) AS headloss_min,
            MAX(rpt.setting) AS setting_max,
            MIN(rpt.setting) AS setting_min,
            MAX(rpt.reaction) AS reaction_max,
            MIN(rpt.reaction) AS reaction_min,
            MAX(rpt.ffactor) AS ffactor_max,
            MIN(rpt.ffactor) AS ffactor_min,
            arc.length,
            (MAX(rpt.headloss) * arc.length / 1000)::numeric(12, 2) AS tot_headloss_max,
            (MIN(rpt.headloss) * arc.length / 1000)::numeric(12, 2) AS tot_headloss_min,
            arc.the_geom
        FROM rpt_inp_arc arc
        JOIN rpt_arc rpt ON rpt.arc_id::text = arc.arc_id::text
        WHERE arc.result_id = %s AND rpt.result_id = %s
        GROUP BY arc.arc_id, arc.arc_type, arc.sector_id, arc.arccat_id, arc.length, arc.the_geom
        ORDER BY arc.arc_id
    """
    dao.execute(sql, (result_id, result_id, result_id), commit=False)


def _finalize_import(dao: HePgDao, result_id: str) -> None:
    """
    Finalize the import process:
    - Update rpt_cat_result with execution metadata
    - Set selector_rpt_main for current user
    - Clean up null time values
    
    :param dao: Database access object
    :param result_id: Result identifier
    """
    # Update rpt_cat_result
    sql_update_result = """
        UPDATE rpt_cat_result 
        SET exec_date = now(), cur_user = current_user, status = 2, 
        expl_id = (SELECT array_agg(expl_id) FROM selector_expl WHERE cur_user = current_user AND expl_id > 0),
        sector_id = (SELECT array_agg(sector_id) FROM selector_sector WHERE cur_user = current_user AND sector_id > 0)
        WHERE result_id = %s
    """
    dao.execute(sql_update_result, (result_id,), commit=False)

    # Set result selector for current user
    sql_delete_selector = "DELETE FROM selector_rpt_main WHERE cur_user = current_user"
    dao.execute(sql_delete_selector, commit=False)

    sql_insert_selector = "INSERT INTO selector_rpt_main (result_id, cur_user) VALUES (%s, current_user)"
    dao.execute(sql_insert_selector, (result_id,), commit=False)

    # Clean null time values
    sql_clean_node_time = "UPDATE rpt_node SET time = '0:00' WHERE time = 'null' AND result_id = %s"
    dao.execute(sql_clean_node_time, (result_id,), commit=False)

    sql_clean_arc_time = "UPDATE rpt_arc SET time = '0:00' WHERE time = 'null' AND result_id = %s"
    dao.execute(sql_clean_arc_time, (result_id,), commit=False)



def _convert_from_si(value: float, unit_system: wntr.epanet.util.FlowUnits, param: wntr.epanet.util.HydParam, round_decimals: int = 2) -> Optional[float]:
    """Convert value from SI to EPANET units."""
    try:
        return round(float(from_si(unit_system, value, param)), round_decimals)
    except Exception as e:
        tools_log.log_error(f"Error converting value from SI to EPANET units: {e}")
        return None

# endregion

# region Export to FROST-Server Helper Functions

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
