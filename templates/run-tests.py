#!/usr/bin/env python3

import argparse
import sys
import subprocess
from pathlib import Path
import time
import shlex
from typing import List, Literal, Optional


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

TOTAL_NUM_LG : int = {{ emqx_loadgen_num }}
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
# / s
CONN_RATE : int = {{ emqtt_bench_conn_rate | default(0) }}
NUM_BUCKETS : int = {{ emqtt_bench_num_buckets | default(1) }}

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


def host_targets() -> str:
    if REPLICANTS:
        targets = ",".join(REPLICANTS)
    else:
        targets = ",".join(CORES)
    return targets


def params_for_lg(total_lg_num : int, num_targets : int,
                  total_connections : int, desired_total_conn_rate : int):
    assert total_connections >= total_lg_num, "too few connetions per LG"
    conns_per_lg = total_connections // total_lg_num
    conns_per_target_lg = conns_per_lg // num_targets
    # might loose a few to keep it even.
    conns_per_lg = conns_per_target_lg * num_targets

    conn_rate_per_lg = desired_total_conn_rate // total_lg_num
    start_n_lg = total_lg_num * conns_per_lg
    # FIXME: wrong for more than 1 bucket...
    start_nums_per_lg = [
        start_n_lg + i * conns_per_lg
        for i in range(total_lg_num)
    ]
    return {
        "num_conns": conns_per_lg,
        "conn_rate": conn_rate_per_lg,
        "start_nums": start_nums_per_lg,
    }


def spawn_bench(i: int, bench_cmd : BenchCmd, topic : str, hosts : str, qos = 0,
                start_n : int = START_N, num_conns : int = NUM_CONNS,
                conn_rate : int = CONN_RATE) -> subprocess.Popen:
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
        # the input to this MUST vary by one on each process, across
        # all procs in the same LG, and must be contiguous between all
        # LGs...
        "-d",
        "-h", hosts,
        "-q", str(qos),
        "--num-retry-connect", str(NUM_RETRY_CONNECT),
        "--force-major-gc-interval", str(FORCE_MAJOR_GC_INTERVAL),
    ]
    if LOWMEM_MODE:
        args.append("--lowmem")
    if USE_SHORTIDS:
        args.append("--shortids")
    if CLIENTID_PREFIX:
        args += ["--prefix", CLIENTID_PREFIX]
    if CONN_RATE != 0:
        args += ["--connrate", str(conn_rate)]
    if bench_cmd == "pub":
        args += [
            "-I", str(PUB_INTERVAL_MS),
            "--min-random-wait", str(MIN_RANDOM_WAIT),
            "--max-random-wait", str(MAX_RANDOM_WAIT),
        ]
    outfile_path = Path("/", "tmp", f"{RESULT_FILE}.{bench_cmd}.{i}")
    outfile = open(outfile_path, "w+")
    args_str = shlex.join([str(a) for a in args])
    outfile.writelines([f"# {args_str}\n\n"])
    proc = subprocess.Popen(
        args,
        cwd = cwd,
        stdout = outfile,
        stderr = outfile,
    )
    return proc


