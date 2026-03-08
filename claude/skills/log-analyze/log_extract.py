#!/usr/bin/env python3
"""ArduPilot DataFlash log extraction tool for Claude Code.

Provides structured extraction of .bin log data for analysis.
All output goes to stdout (except plots to file). Read-only — never modifies logs.

Usage:
    python3 log_extract.py overview <logfile>
    python3 log_extract.py extract <logfile> --types XKF1,BARO [--fields ...] [--condition ...]
    python3 log_extract.py compare <logfile> --recipe altitude
    python3 log_extract.py plot <logfile> --recipe altitude --output /tmp/plot.png
"""

import argparse
import csv
import io
import os
import sys

# Find pymavlink from the ArduPilot repo submodule
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Walk up from .claude/skills/log-analyze/ to repo root
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
PYMAVLINK_DIR = os.path.join(REPO_ROOT, 'modules', 'mavlink')
if os.path.exists(PYMAVLINK_DIR):
    sys.path.insert(0, PYMAVLINK_DIR)

os.environ['MAVLINK20'] = '1'

from pymavlink import mavutil


# ---------------------------------------------------------------------------
# Lookup tables from AP_Logger.h
# ---------------------------------------------------------------------------

EVENT_NAMES = {
    10: 'ARMED', 11: 'DISARMED', 15: 'AUTO_ARMED',
    17: 'LAND_COMPLETE_MAYBE', 18: 'LAND_COMPLETE', 19: 'LOST_GPS',
    21: 'FLIP_START', 22: 'FLIP_END',
    25: 'SET_HOME', 26: 'SET_SIMPLE_ON', 27: 'SET_SIMPLE_OFF',
    28: 'NOT_LANDED', 29: 'SET_SUPERSIMPLE_ON',
    30: 'AUTOTUNE_INITIALISED', 31: 'AUTOTUNE_OFF',
    32: 'AUTOTUNE_RESTART', 33: 'AUTOTUNE_SUCCESS',
    34: 'AUTOTUNE_FAILED', 35: 'AUTOTUNE_REACHED_LIMIT',
    36: 'AUTOTUNE_PILOT_TESTING', 37: 'AUTOTUNE_SAVEDGAINS',
    38: 'SAVE_TRIM', 39: 'SAVEWP_ADD_WP',
    41: 'FENCE_ENABLE', 42: 'FENCE_DISABLE',
    43: 'ACRO_TRAINER_OFF', 44: 'ACRO_TRAINER_LEVELING',
    45: 'ACRO_TRAINER_LIMITED',
    46: 'GRIPPER_GRAB', 47: 'GRIPPER_RELEASE',
    49: 'PARACHUTE_DISABLED', 50: 'PARACHUTE_ENABLED',
    51: 'PARACHUTE_RELEASED',
    52: 'LANDING_GEAR_DEPLOYED', 53: 'LANDING_GEAR_RETRACTED',
    54: 'MOTORS_EMERGENCY_STOPPED', 55: 'MOTORS_EMERGENCY_STOP_CLEARED',
    56: 'MOTORS_INTERLOCK_DISABLED', 57: 'MOTORS_INTERLOCK_ENABLED',
    58: 'ROTOR_RUNUP_COMPLETE', 59: 'ROTOR_SPEED_BELOW_CRITICAL',
    60: 'EKF_ALT_RESET', 61: 'LAND_CANCELLED_BY_PILOT',
    62: 'EKF_YAW_RESET',
    63: 'AVOIDANCE_ADSB_ENABLE', 64: 'AVOIDANCE_ADSB_DISABLE',
    65: 'AVOIDANCE_PROXIMITY_ENABLE', 66: 'AVOIDANCE_PROXIMITY_DISABLE',
    67: 'GPS_PRIMARY_CHANGED',
    71: 'ZIGZAG_STORE_A', 72: 'ZIGZAG_STORE_B',
    73: 'LAND_REPO_ACTIVE',
    74: 'STANDBY_ENABLE', 75: 'STANDBY_DISABLE',
    76: 'FENCE_ALT_MAX_ENABLE', 77: 'FENCE_ALT_MAX_DISABLE',
    78: 'FENCE_CIRCLE_ENABLE', 79: 'FENCE_CIRCLE_DISABLE',
    80: 'FENCE_ALT_MIN_ENABLE', 81: 'FENCE_ALT_MIN_DISABLE',
    82: 'FENCE_POLYGON_ENABLE', 83: 'FENCE_POLYGON_DISABLE',
    85: 'EK3_SOURCES_SET_TO_PRIMARY',
    86: 'EK3_SOURCES_SET_TO_SECONDARY',
    87: 'EK3_SOURCES_SET_TO_TERTIARY',
    90: 'AIRSPEED_PRIMARY_CHANGED',
    163: 'SURFACED', 164: 'NOT_SURFACED',
    165: 'BOTTOMED', 166: 'NOT_BOTTOMED',
}

