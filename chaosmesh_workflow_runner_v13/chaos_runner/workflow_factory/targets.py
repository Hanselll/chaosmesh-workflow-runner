# -*- coding: utf-8 -*-
from chaos_runner.discover.upc import find_upc_talker, find_upc_non_talkers, find_upc_pods
#from chaos_runner.discover.rc import fetch_cluster_state, find_rc_leader
#from chaos_runner.discover.rc import fetch_rc_health, find_rc_leader
import chaos_runner.discover.rc as rc_discover
from chaos_runner.discover.pods import find_pods_by_label
from chaos_runner.discover.ddb import find_ddb_masters, find_ddb_non_masters
from chaos_runner.discover.sdb import (
    find_sdb_master,
    find_sdb_slaves,
    find_sdb_sentinel_info,
)


_DEFAULT_TARGET_ALIASES_BY_FINDER = {
    # Backward-compat: many cases reference target id "etcd" in selectors.
    # If a case defines rc_etcd_leader using another id, also expose "etcd".
    "rc_etcd_leader": "etcd",
}


def _call_optional_rc_finder(func_name, cluster_state):
    finder = getattr(rc_discover, func_name, None)
    if finder is None:
        raise RuntimeError("finder {} is not supported by this chaos_runner build".format(func_name))
    return finder(cluster_state)

def resolve_targets(case):
    ctx={"rc_cluster_state": None}
    resolved={}
    for t in case.get("targets", []):
        tid=t["id"]; finder=t["finder"]
        if finder=="upc_talker":
            resolved[tid]=find_upc_talker()
        elif finder == "upc_non_talkers":
            # return list of UPC pods excluding the talker
            resolved[tid] = find_upc_non_talkers()
        elif finder == "upc_pods":
            # return all UPC pods
            resolved[tid] = find_upc_pods()
        elif finder == "rc_leader":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = rc_discover.find_rc_leader(ctx["rc_cluster_state"])
        elif finder == "rc_followers":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = _call_optional_rc_finder("find_rc_followers", ctx["rc_cluster_state"])
        elif finder == "rc_pods":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = _call_optional_rc_finder("find_rc_pods", ctx["rc_cluster_state"])
        
        elif finder == "rc_etcd_leader":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = rc_discover.find_etcd_leader(ctx["rc_cluster_state"])
        elif finder == "etcd_followers":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = _call_optional_rc_finder("find_etcd_followers", ctx["rc_cluster_state"])
        elif finder == "etcd_pods":
            if ctx.get("rc_cluster_state") is None:
                data, url = rc_discover.fetch_rc_cluster()
                ctx["rc_cluster_state"] = data
                ctx["rc_cluster_url"] = url
            resolved[tid] = _call_optional_rc_finder("find_etcd_pods", ctx["rc_cluster_state"])

        elif finder=="ddb_masters":
            resolved[tid]=find_ddb_masters()
        elif finder=="ddb_non_masters":
            resolved[tid] = find_ddb_non_masters()
        elif finder == "sdb_master":
            # Resolve the master pod of the SDB Redis cluster.  Returns a
            # single dict with ``pod`` and ``ip`` keys.
            resolved[tid] = find_sdb_master()
        elif finder == "sdb_slaves":
            # Resolve all slave pods of the SDB Redis cluster.  Returns a list
            # of dicts with ``pod`` and ``ip`` keys for each slave.
            resolved[tid] = find_sdb_slaves()
        elif finder == "sdb_sentinel_info":
            # Retrieve sentinel monitoring information for the SDB cluster.
            # The returned dict includes fields such as sentinel_masters and
            # master_address as documented in discover.sdb._parse_sentinel_info.
            resolved[tid] = find_sdb_sentinel_info()
        elif finder == "by_label":
            # 从 target 配置中读取 label 字符串，例如 "app.kubernetes.io/component: dupf-pod-upu-3"
            label_kv = t.get("label")
            if not label_kv:
                raise RuntimeError(f"finder=by_label requires 'label' field in target {tid}")
            resolved[tid] = find_pods_by_label(label_kv)
        else:
            raise RuntimeError("Unknown finder: {}".format(finder))

        alias = _DEFAULT_TARGET_ALIASES_BY_FINDER.get(finder)
        if alias and alias not in resolved:
            resolved[alias] = resolved[tid]

    return resolved
