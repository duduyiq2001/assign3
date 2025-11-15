#!/usr/bin/env python3
"""
Script to run gem5 simulations with different cache configurations
and collect performance metrics.
"""

import os
import subprocess
import csv
import re
from pathlib import Path


# Configuration parameters
CONFIGS = [
    # (clock_freq, l1d_assoc, l1d_size)
    ("1GHz", 2, "1kB"),
    ("1GHz", 2, "2kB"),
    ("1GHz", 2, "4kB"),
    ("1GHz", 2, "8kB"),
    ("0.8GHz", 4, "1kB"),
    ("0.8GHz", 4, "2kB"),
    ("0.8GHz", 4, "4kB"),
    ("0.8GHz", 4, "8kB"),
]

# Common parameters
PROGRAM = "queens"
BP_TYPE = "LocalBP"  # Changed from SimpleBP to LocalBP
BP_SIZE = 16
BP_BITS = 2

# Paths
GEM5_PATH = os.environ.get("GEM5")
if not GEM5_PATH:
    raise RuntimeError("GEM5 environment variable not set")

GEM5_BINARY = os.path.join(GEM5_PATH, "build/X86/gem5.opt")
SCRIPT_DIR = Path(__file__).parent
ASSIGNMENT_SCRIPT = SCRIPT_DIR / "assignment3.py"


def run_gem5_simulation(clock_freq, l1d_assoc, l1d_size, output_dir):
    """Run a single gem5 simulation with the given configuration."""

    cmd = [
        GEM5_BINARY,
        f"--outdir={output_dir}",
        str(ASSIGNMENT_SCRIPT),
        f"--prog={PROGRAM}",
        f"--bp={BP_TYPE}",
        f"--bp_size={BP_SIZE}",
        f"--bp_bits={BP_BITS}",
        f"--l1d_size={l1d_size}",
        f"--l1d_assoc={l1d_assoc}",
        f"--clock_freq={clock_freq}",
    ]

    print(f"Running: clock={clock_freq}, l1d_assoc={l1d_assoc}, l1d_size={l1d_size}")
    print(f"Output dir: {output_dir}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
            cwd=SCRIPT_DIR
        )
        print(f"  ✓ Completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed with error:")
        print(e.stderr)
        return False


def parse_stat(stats_content, stat_name):
    """Extract a stat value from stats.txt content."""
    pattern = rf'^{re.escape(stat_name)}\s+(\S+)'
    match = re.search(pattern, stats_content, re.MULTILINE)
    if match:
        value = match.group(1)
        # Remove any trailing comments or units
        value = value.split('#')[0].strip()
        return value
    return "N/A"


def extract_metrics(output_dir):
    """Extract performance metrics from gem5 stats.txt file."""
    stats_file = Path(output_dir) / "stats.txt"

    if not stats_file.exists():
        print(f"  Warning: {stats_file} not found")
        return None

    with open(stats_file, 'r') as f:
        stats_content = f.read()

    # Extract raw stats
    instructions = parse_stat(stats_content, "board.processor.cores.core.thread_0.numInsts")
    cpu_cycles = parse_stat(stats_content, "board.processor.cores.core.numCycles")

    l1d_hits = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l1_controllers.L1Dcache.m_demand_hits")
    l1d_misses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l1_controllers.L1Dcache.m_demand_misses")
    l1d_accesses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l1_controllers.L1Dcache.m_demand_accesses")

    l1i_misses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l1_controllers.L1Icache.m_demand_misses")
    l1i_accesses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l1_controllers.L1Icache.m_demand_accesses")

    l2_misses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l2_controllers.L2cache.m_demand_misses")
    l2_accesses = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.l2_controllers.L2cache.m_demand_accesses")

    l1_replacements = parse_stat(stats_content, "board.cache_hierarchy.ruby_system.L1Cache_Controller.L1_Replacement")
    avg_gap = parse_stat(stats_content, "board.memory.mem_ctrl.avgGap")

    # Calculate miss rates
    def calc_miss_rate(misses, accesses):
        try:
            return f"{(float(misses) / float(accesses)):.6f}" if accesses != "N/A" and float(accesses) > 0 else "N/A"
        except:
            return "N/A"

    l1d_miss_rate = calc_miss_rate(l1d_misses, l1d_accesses)
    l1i_miss_rate = calc_miss_rate(l1i_misses, l1i_accesses)
    l2_miss_rate = calc_miss_rate(l2_misses, l2_accesses)

    metrics = {
        "instructions_committed": instructions,
        "avg_gap_between_requests": avg_gap,
        "l1d_hits": l1d_hits,
        "l1d_replacements": l1_replacements,
        "l1d_miss_rate": l1d_miss_rate,
        "l1i_miss_rate": l1i_miss_rate,
        "l2_miss_rate": l2_miss_rate,
        "cpu_cycles": cpu_cycles,
    }

    return metrics


def main():
    """Main function to run all experiments and collect results."""

    results = []

    # Run simulations for each configuration
    for clock_freq, l1d_assoc, l1d_size in CONFIGS:
        # Create output directory name
        output_dir = f"results_clk{clock_freq}_assoc{l1d_assoc}_size{l1d_size}"
        output_dir = SCRIPT_DIR / output_dir
        output_dir.mkdir(exist_ok=True)

        # Run simulation
        success = run_gem5_simulation(clock_freq, l1d_assoc, l1d_size, output_dir)

        if not success:
            print(f"  Skipping metrics extraction due to failure")
            continue

        # Extract metrics
        metrics = extract_metrics(output_dir)

        if metrics:
            result = {
                "clock_freq": clock_freq,
                "l1d_assoc": l1d_assoc,
                "l1d_size": l1d_size,
                **metrics
            }
            results.append(result)
            print(f"  Extracted metrics successfully")
        else:
            print(f"  Failed to extract metrics")

    # Write results to CSV
    if results:
        csv_file = SCRIPT_DIR / "experiment_results.csv"
        fieldnames = [
            "clock_freq",
            "l1d_assoc",
            "l1d_size",
            "instructions_committed",
            "avg_gap_between_requests",
            "l1d_hits",
            "l1d_replacements",
            "l1d_miss_rate",
            "l1i_miss_rate",
            "l2_miss_rate",
            "cpu_cycles"
        ]

        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print(f"\n✓ Results written to {csv_file}")
        print(f"  Total configurations tested: {len(results)}")
    else:
        print("\n✗ No results to write")


if __name__ == "__main__":
    main()
