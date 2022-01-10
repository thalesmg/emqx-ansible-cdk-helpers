#!/usr/bin/env python

import argparse
from datetime import datetime
from fabric import Connection, ThreadingGroup
from pathlib import Path
import gzip
import shutil
import sys

# pip install fabric

# c = Connection('emqx-0.int.thalesmg',
#                user='ubuntu',
#                gateway=Connection('34.250.54.249', user='ec2-user'),
#                )

def inventory_emqx(num_emqx, bastion_ip, cluster_name):
    emqxs = [f"emqx-{i}.int.{cluster_name}" for i in range(num_emqx)]
    return ThreadingGroup(
        *emqxs,
        user='ubuntu',
        gateway=Connection(bastion_ip, user='ec2-user')
    )


def inventory_lg(num_lg, bastion_ip, cluster_name):
    lgs = [f"loadgen-{i}.int.{cluster_name}" for i in range(num_lgs)]
    return ThreadingGroup(
        *lgs,
        user='ubuntu',
        gateway=Connection(bastion_ip, user='ec2-user')
    )


def default_prefix(prefix):
    now =  datetime.today().strftime("%Y%m%d-%H%M")
    if prefix is None:
        return f"{now}"
    else:
        return f"{now}.{prefix}"


def gzip_file(inputfile):
    outfile = f"{inputfile}.gz"
    with open(inputfile, 'rb') as f_in:
        with gzip.open(outfile, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)


def get_node_dump_output_file(res) -> str:
    return [
        Path(l.removeprefix("Created a node dump "))
        for l in res.stdout.splitlines()
        if "Created a node dump" in l
    ][0]


def fetch_crashdump(c : Connection, outdir : Path, prefix : str):
    crashdump = "/var/log/emqx/erl_crash.dump"
    stat = c.run(f"sudo stat {crashdump}", warn=True, hide=True)
    if stat.exited == 0:
        c.run(f"sudo cp {crashdump} /tmp/")
        crashdump = "/tmp/erl_crash.dump"
        c.run(f"sudo chmod 0777 {crashdump}")
        outfile = f"{prefix}.{c.host}.crashdump"
        outfilepath = outdir.joinpath(outfile)
        c.get(crashdump, local=str(outfilepath))
        gzip_file(outfilepath)
        outfilepath.unlink()


def fetch_node_dump(c : Connection, outdir : Path, prefix : str):
    res = c.run("sudo /usr/lib/emqx/bin/node_dump")
    nodedump = get_node_dump_output_file(res)
    outfile = f"{prefix}.{c.host}.{nodedump.name}"
    outfilepath = outdir.joinpath(outfile)
    c.get(str(nodedump), local=str(outfilepath))


def fetch_syslog(c : Connection, outdir : Path, prefix : str):
    outfile = f"{prefix}.{c.host}.syslog"
    syslog = "/var/log/syslog"
    outfilepath = outdir.joinpath(outfile)
    c.get(syslog, local=str(outfilepath))
    gzip_file(outfilepath)
    outfilepath.unlink()


def fetch_mem_ets_dump(c : Connection, outdir : Path, prefix : str):
    dumps = [
        med
        for med in c.run("ls /tmp/", hide=True).stdout.splitlines()
        if med.endswith("_mem-ets-dump.txt")
    ]
    for dump in dumps:
        infile = f"/tmp/{dump}"
        outfile = f"{prefix}.{c.host}.{dump}"
        outfilepath = outdir.joinpath(outfile)
        c.get(infile, local=str(outfilepath))


def fetch_logs(args):
    outdir = args.outdir
    bastion_ip = args.bastion_ip
    cluster_name = args.cluster_name
    num_emqx = args.num_emqx
    prefix = args.prefix

    for c in inventory_emqx(num_emqx, bastion_ip, cluster_name):
        fetch_syslog(c, outdir, prefix)
        fetch_node_dump(c, outdir, prefix)
        fetch_crashdump(c, outdir, prefix)
        fetch_mem_ets_dump(c, outdir, prefix)


def main(argv):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    fetch_log_parser = subparsers.add_parser(
        "fetch_logs", help="fetches syslog and node_dump output from emqx"
    )

    fetch_log_parser.add_argument(
        "--num-emqx", type=int,
        required=True
    )
    fetch_log_parser.add_argument(
        "--num-lg", type=int,
        required=True
    )
    fetch_log_parser.add_argument(
        "--bastion-ip", type=str,
        required=True
    )
    fetch_log_parser.add_argument(
        "--prefix", type=str,
        required=False
    )
    fetch_log_parser.add_argument(
        "--cluster-name", type=str,
        required=True
    )
    fetch_log_parser.add_argument(
        "--outdir", type=Path,
        required=True
    )

    parsed = parser.parse_args(argv)

    if parsed.command == "fetch_logs":
        fetch_logs(parsed)


if __name__ == '__main__':
    main(sys.argv[1:])
