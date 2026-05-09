# -*- coding: utf-8 -*-
from chaos_runner.tools.k8s import sh, find_pod_by_ip_allns
from chaos_runner.tools.pty_lmt import run_lmt_list_in_container, extract_ip
from chaos_runner import config


def _list_upc_pod_names():
    """
    Return UPC data-plane pod names (exclude upc-lb).

    Preferred strategy is label exact match:
      app.kubernetes.io/component=dupf-pod-upc

    Fallback keeps backward compatibility with name-hint based matching, while
    explicitly excluding upc-lb style pods to avoid misclassification.
    """
    raw = sh(
        "kubectl -n {} get pod -l app.kubernetes.io/component=dupf-pod-upc "
        "-o jsonpath='{{.items[*].metadata.name}}'".format(config.NS_TARGET),
        check=False,
    )
    names = [n for n in (raw or "").strip().split() if n]
    if names:
        return names

    # Fallback for legacy environments where the exact component label is not
    # present on UPC pods.
    out_raw = sh("kubectl get pod -n {} -o jsonpath='{{.items[*].metadata.name}}'".format(config.NS_TARGET))
    all_names = [n for n in (out_raw.strip() or "").split() if n]
    out = []
    for pod in all_names:
        low = pod.lower()
        if config.UPC_PODNAME_HINT.lower() not in low:
            continue
        # Avoid treating upc-lb as UPC data-plane pod.
        if "upc-lb" in low:
            continue
        out.append(pod)
    return out

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
    from chaos_runner.tools.k8s import get_pod_ip
    names = _list_upc_pod_names()
    out = []
    for pod in names:
        # skip talker
        if pod == talker_name:
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
    from chaos_runner.tools.k8s import get_pod_ip
    names = _list_upc_pod_names()
    out = []
    for pod in names:
        ip = get_pod_ip(config.NS_TARGET, pod)
        out.append({"pod": pod, "ip": ip})
    return out
