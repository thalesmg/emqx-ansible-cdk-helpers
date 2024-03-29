#!/usr/bin/env python3

import argparse
import sys
import subprocess
from pathlib import Path
import time
import shlex
import itertools
from typing import List, Literal, Optional, Tuple


OLD_SCRIPTS = [
    "conn-test.sh",
    "sub1-test.sh",
    "sub-unique-test.sh",
]
NUM_CORES : int = {{ emqx_num_cores }}
CLUSTER_NAME : str = "{{ emqx_cluster_name }}"
REPLICANTS : List[str] = [
    {% for replicant_host in (groups['replicants'] | default([])) %}
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
PAYLOAD_SIZE : int = {{ emqtt_bench_payload_size | default(256) }}
NUM_INFLIGHT : int = {{ emqtt_bench_num_inflight | default(1) }}
USE_SSL : bool = {{ emqtt_bench_use_ssl | default(False) | bool }}
WAIT_BEFORE_PUBLISHING : bool = {{ emqtt_bench_wait_before_publishing | default(False) | bool }}
# s
RELAXATION_PERIOD : int = {{ emqtt_bench_relaxation_period | default(120) }}
MAYBE_PUBLISH_FUEL : int = {{ emqtt_bench_fuel | default(10) }}
# s
CONNECT_TIMEOUT : int = {{ emqtt_bench_connect_timeout | default(60) }}
RANDOM_HOSTS : bool = {{ emqtt_bench_random_hosts | default(False) | bool }}
# s
MQTT_KEEPALIVE : int = {{ emqtt_bench_mqtt_keepalive | default(300) }}
MQTT_FORCE_PING : bool = {{ emqtt_bench_mqtt_force_ping | default(False) | bool }}

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


def ward_off_oom_killer(proc : subprocess.Popen):
    subprocess.run(f"echo -100 > /proc/{proc.pid}/oom_score_adj", shell=True)


def replicant_target(i : int) -> str:
    if REPLICANTS:
        target = REPLICANTS[i % len(REPLICANTS)]
    else:
        target = CORES[i % len(CORES)]
    return target


def consume(iterable, n):
    next(itertools.islice(iterable, n, n), None)


def take(iterable, n):
    return list(itertools.islice(iterable, n))


def rotate(xs, n):
    nx = len(xs)
    cic = itertools.cycle(xs)
    consume(cic, n)
    return take(cic, nx)


def host_targets(host_shift : int = 0) -> str:
    if REPLICANTS:
        targets = rotate(REPLICANTS, host_shift)
        targets_str = ",".join(targets)
    else:
        targets = rotate(CORES, host_shift)
        targets_str = ",".join(targets)
    return targets_str


def partition_range(a : int, b : int, n : int) -> List[Tuple[(int, int)]]:
    assert n > 0
    step = (b - a) // n
    return [
        (a + step * i, a + step * (i + 1))
        for i in range(0, n)
    ]


def params_for_lg(total_lg_num : int, num_targets : int,
                  total_connections : int, desired_total_conn_rate : int,
                  num_procs : int):
    assert total_connections >= total_lg_num, "too few connetions per LG"
    assert num_procs >= 1
    conns_per_lg = total_connections // total_lg_num
    conns_per_target_lg = conns_per_lg // num_targets
    # might lose a few to keep it even.
    conns_per_lg = conns_per_target_lg * num_targets
    conns_per_proc = conns_per_lg // num_procs

    conn_rate_per_lg = (desired_total_conn_rate // total_lg_num) // num_procs
    max_n_lg = total_lg_num * conns_per_lg

    start_nums_per_lg = [
        [start_n for (start_n, _end_n) in partition_range(a_lg, b_lg, num_procs)]
        for (a_lg, b_lg) in partition_range(0, max_n_lg, total_lg_num)
    ]
    return {
        "num_conns": conns_per_proc,
        "conn_rate": conn_rate_per_lg,
        "start_nums": start_nums_per_lg,
    }


def spawn_bench(lg_num: int, proc_num : int, bench_cmd : BenchCmd, topic : str, hosts : str, qos = 0,
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
        "--connect-timeout", str(CONNECT_TIMEOUT),
        "--keepalive", str(MQTT_KEEPALIVE),
    ]
    if bench_cmd != "conn":
        args += [
            "--force-ping",
        ]
    if LOWMEM_MODE:
        args.append("--lowmem")
    if bench_cmd == "pub" and WAIT_BEFORE_PUBLISHING:
        args.append("--wait-before-publishing")
    if USE_SHORTIDS:
        args.append("--shortids")
    if CLIENTID_PREFIX:
        args += ["--prefix", CLIENTID_PREFIX]
    if CONN_RATE != 0:
        args += ["--connrate", str(conn_rate)]
    if USE_SSL:
        args += [
            "--ssl",
            "--certfile", "/tmp/client-cert.pem",
            "--keyfile", "/tmp/client-key.pem",
            "-p", "8883",
        ]
    if RANDOM_HOSTS:
        args.append("--random-hosts")
    if bench_cmd == "pub":
        args += [
            "-I", str(PUB_INTERVAL_MS),
            "--min-random-wait", str(MIN_RANDOM_WAIT),
            "--max-random-wait", str(MAX_RANDOM_WAIT),
            "-s", str(PAYLOAD_SIZE),
            "-F", str(NUM_INFLIGHT),
            "--fuel", str(MAYBE_PUBLISH_FUEL),
        ]
    outfile_path = Path("/", "tmp", f"{RESULT_FILE}.{bench_cmd}.{lg_num}.{proc_num}")
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


def get_ifaddrs() -> str:
    out = subprocess.run("ip addr |grep -o '192.*/32' | sed 's#/32##g' | paste -s -d , -",
                         shell=True, capture_output=True,
                         )
    addrs = out.stdout.decode("utf-8").strip()
    return addrs


def emqttb_pubsub_fwd(hosts : str,
                      start_n : int = START_N, num_conns : int = NUM_CONNS,
                      conn_rate : int = CONN_RATE) -> subprocess.Popen:
    cwd = "/root/emqttb/"
    script = Path(f"{cwd}/emqttb")
    # in us
    conn_interval = int(1 / conn_rate * 1_000_000)
    ifaddrs = get_ifaddrs()
    args = [
        script,
        "--log-level", "info",
        # "--restapi",
        # "--pushgw",
        # "--pushgw-url", f"http://lb.int.{CLUSTER_NAME}:9091",
        # "--pushgw-interval", "10s",
        # "--conf-dump-file", "emqttb.conf",
        # "--conf", "emqttb.conf",
        # "--grafana",
        # "--grafana-url", f"http://lb.int.{CLUSTER_NAME}:3000",
        # "--grafana-login", "admin",
        "@g",
        "--lowmem",
        "-h", hosts,
        "--ifaddr", ifaddrs,
        "@pubsub_fwd",
        "--num-clients", str(num_conns),
        "--conninterval", f"{conn_interval}us",
        "--pubinterval", f"{PUB_INTERVAL_MS}ms",
        "--sub-qos", str(SUB_QoS),
        "--pub-qos", str(PUB_QoS),
        "--start-n", str(start_n),
    ]
    outfile_path = Path("/", "tmp", f"{RESULT_FILE}.pubsub_fwd")
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


def pub_sub_1_to_1_emqttb(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    targets = host_targets(host_shift=0)
    num_targets = len(targets)
    conn_rate = CONN_RATE
    num_conns = NUM_CONNS
    params = params_for_lg(TOTAL_NUM_LG, num_targets, num_conns, conn_rate, NUM_PROCS)
    log("spawning...")
    procs = [
        emqttb_pubsub_fwd(
            # start_n for this process
            start_n = start_n,
            num_conns = params["num_conns"],
            hosts = targets,
            conn_rate = params["conn_rate"],
        )
        for start_n in params["start_nums"][LG_NUM]
    ]
    pid_list += procs
    log(f"spawned: {procs}")
    return pid_list


def pub_sub_1_to_1(pid_list : List[subprocess.Popen],
                   host_shift : int = 0,
                   is_wildcard : bool = True,
                   subs_first : bool = True) -> List[subprocess.Popen]:
    # host_shift is for forcing forwarding between nodes.  If set to a
    # multiple of the number of nodes, i.e., `host_shift %
    # len(REPLICANTS) == 0`, then publishing is local to each node.

    # total connections = pubs + subs
    num_conns = NUM_CONNS // 2

    sub_targets = host_targets(host_shift=0)
    num_targets = len(sub_targets)
    pub_targets = host_targets(host_shift=host_shift)

    conn_rate = CONN_RATE
    pub_topic = "bench/%i/test"
    if is_wildcard:
        sub_topic = "bench/%i/#"
    else:
        sub_topic = pub_topic
    params = params_for_lg(TOTAL_NUM_LG, num_targets, num_conns, conn_rate, NUM_PROCS)

    def spawn_subs():
        log("spawning subscribers...")
        sub_procs = [
            spawn_bench(LG_NUM, proc_n, "sub", topic = sub_topic, qos = SUB_QoS,
                        # start_n for this process
                        start_n = start_n,
                        num_conns = params["num_conns"], hosts = sub_targets,
                        conn_rate = params["conn_rate"],
                        )
            for (proc_n, start_n) in enumerate(params["start_nums"][LG_NUM])
        ]
        log(f"subscribers spawned: {sub_procs}")
        return sub_procs

    def spawn_pubs():
        log("spawning publishers...")
        # shifting only the pubs
        pub_procs = [
            spawn_bench(LG_NUM, proc_n, "pub", topic = pub_topic, qos = PUB_QoS,
                        # start_n for this process
                        start_n = start_n,
                        num_conns = params["num_conns"], hosts = pub_targets,
                        conn_rate = params["conn_rate"],
                        )
            for (proc_n, start_n) in enumerate(params["start_nums"][LG_NUM])
        ]
        log(f"publishers spawned: {pub_procs}")
        log("warding off oom killer...")
        for p in pub_procs:
            ward_off_oom_killer(p)
        return pub_procs

    if subs_first:
        first = spawn_subs
        second = spawn_pubs
    else:
        first = spawn_pubs
        second = spawn_subs

    procs1 = first()
    pid_list += procs1
    # estimated time for the subscriptions to complete
    if conn_rate != 0:
        time_to_stabilize_s = num_conns / conn_rate + RELAXATION_PERIOD
    else:
        time_to_stabilize_s = CONN_INTERVAL_MS * num_conns // 1_000 + RELAXATION_PERIOD
    time.sleep(time_to_stabilize_s)

    procs2 = second()
    pid_list += procs2

    return pid_list


# for faster iteration
def pub_sub_1_to_1_only_pubs(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    # host_shift is for forcing forwarding between nodes.  If set to a
    # multiple of the number of nodes, i.e., `host_shift %
    # len(REPLICANTS) == 0`, then publishing is local to each node.

    # total connections = pubs + subs
    num_conns = NUM_CONNS // 2

    targets = host_targets()
    num_targets = len(targets)
    conn_rate = CONN_RATE
    params = params_for_lg(TOTAL_NUM_LG, num_targets, num_conns, conn_rate, NUM_PROCS)

    log("spawning publishers...")
    # shifting only the pubs
    pub_procs = [
        spawn_bench(LG_NUM, proc_n, "pub", topic = "bench/%i/test", qos = PUB_QoS,
                    # start_n for this process
                    start_n = start_n,
                    num_conns = params["num_conns"], hosts = targets,
                    conn_rate = params["conn_rate"],
                    )
        for (proc_n, start_n) in enumerate(params["start_nums"][LG_NUM])
    ]
    pid_list += pub_procs
    log(f"publishers spawned: {pub_procs}")

    return pid_list


# for faster iteration
def pub_sub_1_to_1_only_subs(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    # host_shift is for forcing forwarding between nodes.  If set to a
    # multiple of the number of nodes, i.e., `host_shift %
    # len(REPLICANTS) == 0`, then publishing is local to each node.

    # total connections = pubs + subs
    num_conns = NUM_CONNS // 2

    targets = host_targets()
    num_targets = len(targets)
    conn_rate = CONN_RATE
    params = params_for_lg(TOTAL_NUM_LG, num_targets, num_conns, conn_rate, NUM_PROCS)

    log("spawning subscribers...")
    # shifting only the subs
    sub_procs = [
        spawn_bench(LG_NUM, proc_n, "sub", topic = "bench/%i/test", qos = SUB_QoS,
                    # start_n for this process
                    start_n = start_n,
                    num_conns = params["num_conns"], hosts = targets,
                    conn_rate = params["conn_rate"],
                    )
        for (proc_n, start_n) in enumerate(params["start_nums"][LG_NUM])
    ]
    pid_list += sub_procs
    log(f"subscribers spawned: {sub_procs}")

    return pid_list


def pub_sub_1_to_1_fwd(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    return pub_sub_1_to_1(pid_list, host_shift=1)


def pub_sub_1_to_1_fwd_no_wildcard(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    return pub_sub_1_to_1(pid_list, is_wildcard=False, host_shift=1)


def pub_sub_1_to_1_fwd_no_wildcard_pubs_first(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    return pub_sub_1_to_1(pid_list, is_wildcard=False, host_shift=1,
                          subs_first=False)


def sub_single_wildcard(pid_list : List[subprocess.Popen]) -> List[subprocess.Popen]:
    # this assumes that the bench version being used supports the
    # `--connrate` option and a comma-separated list of hosts in `-h`.

    total_num_conns = NUM_CONNS
    conn_rate = CONN_RATE

    log("spawning subscribers...")
    targets = host_targets()
    num_targets = len(targets)
    params = params_for_lg(TOTAL_NUM_LG, num_targets, total_num_conns, conn_rate, NUM_PROCS)
    sub_procs = [
        spawn_bench(LG_NUM, proc_n, "sub", topic = "bench/test/#", qos = SUB_QoS,
                    # start_n for this process
                    start_n = start_n,
                    num_conns = params["num_conns"], hosts = targets,
                    conn_rate = params["conn_rate"],
                    )
        for (proc_n, start_n) in enumerate(params["start_nums"][LG_NUM])
    ]
    pid_list += sub_procs
    log(f"spawned subscribers: {pid_list}")
    return pid_list


def single_topic_bucket(action : BenchCmd,
                        pid_list : List[subprocess.Popen],
                        num_buckets : int = NUM_BUCKETS) -> List[subprocess.Popen]:
    # this assumes that the bench version being used supports the
    # `--connrate` option and a comma-separated list of hosts in `-h`.

    total_num_conns = NUM_CONNS
    num_conns_per_bucket = total_num_conns // num_buckets
    conn_rate_per_bucket = CONN_RATE // num_buckets

    if action == "sub":
        things = "subscribers"
        qos = SUB_QoS
    elif action == "pub":
        things = "publishers"
        qos = PUB_QoS
    else:
        raise RuntimeError("bad action")

    log(f"spawning {things} for {num_buckets} buckets...")
    targets = host_targets()
    num_targets = len(targets)
    params = params_for_lg(TOTAL_NUM_LG, num_targets,
                           num_conns_per_bucket, conn_rate_per_bucket,
                           NUM_PROCS)
    sub_procs = [
        spawn_bench(LG_NUM, action, topic = f"bench/test/{i}",
                    qos = qos,
                    # start_n for this process
                    # FIXME: wrong for more than 1 bucket...
                    start_n = params["start_nums"][LG_NUM],
                    num_conns = params["num_conns"],
                    hosts = targets,
                    conn_rate = params["conn_rate"])
        # +1 to match erlang's 1 index convention in the benches...
        for i in range(1, num_buckets + 1)
    ]
    pid_list += sub_procs
    log(f"spawned {things}: {pid_list}")
    return pid_list


def sub_single_topic_bucket(pid_list : List[subprocess.Popen],
                            num_buckets : int = NUM_BUCKETS) -> List[subprocess.Popen]:
    return single_topic_bucket("sub", pid_list, num_buckets)


def pub_single_topic_bucket(pid_list : List[subprocess.Popen],
                            num_buckets : int = NUM_BUCKETS) -> List[subprocess.Popen]:
    return single_topic_bucket("pub", pid_list, num_buckets)


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
    elif callable(globals().get(args.script)):
        fun = globals().get(args.script)
        try_run(fun)
    else:
        print("TODO!!!")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("script", type=str)

    args = parser.parse_args()
    main(args)
