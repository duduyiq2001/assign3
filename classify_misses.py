#!/usr/bin/env python3
"""
Script to classify L1D cache misses into cold, capacity, and conflict types.
Runs gem5 with different cache configurations to isolate each miss type.
"""

import os
import subprocess
import csv
import re
from pathlib import Path


# Configuration parameters for miss classification
CONFIGS = [
    # (name, l1d_size, l1d_assoc, purpose)
    ("baseline", "1kB", 2, "Total misses (cold + capacity + conflict)"),
    ("no_conflict", "1kB", 8, "Cold + capacity misses (no conflict)"),
    ("no_capacity", "8kB", 8, "Cold misses only (no capacity, no conflict)"),
]

# Common parameters
CLOCK_FREQ = "1GHz"
PROGRAM = "queens"
BP_TYPE = "LocalBP"
BP_SIZE = 2048
BP_BITS = 2

# Paths
GEM5_PATH = os.environ.get("GEM5")
if not GEM5_PATH:
    raise RuntimeError("GEM5 environment variable not set")

GEM5_BINARY = os.path.join(GEM5_PATH, "build/X86/gem5.opt")
SCRIPT_DIR = Path(__file__).parent
ASSIGNMENT_SCRIPT = SCRIPT_DIR / "assignment3.py"


def run_gem5_simulation(name, l1d_size, l1d_assoc, output_dir):
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
        f"--clock_freq={CLOCK_FREQ}",
    ]

    print(f"\nRunning {name}: size={l1d_size}, assoc={l1d_assoc}")
    print(f"  Output dir: {output_dir}")

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
    return None


def extract_l1d_misses(output_dir):
    """Extract L1D cache misses from gem5 stats.txt file."""
    stats_file = Path(output_dir) / "stats.txt"

    if not stats_file.exists():
        print(f"  Warning: {stats_file} not found")
        return None

    with open(stats_file, 'r') as f:
        stats_content = f.read()

    l1d_misses = parse_stat(
        stats_content,
        "board.cache_hierarchy.ruby_system.l1_controllers.L1Dcache.m_demand_misses"
    )

    if l1d_misses:
        return int(l1d_misses)
    return None


def main():
    """Main function to run experiments and classify cache misses."""

    results = {}

    # Run simulations for each configuration
    for name, l1d_size, l1d_assoc, purpose in CONFIGS:
        output_dir = SCRIPT_DIR / f"miss_classify_{name}"
        output_dir.mkdir(exist_ok=True)

        # Run simulation
        success = run_gem5_simulation(name, l1d_size, l1d_assoc, output_dir)

        if not success:
            print(f"  Skipping metrics extraction due to failure")
            continue

        # Extract L1D misses
        misses = extract_l1d_misses(output_dir)

        if misses is not None:
            results[name] = {
                "l1d_size": l1d_size,
                "l1d_assoc": l1d_assoc,
                "misses": misses,
                "purpose": purpose
            }
            print(f"  L1D misses: {misses}")
        else:
            print(f"  Failed to extract misses")

    # Calculate miss breakdown
    if len(results) == 3:
        print("\n" + "="*70)
        print("MISS CLASSIFICATION RESULTS")
        print("="*70)

        total_misses = results["baseline"]["misses"]
        cold_capacity_misses = results["no_conflict"]["misses"]
        cold_misses = results["no_capacity"]["misses"]

        capacity_misses = cold_capacity_misses - cold_misses
        conflict_misses = total_misses - cold_capacity_misses

        print(f"\nBaseline config (1kB, 2-way):")
        print(f"  Total L1D misses: {total_misses}")
        print(f"\nMiss breakdown:")
        print(f"  Cold misses:     {cold_misses:5d} ({100*cold_misses/total_misses:5.1f}%)")
        print(f"  Capacity misses: {capacity_misses:5d} ({100*capacity_misses/total_misses:5.1f}%)")
        print(f"  Conflict misses: {conflict_misses:5d} ({100*conflict_misses/total_misses:5.1f}%)")
        print(f"  ---")
        print(f"  Sum:            {cold_misses + capacity_misses + conflict_misses:5d} (should equal total)")

        # Verification
        if cold_misses + capacity_misses + conflict_misses == total_misses:
            print(f"\n✓ Verification passed!")
        else:
            print(f"\n⚠ Warning: Sum doesn't match total!")

        # Write results to CSV
        csv_file = SCRIPT_DIR / "miss_classification.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Miss Type",
                "Total Misses",
                "Percentage",
                "Configuration Used To Discover This"
            ])

            writer.writerow([
                "Total",
                total_misses,
                "100%",
                f"L1D$ Size: {results['baseline']['l1d_size']} — L1D$ Association: {results['baseline']['l1d_assoc']}"
            ])

            writer.writerow([
                "Cold",
                cold_misses,
                f"{100*cold_misses/total_misses:.1f}%",
                f"L1D$ Size: {results['no_capacity']['l1d_size']} — L1D$ Association: {results['no_capacity']['l1d_assoc']}"
            ])

            writer.writerow([
                "Capacity",
                capacity_misses,
                f"{100*capacity_misses/total_misses:.1f}%",
                f"Difference between (1kB, 8-way) and (8kB, 8-way)"
            ])

            writer.writerow([
                "Conflict",
                conflict_misses,
                f"{100*conflict_misses/total_misses:.1f}%",
                f"Difference between (1kB, 2-way) and (1kB, 8-way)"
            ])

        print(f"\n✓ Results written to {csv_file}")

    else:
        print("\n✗ Not all configurations completed successfully")


if __name__ == "__main__":
    main()
