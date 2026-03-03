# -*- coding: utf-8 -*-
import re
from chaos_runner.tools.k8s import exec_in_pod, get_ns_pod_ip_map
from chaos_runner import config

def _cluster_nodes_raw():
    cmd = 'export REDISCLI_AUTH="{auth}"; redis-cli -p {port} cluster nodes'.format(auth=config.REDIS_AUTH, port=int(config.REDIS_PORT))
    raw = exec_in_pod(config.NS_TARGET, config.DDB_EXEC_POD, cmd)
    open("/tmp/ddb_cluster_nodes.txt","w").write(raw)
    return raw

def _parse_master_ips(raw):
    ips=[]
    for line in (raw or "").splitlines():
        parts=line.split()
        if len(parts)<3:
            continue
        addr=parts[1]; flags=parts[2]
        if "master" not in flags:
            continue
        ip=addr.split(":")[0]
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip) and ip not in ips:
            ips.append(ip)
    return ips

def find_ddb_masters():
    raw=_cluster_nodes_raw()
    ips=_parse_master_ips(raw)
    if len(ips) < int(config.EXPECTED_MASTER_COUNT):
        raise RuntimeError("masters ips too few: {} raw=/tmp/ddb_cluster_nodes.txt".format(ips))
    ip2pod=get_ns_pod_ip_map(config.NS_TARGET)
    out=[]; miss=[]
    for ip in ips[:int(config.EXPECTED_MASTER_COUNT)]:
        pod=ip2pod.get(ip)
        if not pod: miss.append(ip)
        else: out.append({"pod": pod, "ip": ip})
    if miss:
        raise RuntimeError("cannot map master ips to pods: {} raw=/tmp/ddb_cluster_nodes.txt".format(miss))
    return out

# Added function to find non‑master DDB pods
def find_ddb_non_masters():
    """
    Return a list of DDB pods that are not masters.

    This function discovers all DDB pods running in the target namespace and
    filters out any pods that are currently acting as masters. The return
    format matches ``find_ddb_masters`` by producing a list of dicts with
    ``pod`` and ``ip`` keys.

    Since Redis cluster roles are determined via the ``cluster nodes``
    command, we first reuse ``find_ddb_masters`` to build a set of master pod
    names. We then retrieve all pod IP mappings from Kubernetes and select
    pods whose name contains ``dupf-ddb`` but are not in the master set.
    """
    # Get current masters so they can be excluded
    masters = find_ddb_masters()
    master_pods = {m["pod"] for m in masters}

    # Build a reverse map pod->ip from the namespace
    ip_map = get_ns_pod_ip_map(config.NS_TARGET)
    pod_to_ip = {pod: ip for ip, pod in ip_map.items()}

    # Determine all DDB pods by name pattern. The convention is that DDB pods
    # include "dupf-ddb" in their name (e.g. ``dupf-ddb-shd-0-0``). If this
    # convention changes, update the substring accordingly.
    ddb_pods = [pod for pod in pod_to_ip if "dupf-ddb" in pod]

    # Filter out masters and build the result list
    out = []
    for pod in ddb_pods:
        if pod in master_pods:
            continue
        ip = pod_to_ip.get(pod, "")
        out.append({"pod": pod, "ip": ip})
    return out
