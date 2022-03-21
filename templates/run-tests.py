#!/usr/bin/env python3

import argparse
import sys
import subprocess
from pathlib import Path
import time
from typing import List, Literal


OLD_SCRIPTS = [
    "conn-test.sh",
    "sub1-test.sh",
    "sub-unique-test.sh",
]
NUM_CORES : int = {{ emqx_num_cores }}
CLUSTER_NAME : str = "{{ emqx_cluster_name }}"
REPLICANTS : List[str] = [
    {% for replicant_host in groups['replicants'] %}
    "{{ replicant_host }}",
    {% endfor %}
]
CORES : List[str] = [
    {% for core_host in groups['cores'] %}
    "{{ core_host }}",
    {% endfor %}
]

LG_NUM : int = {{ loadgen_num }}
# only for old scripts; doesn't make much sense for newer ones
START_N : int = {{ start_n }}
NUM_PROCS : int = {{ num_procs }}
RESULT_FILE : str = "{{ emqx_script_result_file }}"
# seconds
TIMEOUT : int = {{ timeout }}
NUM_CONNS : int = {{ emqtt_bench_number_of_connections }}
CONN_INTERVAL_MS : int = {{ emqtt_bench_interval }}
PUB_INTERVAL_MS : int = {{ emqtt_bench_pub_interval }}
SESSION_EXPIRY_INTERVAL : int = {{ emqtt_bench_session_expiry_interval }}
LOWMEM_MODE : bool = {{ emqtt_bench_lowmem_mode | default(False) | bool }}
CLIENTID_PREFIX =  {{ "\"" + emqtt_bench_prefix + "\"" if emqtt_bench_prefix is defined else None }}
USE_SHORTIDS : bool = {{ emqtt_bench_shortids | default(False) | bool }}
SUB_QoS : int = {{ emqtt_bench_sub_qos | default(0) }}
PUB_QoS : int = {{ emqtt_bench_pub_qos | default(0) }}
MIN_RANDOM_WAIT : int = {{ emqtt_bench_min_random_wait | default(0) }}
MAX_RANDOM_WAIT : int = {{ emqtt_bench_max_random_wait | default(0) }}
NUM_RETRY_CONNECT : int = {{ emqtt_bench_num_retry_connect | default(0) }}
# ms
FORCE_MAJOR_GC_INTERVAL : int = {{ emqtt_bench_force_major_gc_interval | default(0) }}

BenchCmd = Literal["sub", "pub", "conn"]


def run_old_script(script_name : str) -> List[subprocess.Popen]:
    cwd = "/root/emqtt-bench/"
    script_path = Path(f"{cwd}/{script_name}")
    procs = [
        subprocess.Popen(
            [
                script_path,
                str(i),
                RESULT_FILE
            ],
            cwd = cwd,
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL,
        )
        for i in range(START_N, START_N + NUM_PROCS)
    ]
    return procs


def log(msg : str):
    print(msg)
    prefix = "cluster_test"
    subprocess.run(
        ["logger", "-t", prefix, msg]
    )


def replicant_target(i : int) -> str:
    if REPLICANTS:
        target = REPLICANTS[i % len(REPLICANTS)]
    else:
        target = CORES[i % len(CORES)]
    return target


def spawn_bench(i: int, bench_cmd : BenchCmd, topic : str, qos = 0,
                start_n : int = START_N, num_conns : int = NUM_CONNS) -> subprocess.Popen:
    cwd = "/root/emqtt-bench/"
    script1 = Path(f"{cwd}/with-ipaddrs.sh")
    script2 = Path(f"{cwd}/emqtt_bench")
    args = [
        script1,
        script2,
        bench_cmd,
        "-c", str(num_conns),
        "-i", str(CONN_INTERVAL_MS),
        "-x", str(SESSION_EXPIRY_INTERVAL),
        "-t", topic,
        "-n", str(start_n),
        # start n varies with i as well, to partition the client_id
        # space
        "-h", replicant_target(start_n),
        "-q", str(qos),
        "--num-retry-connect", str(NUM_RETRY_CONNECT),
    ]
    if LOWMEM_MODE:
        args.append("--lowmem")
    if USE_SHORTIDS:
        args.append("--shortids")
    if CLIENTID_PREFIX:
        args += ["--prefix", CLIENTID_PREFIX]
    if bench_cmd == "pub":
        args += [
            "-I", str(PUB_INTERVAL_MS),
            "--min-random-wait", str(MIN_RANDOM_WAIT),
            "--max-random-wait", str(MAX_RANDOM_WAIT),
            "--force-major-gc-interval", str(FORCE_MAJOR_GC_INTERVAL),
        ]
    outfile_path = Path("/", "tmp", f"{RESULT_FILE}.{bench_cmd}.{i}")
    outfile = open(outfile_path, "w+")
    args_str = " ".join(str(a) for a in args)
    outfile.writelines([f"# {args_str}\n\n"])
    proc = subprocess.Popen(
        args,
        cwd = cwd,
        stdout = outfile,
        stderr = outfile,
    )
    return proc


def pub_sub_1_to_1(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    # start_n for the whole loadgen
    start_n_lg = LG_NUM * NUM_PROCS * NUM_CONNS
    # total connections = pubs + subs
    num_conns = NUM_CONNS // 2

    log("spawning subscribers...")
    sub_procs = [
        spawn_bench(i, "sub", topic = "bench/%i/#", qos = SUB_QoS,
                    # start_n for this process
                    start_n = start_n_lg + i * num_conns,
                    num_conns = num_conns)
        for i in range(NUM_PROCS)
    ]
    pid_list += sub_procs
    log(f"subscribers spawned: {sub_procs}")

    # estimated time for the subscriptions to complete
    time_to_stabilize_s = CONN_INTERVAL_MS * num_conns // 1_000 + 120
    time.sleep(time_to_stabilize_s)

    log("spawning publishers...")
    pub_procs = [
        spawn_bench(i, "pub", topic = "bench/%i/test", qos = PUB_QoS,
                    # start_n for this process
                    start_n = start_n_lg + i * num_conns,
                    num_conns = num_conns)
        for i in range(NUM_PROCS)
    ]
    pid_list += pub_procs
    log(f"publishers spawned: {pub_procs}")

    return pid_list


def main(args):
    if args.script in OLD_SCRIPTS:
        procs = run_old_script(args.script)
        try:
            time.sleep(TIMEOUT)
        finally:
            for p in procs:
                p.kill()
    elif args.script == "pub_sub_1_to_1":
        procs = []
        try:
            pub_sub_1_to_1(procs)
            time.sleep(TIMEOUT)
        finally:
            for p in procs:
                p.kill()
    else:
        print("TODO!!!")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("script", type=str)

    args = parser.parse_args()
    main(args)
