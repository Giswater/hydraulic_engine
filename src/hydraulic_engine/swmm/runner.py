"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
import os

from dataclasses import dataclass, field
from typing import Any, List, Optional, Callable
from pyswmm import Simulation
from datetime import datetime

from ..utils.enums import RunStatus, ExportDataSource
from .rpt_handler import SwmmRptHandler
from .out_handler import SwmmOutHandler
from .models import SwmmFeatureSettings, SwmmOptionsSettings, SwmmOtherSettings
from .inp_handler import SwmmInpHandler
from ..utils import tools_log
from ..utils.tools_api import HeFrostClient


@dataclass
class SwmmRunResult:
    """Result of a SWMM simulation run"""
    status: RunStatus = RunStatus.NOT_RUN
    inp_path: Optional[str] = None
    rpt_path: Optional[str] = None
    out_path: Optional[str] = None
    return_code: Optional[int] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_seconds: Optional[float] = None
    # Simulation statistics
    routing_steps: Optional[int] = None
    flow_routing_error: Optional[float] = None
    runoff_error: Optional[float] = None


class SwmmRunner:
    """
    Class for running SWMM simulations using pyswmm.
    
    pyswmm provides direct access to the SWMM5 computational engine,
    allowing for real-time interaction and progress tracking during simulations.
    
    Example usage:
        # Run simulation
        runner = SwmmRunner(
            inp_path="model.inp",
            rpt_path="results.rpt",
            out_path="results.out",
            progress_callback=on_progress
        )
        result = runner.run()

        # Check results
        if result.status == RunStatus.SUCCESS:
            print(f"Simulation completed successfully in {result.duration_seconds:.2f}s")
            print(f"RPT file: {result.rpt_path}")
            print(f"OUT file: {result.out_path}")
        else:
            print(f"Simulation failed: {result.errors}")

        # Export results to database
        runner.export_result(ExportDataSource.DATABASE)
    """

    def __init__(
        self,
        inp_path: Optional[str] = None,
        rpt_path: Optional[str] = None,
        out_path: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ):
        """Initialize SWMM runner."""
        self.inp_path = inp_path
        self.rpt_path = rpt_path
        self.out_path = out_path
        self.result: Optional[SwmmRunResult] = None
        self.inp: Optional[SwmmInpHandler] = None
        self.rpt: Optional[SwmmRptHandler] = None
        self.out: Optional[SwmmOutHandler] = None
        self._progress_callback = progress_callback

    def _report_progress(self, progress: int, message: str) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(progress, message)

    def _format_time(self, seconds: float) -> str:
        """Format seconds into a human-readable string (e.g., '2m 30s', '1h 15m')."""
        if seconds < 0:
            return "0s"

        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

    def run(
        self,
        feature_settings: Optional[SwmmFeatureSettings] = None,
        options_settings: Optional[SwmmOptionsSettings] = None,
        other_settings: Optional[SwmmOtherSettings] = None,
        step_callback: Optional[Callable[[Any, int], bool]] = None
    ) -> SwmmRunResult:
        """
        Run SWMM simulation using pyswmm.
        
        :param inp_path: Path to INP file
        :param rpt_path: Path for RPT output (optional, derived from inp_path if not provided)
        :param out_path: Path for OUT binary output (optional, derived from inp_path if not provided)
        :param feature_settings: Feature settings for the simulation
        :param options_settings: Options settings for the simulation
        :param other_settings: Other settings for the simulation
        :param step_callback: Callback function to track simulation progress
        :return: SwmmRunResult with simulation results
        """
        result = SwmmRunResult()

        self.inp = SwmmInpHandler()
        if not self.inp.load_file(self.inp_path):
            result.status = RunStatus.ERROR
            result.errors.append(f"Failed to load INP file: {self.inp_path}")
            tools_log.log_error(f"Failed to load INP file: {self.inp_path}")
            return result

        validation = self.inp.validate_inp()
        if not validation["valid"]:
            result.status = RunStatus.ERROR
            result.errors.append(f"INP file validation failed: {self.inp_path}")
            tools_log.log_error(f"INP file validation failed: {self.inp_path}")
            return result

        self.rpt = SwmmRptHandler()
        self.out = SwmmOutHandler()

        # Generate temporary rpt and out file paths
        self.rpt.file_path = str(self.rpt.get_file_path(output_path=self.rpt_path, extension=".rpt"))
        self.out.file_path = str(self.out.get_file_path(output_path=self.out_path, extension=".out"))

        result.inp_path = self.inp.file_path
        result.rpt_path = self.rpt.file_path
        result.out_path = self.out.file_path

        # Modify the INP file with the feature settings, options settings and other settings
        try:
            self.inp.update_inp_from_settings(
                feature_settings=feature_settings,
                options_settings=options_settings,
                other_settings=other_settings,
            )
            temp_inp_path = self.inp.get_file_path(None, ".inp")
            self.inp.write(output_path=temp_inp_path)
            result.inp_path = str(temp_inp_path)
        except Exception as e:
            result.status = RunStatus.ERROR
            result.errors.append(f"Failed to update INP file with settings: {e}")
            tools_log.log_error(f"Failed to update INP file with settings: {e}")
            return result

        self._report_progress(5, "Starting SWMM simulation...")
        tools_log.log_info(f"Running SWMM simulation: {self.inp_path}")

        return self._run_with_pyswmm(result, step_callback)

    def _run_with_pyswmm(self, result: SwmmRunResult, step_callback: Optional[Callable[[Any, int], bool]] = None) -> SwmmRunResult:
        """
        Run simulation using pyswmm library.
        
        :param result: SwmmRunResult object to populate
        :param step_callback: Callback function to track simulation progress
        :return: Updated SwmmRunResult
        """
        import time
        start_time = time.time()

        try:
            self._report_progress(10, "Initializing SWMM engine...")

            # Create simulation with output files
            with Simulation(
                inputfile=result.inp_path,
                reportfile=result.rpt_path,
                outputfile=result.out_path
            ) as sim:

                self._report_progress(15, "SWMM engine initialized, starting simulation...")

                last_progress = 15
                last_report_time = time.time()
                real_start_time = time.time()
                step_count = 0

                # Step through simulation
                for step in sim:
                    step_count += 1
                    percent = sim.percent_complete

                    # Map 0.0-1.0 to 15-100% progress range
                    sim_progress = min(100, int(15 + percent * 85))

                    # Only report every 0.5 seconds to avoid flooding
                    current_real_time = time.time()
                    if sim_progress != last_progress and (current_real_time - last_report_time) >= 0.5:
                        # Calculate ETA based on average step duration
                        elapsed_real = current_real_time - real_start_time
                        if percent > 0:
                            estimated_total_time = elapsed_real / percent
                            remaining_real = estimated_total_time - elapsed_real
                        else:
                            remaining_real = 0

                        remaining_str = self._format_time(remaining_real)
                        datetime_str = sim.current_time.strftime("%Y-%m-%d %H:%M:%S")

                        progress_msg = f"ETA: {remaining_str} | {datetime_str}"
                        self._report_progress(sim_progress, progress_msg)
                        last_progress = sim_progress
                        last_report_time = current_real_time

                    # Call user callback if provided
                    if step_callback:
                        continue_simulation = step_callback(sim, step_count)
                        if not continue_simulation:
                            tools_log.log_info(f"Simulation stopped by callback at step {step_count}")
                            break

                result.routing_steps = step_count

                # Get simulation statistics after completion
                try:
                    result.flow_routing_error = sim.flow_routing_error
                    result.runoff_error = sim.runoff_error
                except AttributeError:
                    pass

            self._report_progress(90, "Simulation completed, checking results...")

            # Check if output files were created
            if os.path.isfile(result.rpt_path):
                # Parse RPT for errors/warnings
                self._parse_rpt_status(result)
                self.rpt.load_file(result.rpt_path)
            else:
                result.status = RunStatus.ERROR
                result.errors.append("RPT file was not created")

            if os.path.isfile(result.out_path):
                self.out.load_file(result.out_path)
            else:
                result.status = RunStatus.ERROR
                result.errors.append("OUT file was not created")

            result.duration_seconds = time.time() - start_time

            # Determine final status
            if result.status == RunStatus.NOT_RUN:
                if result.errors:
                    result.status = RunStatus.ERROR
                elif result.warnings:
                    result.status = RunStatus.WARNING
                else:
                    result.status = RunStatus.SUCCESS

            self._report_progress(100, f"Simulation finished: {result.status.value}")
            tools_log.log_info(
                f"SWMM simulation completed: {result.status.value} "
                f"({result.duration_seconds:.2f}s, {result.routing_steps} steps)"
            )

        except ImportError as e:
            result.status = RunStatus.ERROR
            result.errors.append(f"pyswmm not installed: {e}. Install with: pip install pyswmm")
            tools_log.log_error(f"pyswmm not installed: {e}")

        except Exception as e:
            result.status = RunStatus.ERROR
            result.errors.append(str(e))
            tools_log.log_error(f"SWMM simulation error: {e}")
            result.duration_seconds = time.time() - start_time

        return result

    def _parse_rpt_status(self, result: SwmmRunResult) -> None:
        """
        Parse RPT file for errors and warnings.
        
        :param result: SwmmRunResult to update
        """
        try:
            with open(result.rpt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.split('\n')

            for line in lines:
                line_stripped = line.strip()
                line_lower = line_stripped.lower()

                # Check for run errors
                if 'run was unsuccessful' in line_lower:
                    result.errors.append("SWMM run was unsuccessful")
                    result.status = RunStatus.ERROR

                if 'error' in line_lower and 'error:' in line_lower:
                    result.errors.append(line_stripped)
                    result.status = RunStatus.ERROR

                # Check for warnings
                if line_lower.startswith('warning'):
                    result.warnings.append(line_stripped)

        except Exception as e:
            tools_log.log_warning(f"Could not parse RPT file for status: {e}")

    def export_result(
            self,
            to: ExportDataSource,
            result_id: str,
            batch_size: int = 50,
            max_workers: int = 4,
            crs_from: int = 25831,
            crs_to: int = 4326,
            start_time: Optional[datetime] = None,
            client: Optional[HeFrostClient] = None,
        ) -> bool:
        """
        Export the result file to a specific datasource
        """

        if to == ExportDataSource.DATABASE:
            pass
        elif to == ExportDataSource.FROST:
            return self.out.export_to_frost(
                inp_handler=self.inp,
                result_id=result_id,
                batch_size=batch_size,
                max_workers=max_workers,
                crs_from=crs_from,
                crs_to=crs_to,
                client=client,
            )
