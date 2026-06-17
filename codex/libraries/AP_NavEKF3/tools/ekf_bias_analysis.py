#!/usr/bin/env python3
"""
EKF3 Bias Analysis Tool

Analyzes EKF3 logs to compare Z-axis accelerometer bias between original
and replayed data. Useful for validating bias inhibition fixes.

Usage:
    ./ekf_bias_analysis.py <logfile.bin>
    ./ekf_bias_analysis.py <logfile.bin> --plot
    ./ekf_bias_analysis.py <logfile.bin> --csv output.csv

Requires: pymavlink (pip install pymavlink)
Optional: matplotlib (for --plot)
"""

import argparse
import sys
import os

def check_dependencies():
    """Check for required dependencies."""
    try:
        from pymavlink import mavutil
        return True
    except ImportError:
        print("Error: pymavlink not installed. Run: pip install pymavlink")
        return False


def load_log(filename):
    """Load a MAVLink log file and extract relevant messages."""
    from pymavlink import mavutil

    mlog = mavutil.mavlink_connection(filename)

    data = {
        'XKF2': [],  # Accel bias data
        'XKF1': [],  # Position/velocity data
        'ARM': [],   # Arm/disarm events
    }

    while True:
        msg = mlog.recv_match(type=['XKF2', 'XKF1', 'EV'])
        if msg is None:
            break

        msg_type = msg.get_type()

        if msg_type == 'XKF2':
            data['XKF2'].append({
                'time_s': msg.TimeUS / 1e6,
                'core': msg.C,
                'AX': msg.AX,
                'AY': msg.AY,
                'AZ': msg.AZ,
            })
        elif msg_type == 'XKF1':
            data['XKF1'].append({
                'time_s': msg.TimeUS / 1e6,
                'core': msg.C,
                'VN': msg.VN,
                'VE': msg.VE,
                'VD': msg.VD,
                'PD': msg.PD,
            })
        elif msg_type == 'EV':
            # Event messages for arm/disarm
            if msg.Id == 10:  # Armed
                data['ARM'].append({'time_s': msg.TimeUS / 1e6, 'armed': True})
            elif msg.Id == 11:  # Disarmed
                data['ARM'].append({'time_s': msg.TimeUS / 1e6, 'armed': False})

    return data


def filter_by_core(data, core):
    """Filter data by EKF core index."""
    return [d for d in data if d['core'] == core]


def get_value_at_time(data, key, target_time, tolerance=1.0):
    """Get a value from data at a specific time."""
    for d in data:
        if abs(d['time_s'] - target_time) < tolerance:
            return d[key]
    return None


def find_time_range(data):
    """Find the time range of the data."""
    if not data:
        return None, None
    times = [d['time_s'] for d in data]
    return min(times), max(times)


def compute_statistics(values):
    """Compute basic statistics for a list of values."""
    if not values:
        return None
    import statistics
    return {
        'mean': statistics.mean(values),
        'std': statistics.stdev(values) if len(values) > 1 else 0,
        'min': min(values),
        'max': max(values),
        'range': max(values) - min(values),
    }


def analyze_zbias(data, verbose=True):
    """Analyze Z-axis bias data."""
    xkf2 = data['XKF2']

    # Separate by core (0=original IMU0, 100=replayed IMU0)
    original = filter_by_core(xkf2, 0)
    replayed = filter_by_core(xkf2, 100)

    has_replay = len(replayed) > 0

    t_start, t_end = find_time_range(original)

    if verbose:
        print("=" * 70)
        print("EKF3 Z-AXIS BIAS ANALYSIS")
        print("=" * 70)
        print(f"Time range: {t_start:.1f}s to {t_end:.1f}s ({t_end-t_start:.1f}s duration)")
        print(f"Original samples (C=0): {len(original)}")
        print(f"Replayed samples (C=100): {len(replayed)}")
        print()

    # Compute statistics for original
    orig_az = [d['AZ'] for d in original]
    orig_stats = compute_statistics(orig_az)

    if verbose:
        print("Original Z-bias statistics:")
        print(f"  Mean:  {orig_stats['mean']:+.3f} m/s²")
        print(f"  Std:   {orig_stats['std']:.3f} m/s²")
        print(f"  Range: {orig_stats['min']:+.3f} to {orig_stats['max']:+.3f} m/s²")
        print(f"  Drift: {orig_stats['range']:.3f} m/s²")
        print()

    if has_replay:
        repl_az = [d['AZ'] for d in replayed]
        repl_stats = compute_statistics(repl_az)

        if verbose:
            print("Replayed Z-bias statistics:")
            print(f"  Mean:  {repl_stats['mean']:+.3f} m/s²")
            print(f"  Std:   {repl_stats['std']:.3f} m/s²")
            print(f"  Range: {repl_stats['min']:+.3f} to {repl_stats['max']:+.3f} m/s²")
            print(f"  Drift: {repl_stats['range']:.3f} m/s²")
            print()

            improvement = orig_stats['range'] - repl_stats['range']
            print(f"Improvement: {improvement:.3f} m/s² less drift")
            print()

    # Sample at key times
    if verbose:
        print("-" * 70)
        if has_replay:
            print(f"{'Time':>8} {'Phase':<25} {'Original':>12} {'Replayed':>12} {'Delta':>10}")
        else:
            print(f"{'Time':>8} {'Phase':<25} {'Z-bias':>12}")
        print("-" * 70)

    # Generate sample points
    duration = t_end - t_start
    sample_times = []

    # Add start, end, and evenly spaced points
    sample_times.append((t_start + 1, "Start"))
    sample_times.append((t_start + duration * 0.25, "25%"))
    sample_times.append((t_start + duration * 0.50, "50%"))
    sample_times.append((t_start + duration * 0.75, "75%"))
    sample_times.append((t_end - 1, "End"))

    results = []
    for t, phase in sample_times:
        orig_val = get_value_at_time(original, 'AZ', t)
        if orig_val is None:
            continue

        if has_replay:
            repl_val = get_value_at_time(replayed, 'AZ', t)
            delta = repl_val - orig_val if repl_val is not None else None
            results.append({
                'time': t,
                'phase': phase,
                'original': orig_val,
                'replayed': repl_val,
                'delta': delta,
            })
            if verbose and repl_val is not None:
                print(f"{t:>7.1f}s {phase:<25} {orig_val:>+12.3f} {repl_val:>+12.3f} {delta:>+10.3f}")
        else:
            results.append({
                'time': t,
                'phase': phase,
                'original': orig_val,
            })
            if verbose:
                print(f"{t:>7.1f}s {phase:<25} {orig_val:>+12.3f}")

    if verbose:
        print("-" * 70)

    return {
        'original': original,
        'replayed': replayed,
        'orig_stats': orig_stats,
        'repl_stats': repl_stats if has_replay else None,
        'samples': results,
        'has_replay': has_replay,
    }