def pub_sub_1_to_1(pid_list : List[subprocess.Popen],
                   host_shift : int = 0) -> List[subprocess.Popen]:
    # host_shift is for forcing forwarding between nodes.  If set to a
    # multiple of the number of nodes, i.e., `host_shift %
    # len(REPLICANTS) == 0`, then publishing is local to each node.

    # start_n for the whole loadgen
    start_n_lg = LG_NUM * NUM_PROCS * NUM_CONNS
    # total connections = pubs + subs
    num_conns = NUM_CONNS // 2

    log("spawning subscribers...")
    sub_procs = [
        spawn_bench(i, "sub", topic = "bench/%i/#", qos = SUB_QoS,
                    # start_n for this process
                    start_n = start_n_lg + i * num_conns,
                    num_conns = num_conns, hosts = replicant_target(i))
        for i in range(LG_NUM * NUM_PROCS, (LG_NUM + 1) * NUM_PROCS)
    ]
    pid_list += sub_procs
    log(f"subscribers spawned: {sub_procs}")

    # estimated time for the subscriptions to complete
    time_to_stabilize_s = CONN_INTERVAL_MS * num_conns // 1_000 + 120
    time.sleep(time_to_stabilize_s)

    log("spawning publishers...")
    # shifting only the pubs
    pub_procs = [
        spawn_bench(i, "pub", topic = "bench/%i/test", qos = PUB_QoS,
                    # start_n for this process
                    start_n = start_n_lg + i * num_conns,
                    num_conns = num_conns,
                    hosts = replicant_target(i + host_shift))
        for i in range(LG_NUM * NUM_PROCS, (LG_NUM + 1) * NUM_PROCS)
    ]
    pid_list += pub_procs
    log(f"publishers spawned: {pub_procs}")

    return pid_list


def pub_sub_1_to_1_fwd(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    return pub_sub_1_to_1(pid_list, host_shift=1)


def sub_single_wildcard(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    # this assumes that the bench version being used supports the
    # `--connrate` option and a comma-separated list of hosts in `-h`.

    total_num_conns = NUM_CONNS
    conn_rate = CONN_RATE

    log("spawning subscribers...")
    targets = host_targets()
    num_targets = len(targets)
    params = params_for_lg(TOTAL_NUM_LG, num_targets, total_num_conns, conn_rate)
    sub_procs = [
        spawn_bench(LG_NUM, "sub", topic = "bench/test/#", qos = SUB_QoS,
                    # start_n for this process
                    start_n = params["start_nums"][LG_NUM],
                    num_conns = params["num_conns"], hosts = targets,
                    conn_rate = params["conn_rate"])
    ]
    pid_list += sub_procs
    log(f"spawned subscribers: {pid_list}")
    return pid_list


def sub_single_topic_bucket(pid_list : List[subprocess.Popen],
                            num_buckets : int = NUM_BUCKETS) -> List[subprocess.Popen]:
    # this assumes that the bench version being used supports the
    # `--connrate` option and a comma-separated list of hosts in `-h`.

    total_num_conns = NUM_CONNS
    num_conns_per_bucket = total_num_conns // num_buckets
    conn_rate_per_bucket = CONN_RATE // num_buckets

    log(f"spawning subscribers for {num_buckets} buckets...")
    targets = host_targets()
    num_targets = len(targets)
    params = params_for_lg(TOTAL_NUM_LG, num_targets,
                           num_conns_per_bucket, conn_rate_per_bucket)
    sub_procs = [
        spawn_bench(LG_NUM, "sub", topic = f"bench/test/{i}",
                    qos = SUB_QoS,
                    # start_n for this process
                    # FIXME: wrong for more than 1 bucket...
                    start_n = params["start_nums"][LG_NUM],
                    num_conns = params["num_conns"],
                    hosts = targets,
                    conn_rate = params["conn_rate"])
        for i in range(num_buckets)
    ]
    pid_list += sub_procs
    log(f"spawned subscribers: {pid_list}")
    return pid_list


def try_run(fun):
    procs = []
    try:
        fun(procs)
        time.sleep(TIMEOUT)
    finally:
        for p in procs:
            p.kill()


def main(args):
    if args.script in OLD_SCRIPTS:
        procs = run_old_script(args.script)
        try:
            time.sleep(TIMEOUT)
        finally:
            for p in procs:
                p.kill()
    elif args.script == "pub_sub_1_to_1":
        try_run(pub_sub_1_to_1)
    elif args.script == "pub_sub_1_to_1_fwd":
        try_run(pub_sub_1_to_1_fwd)
    elif args.script == "sub_single_wildcard":
        try_run(sub_single_wildcard)
    else:
        print("TODO!!!")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("script", type=str)

    args = parser.parse_args()
    main(args)