ERROR_SUBSYS = {
    1: 'MAIN', 2: 'RADIO', 3: 'COMPASS', 4: 'OPTFLOW',
    5: 'FAILSAFE_RADIO', 6: 'FAILSAFE_BATT', 7: 'FAILSAFE_GPS',
    8: 'FAILSAFE_GCS', 9: 'FAILSAFE_FENCE',
    10: 'FLIGHT_MODE', 11: 'GPS', 12: 'CRASH_CHECK',
    13: 'FLIP', 14: 'AUTOTUNE', 15: 'PARACHUTES',
    16: 'EKFCHECK', 17: 'FAILSAFE_EKFINAV', 18: 'BARO',
    19: 'CPU', 20: 'FAILSAFE_ADSB', 21: 'TERRAIN',
    22: 'NAVIGATION', 23: 'FAILSAFE_TERRAIN', 24: 'EKF_PRIMARY',
    25: 'THRUST_LOSS_CHECK', 26: 'FAILSAFE_SENSORS',
    27: 'FAILSAFE_LEAK', 28: 'PILOT_INPUT',
    29: 'FAILSAFE_VIBE', 30: 'INTERNAL_ERROR',
    31: 'FAILSAFE_DEADRECKON',
}

# Key parameters to show in overview (prefix match)
KEY_PARAM_PREFIXES = [
    'FRAME_CLASS', 'FRAME_TYPE',
    'EK3_SRC', 'EK3_RNG_USE_HGT', 'EK3_ALT_M_NSE', 'EK3_GPS_TYPE',
    'TKOFF_GNDEFF', 'BARO1_THST_SCALE', 'BARO1_THST_FILT',
    'ARMING_CHECK', 'BRD_TYPE',
    'GPS_TYPE', 'RNGFND1_TYPE', 'RNGFND1_MAX_CM',
    'FLTMODE', 'INS_ACCEL_FILTER', 'INS_GYRO_FILTER',
    'INS_ACC_VRFB_Z', 'INS_ACC2_VRFB_Z', 'INS_ACC3_VRFB_Z',
    'ACC_ZBIAS_LEARN',
    'SCR_ENABLE',
]