def plot_zbias(analysis_result, output_file=None):
    """Plot Z-bias comparison."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. Run: pip install matplotlib")
        return

    original = analysis_result['original']
    replayed = analysis_result['replayed']

    fig, axes = plt.subplots(2 if replayed else 1, 1, figsize=(12, 8), sharex=True)
    if not replayed:
        axes = [axes]

    # Plot original
    times_orig = [d['time_s'] for d in original]
    az_orig = [d['AZ'] for d in original]
    axes[0].plot(times_orig, az_orig, 'b-', linewidth=0.5, label='Original (C=0)')
    axes[0].set_ylabel('Z-bias (m/s²)')
    axes[0].set_title('Original EKF3 Z-Axis Accel Bias')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    if replayed:
        times_repl = [d['time_s'] for d in replayed]
        az_repl = [d['AZ'] for d in replayed]
        axes[1].plot(times_repl, az_repl, 'g-', linewidth=0.5, label='Replayed (C=100)')
        axes[1].set_ylabel('Z-bias (m/s²)')
        axes[1].set_xlabel('Time (s)')
        axes[1].set_title('Replayed EKF3 Z-Axis Accel Bias (with fixes)')
        axes[1].grid(True, alpha=0.3)
        axes[1].legend()

        # Match y-axis limits
        ymin = min(min(az_orig), min(az_repl)) - 0.1
        ymax = max(max(az_orig), max(az_repl)) + 0.1
        axes[0].set_ylim(ymin, ymax)
        axes[1].set_ylim(ymin, ymax)
    else:
        axes[0].set_xlabel('Time (s)')

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=150)
        print(f"Plot saved to: {output_file}")
    else:
        plt.show()


def export_csv(analysis_result, output_file):
    """Export data to CSV."""
    original = analysis_result['original']
    replayed = analysis_result['replayed']

    with open(output_file, 'w') as f:
        if replayed:
            f.write("time_s,original_AZ,replayed_AZ\n")
            # Create time-aligned data
            orig_dict = {round(d['time_s'], 2): d['AZ'] for d in original}
            repl_dict = {round(d['time_s'], 2): d['AZ'] for d in replayed}
            all_times = sorted(set(orig_dict.keys()) | set(repl_dict.keys()))
            for t in all_times:
                orig_val = orig_dict.get(t, '')
                repl_val = repl_dict.get(t, '')
                f.write(f"{t},{orig_val},{repl_val}\n")
        else:
            f.write("time_s,AZ\n")
            for d in original:
                f.write(f"{d['time_s']},{d['AZ']}\n")

    print(f"CSV exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='EKF3 Z-axis bias analysis tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s flight.bin                    # Basic analysis
  %(prog)s replay_output.bin --plot      # With plot
  %(prog)s replay_output.bin --csv out.csv  # Export to CSV

Notes:
  - For replay comparison, use the output log from the Replay tool
  - Original data is core C=0, replayed data is core C=100
  - Use --plot to visualize the bias over time
        """
    )
    parser.add_argument('logfile', help='MAVLink log file (.bin)')
    parser.add_argument('--plot', action='store_true', help='Show plot')
    parser.add_argument('--plot-file', type=str, help='Save plot to file')
    parser.add_argument('--csv', type=str, help='Export to CSV file')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress output')

    args = parser.parse_args()

    if not os.path.exists(args.logfile):
        print(f"Error: File not found: {args.logfile}")
        return 1

    if not check_dependencies():
        return 1

    print(f"Loading: {args.logfile}")
    data = load_log(args.logfile)

    if not data['XKF2']:
        print("Error: No XKF2 messages found in log")
        return 1

    result = analyze_zbias(data, verbose=not args.quiet)

    if args.csv:
        export_csv(result, args.csv)

    if args.plot or args.plot_file:
        plot_zbias(result, args.plot_file)

    return 0


if __name__ == '__main__':
    sys.exit(main())
