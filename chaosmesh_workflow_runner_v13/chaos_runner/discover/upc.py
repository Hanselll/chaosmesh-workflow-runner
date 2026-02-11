# -*- coding: utf-8 -*-
from chaos_runner.tools.k8s import sh, find_pod_by_ip_allns
from chaos_runner.tools.pty_lmt import run_lmt_list_in_container, extract_ip
from chaos_runner import config

def _find_oam_pod():
    out = sh("kubectl get pod -n {} -o wide".format(config.NS_TARGET))
    for line in out.splitlines():
        if line.startswith("NAME"):
            continue
        if "oam" in line:
            return line.split()[0]
    raise RuntimeError("Cannot find oam pod in {}".format(config.NS_TARGET))

def find_upc_talker():
    oam = _find_oam_pod()
    raw = run_lmt_list_in_container(config.NS_TARGET, oam, config.OAM_CONTAINER,
                                    config.LMT_IP, config.LMT_PORT, config.LMT_USER,
                                    config.LMT_PASSWORD, config.LMT_TABLE)
    ip = extract_ip(raw)
    if not ip:
        raise RuntimeError("No talker IP from lmt output. raw=/tmp/lmt_raw_pty.txt")
    hits = find_pod_by_ip_allns(ip)
    if not hits:
        raise RuntimeError("No pod found with PodIP={}".format(ip))
    for ns,name,node in hits:
        if ns==config.NS_TARGET and config.UPC_PODNAME_HINT.lower() in name.lower():
            return {"pod": name, "ip": ip}
    for ns,name,node in hits:
        if ns==config.NS_TARGET:
            return {"pod": name, "ip": ip}
    ns,name,node = hits[0]
    return {"pod": name, "ip": ip, "note": "matched outside ns-dupf"}

# Added function to find UPC pods excluding the talker
def find_upc_non_talkers():
    """
    Return a list of UPC pods that are not acting as the talker.

    The talker IP and pod are determined using :func:`find_upc_talker`. We then
    list all pods in the target namespace and filter those whose name
    includes the configured UPC hint (e.g. ``upc``) and does not equal the
    talker pod. Each result includes ``pod`` and ``ip``.
    """
    talker = find_upc_talker()
    talker_name = talker.get("pod")
    # Import locally to avoid circular imports at module load time
    from chaos_runner.tools.k8s import sh, get_pod_ip
    # Retrieve all pod names in the target namespace
    out_raw = sh("kubectl get pod -n {} -o jsonpath='{{.items[*].metadata.name}}'".format(config.NS_TARGET))
    names = [n for n in (out_raw.strip() or "").split() if n]
    out = []
    for pod in names:
        # skip talker and pods not matching the hint
        if pod == talker_name:
            continue
        if config.UPC_PODNAME_HINT.lower() not in pod.lower():
            continue
        ip = get_pod_ip(config.NS_TARGET, pod)
        out.append({"pod": pod, "ip": ip})
    return out

# Added function to list all UPC pods (including the talker)
def find_upc_pods():
    """
    Return a list of all UPC pods in the target namespace.

    Uses the configured UPC hint to filter pod names. Each entry contains
    ``pod`` and ``ip``.
    """
    from chaos_runner.tools.k8s import sh, get_pod_ip
    out_raw = sh("kubectl get pod -n {} -o jsonpath='{{.items[*].metadata.name}}'".format(config.NS_TARGET))
    names = [n for n in (out_raw.strip() or "").split() if n]
    out = []
    for pod in names:
        if config.UPC_PODNAME_HINT.lower() not in pod.lower():
            continue
        ip = get_pod_ip(config.NS_TARGET, pod)
        out.append({"pod": pod, "ip": ip})
    return out