# Compare recipes: (msg_type, field, display_label, transform)
RECIPES = {
    'altitude': {
        'title': 'Altitude Comparison',
        'sources': [
            ('BARO', 'Alt', 'BARO.Alt', None),
            ('RFND', 'Dist', 'RFND.Dist', None),
            ('XKF1', 'PD', 'EKF.Alt(m)', 'negate'),
            # Copter CTUN
            ('CTUN', 'Alt', 'CTUN.Alt', None),
            ('CTUN', 'DAlt', 'CTUN.DAlt', None),
            ('CTUN', 'BAlt', 'CTUN.BAlt', None),
            # Plane QuadPlane QTUN
            ('QTUN', 'Alt', 'QTUN.Alt', None),
            ('QTUN', 'DAlt', 'QTUN.DAlt', None),
            ('QTUN', 'BAlt', 'QTUN.BAlt', None),
        ],
    },
    'attitude': {
        'title': 'Attitude Comparison',
        'sources': [
            ('ATT', 'Roll', 'ATT.Roll', None),
            ('ATT', 'Pitch', 'ATT.Pitch', None),
            ('ATT', 'Yaw', 'ATT.Yaw', None),
            ('ATT', 'DesRoll', 'ATT.DesRoll', None),
            ('ATT', 'DesPitch', 'ATT.DesPitch', None),
            ('ATT', 'DesYaw', 'ATT.DesYaw', None),
        ],
    },
    'vibration': {
        'title': 'Vibration Analysis',
        'sources': [
            ('IMU', 'AccX', 'IMU.AccX', None),
            ('IMU', 'AccY', 'IMU.AccY', None),
            ('IMU', 'AccZ', 'IMU.AccZ', None),
            ('VIBE', 'VibeX', 'VIBE.X', None),
            ('VIBE', 'VibeY', 'VIBE.Y', None),
            ('VIBE', 'VibeZ', 'VIBE.Z', None),
        ],
    },
    'ekf_health': {
        'title': 'EKF Health',
        'sources': [
            ('XKF4', 'SV', 'Vel.Var', None),
            ('XKF4', 'SP', 'Pos.Var', None),
            ('XKF4', 'SH', 'Hgt.Var', None),
            ('XKF4', 'SM', 'Mag.Var', None),
            ('XKF4', 'SVT', 'Tilt.Err', None),
        ],
    },
    'rc': {
        'title': 'RC Input/Output',
        'sources': [
            ('RCIN', 'C1', 'RCIN.C1', None),
            ('RCIN', 'C2', 'RCIN.C2', None),
            ('RCIN', 'C3', 'RCIN.C3', None),
            ('RCIN', 'C4', 'RCIN.C4', None),
            ('RCOU', 'C1', 'RCOU.C1', None),
            ('RCOU', 'C2', 'RCOU.C2', None),
            ('RCOU', 'C3', 'RCOU.C3', None),
            ('RCOU', 'C4', 'RCOU.C4', None),
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def open_log(filename):
    """Open a log file with mavutil, return the connection object."""
    if not os.path.exists(filename):
        print(f"Error: file not found: {filename}", file=sys.stderr)
        sys.exit(1)
    return mavutil.mavlink_connection(filename)


def msg_time_s(msg, time_base):
    """Return message time in seconds from log start."""
    return msg._timestamp - time_base


def get_time_base(mlog):
    """Get the timestamp of the first message (for relative times)."""
    mlog._rewind()
    m = mlog.recv_msg()
    if m is None:
        return 0
    t = m._timestamp
    mlog._rewind()
    return t


def get_field_names(mlog, msg_type):
    """Get field names for a message type."""
    if hasattr(mlog, 'name_to_id') and msg_type in mlog.name_to_id:
        fmt_id = mlog.name_to_id[msg_type]
        if fmt_id in mlog.formats:
            return mlog.formats[fmt_id].columns
    return []


def get_instance_field(msg_type):
    """Return the instance/core field name for multi-instance messages."""
    # EKF messages use 'C' for core index
    if msg_type.startswith('XK'):
        return 'C'
    # IMU messages use 'I' for instance
    if msg_type in ('IMU', 'IMU2', 'IMU3', 'ACC', 'GYR'):
        return 'I'
    return None


def format_duration(seconds):
    """Format seconds as human-readable duration."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    elif m > 0:
        return f"{m}m{s:02d}s"
    else:
        return f"{s}s"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_overview(args):
    """Show log overview: message types, key params, events, modes."""
    mlog = open_log(args.log)
    time_base = get_time_base(mlog)

    # -- file info --
    file_size = os.path.getsize(args.log)
    print(f"=== LOG OVERVIEW ===")
    print(f"File: {os.path.abspath(args.log)}")
    print(f"Size: {file_size / (1024*1024):.1f} MB")

    # -- message types --
    types_info = []
    if hasattr(mlog, 'name_to_id'):
        for name, type_id in sorted(mlog.name_to_id.items()):
            count = mlog.counts[type_id]
            if count == 0:
                continue
            columns = []
            if type_id in mlog.formats:
                columns = list(mlog.formats[type_id].columns)
            types_info.append((name, count, columns))

    total_msgs = sum(t[1] for t in types_info)
    print(f"\n=== MESSAGE TYPES ({len(types_info)} types, {total_msgs:,} messages) ===")
    for name, count, columns in types_info:
        cols_str = ','.join(columns) if columns else ''
        # truncate long field lists
        if len(cols_str) > 80:
            cols_str = cols_str[:77] + '...'
        print(f"  {name:<14s} {count:>8,}  {cols_str}")

    # -- key parameters --
    if hasattr(mlog, 'params') and mlog.params:
        print(f"\n=== KEY PARAMETERS ===")
        for prefix in KEY_PARAM_PREFIXES:
            for pname in sorted(mlog.params.keys()):
                if pname.startswith(prefix):
                    print(f"  {pname} = {mlog.params[pname]}")

    # -- flight modes --
    try:
        mode_list = mlog.flightmode_list()
        if mode_list:
            print(f"\n=== FLIGHT MODES ===")
            for mode, t_start, t_end in mode_list:
                rs = t_start - time_base
                re = t_end - time_base
                print(f"  {rs:7.1f}s - {re:7.1f}s: {mode}")
    except Exception:
        pass

    # -- events and errors (single pass) --
    events = []
    errors = []
    mlog._rewind()
    while True:
        m = mlog.recv_match(type=['EV', 'ERR'])
        if m is None:
            break
        t = msg_time_s(m, time_base)
        mtype = m.get_type()
        if mtype == 'EV':
            ev_id = m.Id
            ev_name = EVENT_NAMES.get(ev_id, f'UNKNOWN({ev_id})')
            events.append((t, ev_id, ev_name))
        elif mtype == 'ERR':
            subsys = getattr(m, 'Subsys', 0)
            code = getattr(m, 'ECode', 0)
            subsys_name = ERROR_SUBSYS.get(subsys, f'UNKNOWN({subsys})')
            errors.append((t, subsys, subsys_name, code))

    if events:
        print(f"\n=== EVENTS ===")
        for t, ev_id, ev_name in events:
            print(f"  {t:7.1f}s: {ev_name}")

    if errors:
        print(f"\n=== ERRORS ===")
        for t, subsys, subsys_name, code in errors:
            print(f"  {t:7.1f}s: {subsys_name} Code={code}")

    # -- time range --
    first_t = 0
    last_t = 0
    if events:
        last_t = max(e[0] for e in events)
    # try to get the actual last timestamp by reading total duration
    mlog._rewind()
    while True:
        m = mlog.recv_msg()
        if m is None:
            break
        last_t = msg_time_s(m, time_base)

    print(f"\n=== TIME RANGE ===")
    print(f"  Duration: {format_duration(last_t)}")
    print(f"  Total: {last_t:.1f}s")


def cmd_extract(args):
    """Extract message data as CSV."""
    mlog = open_log(args.log)
    time_base = get_time_base(mlog)

    types = [t.strip() for t in args.types.split(',')]
    req_fields = None
    if args.fields:
        req_fields = [f.strip() for f in args.fields.split(',')]

    # determine output fields per type
    type_fields = {}
    for t in types:
        all_fields = get_field_names(mlog, t)
        if req_fields:
            # filter to only requested fields that exist in this type
            type_fields[t] = [f for f in req_fields if f in all_fields]
        else:
            # skip TimeUS since we provide time_s
            type_fields[t] = [f for f in all_fields if f != 'TimeUS']

    # build CSV header
    multi_type = len(types) > 1
    header = ['time_s']
    if multi_type:
        header.append('type')
    # use union of all fields if multi-type
    if multi_type:
        all_out_fields = []
        for t in types:
            for f in type_fields[t]:
                if f not in all_out_fields:
                    all_out_fields.append(f)
        header.extend(all_out_fields)
    else:
        all_out_fields = type_fields[types[0]]
        header.extend(all_out_fields)

    writer = csv.writer(sys.stdout)
    writer.writerow(header)

    mlog._rewind()
    count = 0
    skip_count = 0
    while True:
        m = mlog.recv_match(type=types, condition=args.condition)
        if m is None:
            break

        t = msg_time_s(m, time_base)

        # time range filter
        if args.from_time is not None and t < args.from_time:
            continue
        if args.to_time is not None and t > args.to_time:
            break

        # decimation
        if args.decimate > 1:
            skip_count += 1
            if skip_count % args.decimate != 1:
                continue

        mtype = m.get_type()
        row = [f"{t:.4f}"]
        if multi_type:
            row.append(mtype)
        for f in all_out_fields:
            if f in type_fields.get(mtype, []):
                row.append(getattr(m, f, ''))
            else:
                row.append('')
        writer.writerow(row)

        count += 1
        if args.limit > 0 and count >= args.limit:
            print(f"# Output limited to {args.limit} rows. Use --limit 0 for all.",
                  file=sys.stderr)
            break


def cmd_compare(args):
    """Time-aligned multi-source comparison."""
    if args.recipe and args.recipe in RECIPES:
        recipe = RECIPES[args.recipe]
        sources = recipe['sources']
        title = recipe['title']
    elif args.sources:
        # custom: "BARO.Alt,RFND.Dist,-XKF1.PD"
        sources = []
        for spec in args.sources.split(','):
            spec = spec.strip()
            transform = None
            if spec.startswith('-'):
                transform = 'negate'
                spec = spec[1:]
            parts = spec.split('.')
            if len(parts) != 2:
                print(f"Error: invalid source spec '{spec}', expected TYPE.FIELD",
                      file=sys.stderr)
                sys.exit(1)
            sources.append((parts[0], parts[1], spec, transform))
        title = 'Custom Comparison'
    else:
        print("Error: specify --recipe or --sources", file=sys.stderr)
        sys.exit(1)

    mlog = open_log(args.log)
    time_base = get_time_base(mlog)

    # Collect raw data for each source
    source_data = {}  # label -> [(time_s, value), ...]
    needed_types = set()
    for msg_type, field, label, transform in sources:
        source_data[label] = []
        needed_types.add(msg_type)

    mlog._rewind()
    while True:
        m = mlog.recv_match(type=list(needed_types))
        if m is None:
            break
        t = msg_time_s(m, time_base)
        if args.from_time is not None and t < args.from_time:
            continue
        if args.to_time is not None and t > args.to_time:
            break
        mtype = m.get_type()

        for msg_type, field, label, transform in sources:
            if mtype != msg_type:
                continue
            val = getattr(m, field, None)
            if val is None:
                continue
            # for multi-instance messages, default to instance 0
            inst_field = get_instance_field(msg_type)
            if inst_field:
                inst = getattr(m, inst_field, 0)
                if inst != 0:
                    continue
            if transform == 'negate':
                val = -val
            source_data[label].append((t, float(val)))

    # Build time-aligned grid
    all_times = set()
    for label, data in source_data.items():
        for t, v in data:
            all_times.add(t)
    if not all_times:
        print("No data found for comparison.", file=sys.stderr)
        return

    t_min = min(all_times)
    t_max = max(all_times)
    interval = args.interval
    grid_times = []
    t = t_min
    while t <= t_max:
        grid_times.append(round(t, 4))
        t += interval

    # Nearest-neighbor interpolation to grid
    def nearest_interp(data, grid):
        """For each grid point, find nearest data point."""
        if not data:
            return [None] * len(grid)
        result = []
        di = 0
        for gt in grid:
            # advance data index to nearest
            while di < len(data) - 1 and abs(data[di + 1][0] - gt) < abs(data[di][0] - gt):
                di += 1
            # only use if within 2x interval
            if abs(data[di][0] - gt) <= interval * 2:
                result.append(data[di][1])
            else:
                result.append(None)
        return result

    # Build aligned data, skip sources with no data
    aligned = {}
    labels = [s[2] for s in sources if source_data[s[2]]]
    for label in labels:
        aligned[label] = nearest_interp(source_data[label], grid_times)

    if not labels:
        print("No data found for any source.", file=sys.stderr)
        return

    # Output CSV
    writer = csv.writer(sys.stdout)
    writer.writerow(['time_s'] + labels)

    count = 0
    for i, t in enumerate(grid_times):
        row = [f"{t:.3f}"]
        for label in labels:
            val = aligned[label][i]
            if val is not None:
                row.append(f"{val:.4f}")
            else:
                row.append('')
        writer.writerow(row)
        count += 1
        if args.limit > 0 and count >= args.limit:
            print(f"# Output limited to {args.limit} rows. Use --limit 0 for all.",
                  file=sys.stderr)
            break


def cmd_plot(args):
    """Generate matplotlib plot and save to file."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. Install with: pip3 install matplotlib",
              file=sys.stderr)
        sys.exit(1)

    # Determine what to plot
    if args.recipe and args.recipe in RECIPES:
        recipe = RECIPES[args.recipe]
        sources = recipe['sources']
        title = args.title or recipe['title']
    elif args.types and args.fields:
        # manual: --types XKF1 --fields PD,VD
        types = [t.strip() for t in args.types.split(',')]
        fields = [f.strip() for f in args.fields.split(',')]
        sources = []
        for t in types:
            for f in fields:
                sources.append((t, f, f"{t}.{f}", None))
        title = args.title or f"{','.join(types)} - {','.join(fields)}"
    else:
        print("Error: specify --recipe or both --types and --fields", file=sys.stderr)
        sys.exit(1)

    mlog = open_log(args.log)
    time_base = get_time_base(mlog)

    # Collect data
    series = {}  # label -> (times[], values[])
    needed_types = set()
    for msg_type, field, label, transform in sources:
        series[label] = ([], [])
        needed_types.add(msg_type)

    mlog._rewind()
    while True:
        m = mlog.recv_match(type=list(needed_types))
        if m is None:
            break
        t = msg_time_s(m, time_base)
        if args.from_time is not None and t < args.from_time:
            continue
        if args.to_time is not None and t > args.to_time:
            break
        mtype = m.get_type()

        for msg_type, field, label, transform in sources:
            if mtype != msg_type:
                continue
            val = getattr(m, field, None)
            if val is None:
                continue
            inst_field = get_instance_field(msg_type)
            if inst_field:
                inst = getattr(m, inst_field, 0)
                if inst != 0:
                    continue
            if transform == 'negate':
                val = -val
            series[label][0].append(t)
            series[label][1].append(float(val))

    # Plot
    fig, ax = plt.subplots(figsize=(14, 6))
    for msg_type, field, label, transform in sources:
        times, values = series[label]
        if times:
            ax.plot(times, values, label=label, linewidth=0.8)

    ax.set_xlabel('Time (s)')
    ax.set_title(title)
    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    output = args.output
    fig.savefig(output, dpi=150)
    plt.close(fig)
    print(f"Plot saved to: {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='ArduPilot DataFlash log extraction tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest='command')

    # overview
    p_ov = subparsers.add_parser('overview', help='Log overview: types, params, modes, events')
    p_ov.add_argument('log', help='Path to .bin log file')

    # extract
    p_ex = subparsers.add_parser('extract', help='Extract message data as CSV')
    p_ex.add_argument('log', help='Path to .bin log file')
    p_ex.add_argument('--types', required=True,
                       help='Message types (comma-separated, e.g. XKF1,BARO)')
    p_ex.add_argument('--fields', default=None,
                       help='Fields to extract (comma-separated, default: all)')
    p_ex.add_argument('--condition', default=None,
                       help='Filter condition (pymavlink syntax, e.g. "XKF1.C==0")')
    p_ex.add_argument('--from-time', type=float, default=None,
                       help='Start time in seconds from log start')
    p_ex.add_argument('--to-time', type=float, default=None,
                       help='End time in seconds from log start')
    p_ex.add_argument('--limit', type=int, default=5000,
                       help='Max rows to output (0=unlimited, default=5000)')
    p_ex.add_argument('--decimate', type=int, default=1,
                       help='Output every Nth message (default=1, no decimation)')

    # compare
    p_cmp = subparsers.add_parser('compare',
                                   help='Time-aligned multi-source comparison')
    p_cmp.add_argument('log', help='Path to .bin log file')
    p_cmp.add_argument('--recipe', choices=list(RECIPES.keys()),
                        help='Pre-built comparison recipe')
    p_cmp.add_argument('--sources', default=None,
                        help='Custom sources (e.g. "BARO.Alt,RFND.Dist,-XKF1.PD")')
    p_cmp.add_argument('--from-time', type=float, default=None,
                        help='Start time in seconds')
    p_cmp.add_argument('--to-time', type=float, default=None,
                        help='End time in seconds')
    p_cmp.add_argument('--limit', type=int, default=5000,
                        help='Max rows (0=unlimited, default=5000)')
    p_cmp.add_argument('--interval', type=float, default=0.1,
                        help='Grid interval in seconds (default=0.1)')

    # plot
    p_pl = subparsers.add_parser('plot', help='Generate plot and save to file')
    p_pl.add_argument('log', help='Path to .bin log file')
    p_pl.add_argument('--recipe', choices=list(RECIPES.keys()),
                       help='Pre-built plot recipe')
    p_pl.add_argument('--types', default=None,
                       help='Message types (for custom plot)')
    p_pl.add_argument('--fields', default=None,
                       help='Fields to plot (for custom plot)')
    p_pl.add_argument('--condition', default=None,
                       help='Filter condition')
    p_pl.add_argument('--from-time', type=float, default=None,
                       help='Start time in seconds')
    p_pl.add_argument('--to-time', type=float, default=None,
                       help='End time in seconds')
    p_pl.add_argument('--output', default='/tmp/ardupilot_plot.png',
                       help='Output file path (default: /tmp/ardupilot_plot.png)')
    p_pl.add_argument('--title', default=None, help='Plot title')

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'overview':
        cmd_overview(args)
    elif args.command == 'extract':
        cmd_extract(args)
    elif args.command == 'compare':
        cmd_compare(args)
    elif args.command == 'plot':
        cmd_plot(args)


if __name__ == '__main__':
    main()
