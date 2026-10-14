"""Run one validation subprocess with RSS, swap-growth and elapsed-time guards.

MLX's set_memory_limit is advisory, so it is not a process memory ceiling.
This supervisor polls every second; it cannot prevent instantaneous peaks.
"""
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import psutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--max-rss-gb', type=float, default=64)
    p.add_argument('--min-available-gb', type=float, default=20)
    p.add_argument('--max-swap-growth-gb', type=float, default=2)
    p.add_argument('--timeout-seconds', type=float, default=1800)
    p.add_argument('--report', required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        p.error('Provide a command after --')
    report_path = Path(args.report)
    if report_path.exists():
        raise FileExistsError(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    initial_swap = psutil.swap_memory().used
    peak = 0
    reason = None
    child = subprocess.Popen(command, start_new_session=True)
    process = psutil.Process(child.pid)
    try:
        while child.poll() is None:
            try:
                rss = sum(p.memory_info().rss for p in [process, *process.children(recursive=True)] if p.is_running())
            except psutil.NoSuchProcess:
                continue
            peak = max(peak, rss)
            if rss > args.max_rss_gb * 2**30:
                reason = 'process_tree_rss_limit'
            elif psutil.virtual_memory().available < args.min_available_gb * 2**30:
                reason = 'system_available_memory_floor'
            elif psutil.swap_memory().used - initial_swap > args.max_swap_growth_gb * 2**30:
                reason = 'system_swap_growth_limit'
            elif time.monotonic() - started > args.timeout_seconds:
                reason = 'elapsed_time_limit'
            if reason:
                print(f'Stopping validation: {reason}', flush=True)
                break
            time.sleep(1)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        report = {'exit_code':child.returncode, 'stop_reason':reason,
            'peak_process_tree_rss_gib':round(peak/2**30,3),
            'elapsed_seconds':round(time.monotonic()-started,1)}
        report_path.write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
    raise SystemExit(child.returncode if not reason else 124)


if __name__ == '__main__':
    main()
