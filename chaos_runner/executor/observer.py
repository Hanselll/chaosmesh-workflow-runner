# -*- coding: utf-8 -*-
import json
from datetime import datetime

from chaos_runner import config
import chaos_runner.discover.ddb as ddb_discover
import chaos_runner.discover.rc as rc_discover
from chaos_runner.tools.k8s import sh
from chaos_runner.tools.pty_lmt import run_lmt_commands_in_container


def _ts_ms():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class CaseLogger(object):
    def __init__(self, path):
        self.path = path

    def log(self, msg):
        line = "[{}] {}".format(_ts_ms(), msg)
        print(line)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _flatten_target_pods(resolved):
    names = set()
    for v in (resolved or {}).values():
        if isinstance(v, dict):
            pod = v.get("pod")
            if pod:
                names.add(pod)
            continue
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("pod"):
                    names.add(it.get("pod"))
    return sorted(names)


def _get_pod_status_map(namespace, pod_names):
    data = json.loads(sh("kubectl -n {} get pod -o json".format(namespace)))
    out = {}
    wanted = set(pod_names)
    for it in data.get("items", []):
        name = ((it.get("metadata") or {}).get("name") or "").strip()
        if name not in wanted:
            continue
        status = ((it.get("status") or {}).get("phase") or "")
        node = ((it.get("spec") or {}).get("nodeName") or "")
        out[name] = {"status": status, "node": node}
    return out


def _find_oam_pod(namespace):
    data = json.loads(sh("kubectl -n {} get pod -o json".format(namespace)))
    for it in data.get("items", []):
        name = ((it.get("metadata") or {}).get("name") or "")
        deletion_ts = ((it.get("metadata") or {}).get("deletionTimestamp") or "")
        if "oam" in name and not deletion_ts:
            return name
    raise RuntimeError("Cannot find oam pod in {}".format(namespace))


def _collect_role_state():
    role = {}

    role["ddb"] = {"masters": ddb_discover.find_ddb_masters(), "slaves": ddb_discover.find_ddb_non_masters()}

    rc_cluster, rc_url = rc_discover.fetch_rc_cluster()
    role["rc_source_url"] = rc_url
    role["rc"] = {
        "leader": rc_discover.find_rc_leader(rc_cluster),
        "followers": rc_discover.find_rc_followers(rc_cluster),
    }
    role["etcd"] = {
        "leader": rc_discover.find_etcd_leader(rc_cluster),
        "followers": rc_discover.find_etcd_followers(rc_cluster),
    }
    return role


def _collect_lmt(namespace):
    oam_pod = _find_oam_pod(namespace)
    commands = [
        "lmt-cli list upfGetTalkerRole --format table",
        "lmt-cli list upfGetNodeAssociateInfo --format table",
        "lmt-cli list upfGetLicenseUsage --format table",
        "lmt-cli list upfGetSessionNum --format table",
        "lmt-cli list upfGetUpcSessionNum --format table",
        "lmt-cli list upfGetUpuInstanceStatus --format table",
        "lmt-cli list upfGetWholeMachineRate --format table",
        "lmt-cli list upfGetUpuForwardRate --format table",
        "lmt-cli list upfGetRoleInterfaceRate --format table",
    ]
    out = run_lmt_commands_in_container(
        namespace,
        oam_pod,
        config.OAM_CONTAINER,
        config.LMT_IP,
        config.LMT_PORT,
        config.LMT_USER,
        config.LMT_PASSWORD,
        commands,
    )
    return {"oam_pod": oam_pod, "commands": commands, "raw_output": out}


def _event_count(it):
    series = it.get("series") or {}
    if series.get("count"):
        return int(series.get("count"))
    if it.get("count"):
        return int(it.get("count"))
    return 1


def _collect_target_events(namespace, pod_names):
    data = json.loads(sh("kubectl -n {} get events -o json".format(namespace), check=False) or "{}")
    out = []
    pods = set(pod_names)
    for it in data.get("items", []):
        inv = it.get("involvedObject") or {}
        if inv.get("kind") != "Pod":
            continue
        if inv.get("name") not in pods:
            continue
        out.append(it)
    return out


def _build_event_snapshot(events):
    snap = {}
    for it in events:
        uid = ((it.get("metadata") or {}).get("uid") or "")
        if not uid:
            continue
        snap[uid] = _event_count(it)
    return snap


def _diff_events(before_snapshot, after_events):
    new_items = []
    for it in after_events:
        uid = ((it.get("metadata") or {}).get("uid") or "")
        after_count = _event_count(it)
        before_count = before_snapshot.get(uid, 0)
        if after_count > before_count:
            new_items.append(it)
    return new_items


def collect_pre_case_state(namespace, resolved, case_log):
    target_pods = _flatten_target_pods(resolved)
    pod_status = _get_pod_status_map(namespace, target_pods)
    role_state = _collect_role_state()
    lmt_state = _collect_lmt(namespace)
    events = _collect_target_events(namespace, target_pods)
    event_snapshot = _build_event_snapshot(events)

    case_log.log("[PRE] target pods={}".format(target_pods))
    case_log.log("[PRE] pod status/node={}".format(json.dumps(pod_status, ensure_ascii=False)))
    case_log.log("[PRE] component roles={}".format(json.dumps(role_state, ensure_ascii=False)))
    case_log.log("[PRE] lmt oam pod={}".format(lmt_state["oam_pod"]))
    case_log.log("[PRE] lmt output:\n{}".format(lmt_state["raw_output"]))
    case_log.log("[PRE] event snapshot size={}".format(len(event_snapshot)))

    return {"target_pods": target_pods, "event_snapshot": event_snapshot}


def collect_post_case_state(namespace, pre_state, case_log):
    target_pods = pre_state.get("target_pods") or []
    pod_status = _get_pod_status_map(namespace, target_pods)
    role_state = _collect_role_state()
    lmt_state = _collect_lmt(namespace)

    after_events = _collect_target_events(namespace, target_pods)
    runtime_new_events = _diff_events(pre_state.get("event_snapshot") or {}, after_events)

    case_log.log("[POST] pod status/node={}".format(json.dumps(pod_status, ensure_ascii=False)))
    case_log.log("[POST] component roles={}".format(json.dumps(role_state, ensure_ascii=False)))
    case_log.log("[POST] lmt oam pod={}".format(lmt_state["oam_pod"]))
    case_log.log("[POST] lmt output:\n{}".format(lmt_state["raw_output"]))
    case_log.log("[POST] runtime events count={}".format(len(runtime_new_events)))
    for it in runtime_new_events:
        meta = it.get("metadata") or {}
        inv = it.get("involvedObject") or {}
        ts = it.get("eventTime") or it.get("lastTimestamp") or it.get("firstTimestamp") or meta.get("creationTimestamp")
        case_log.log(
            "[POST][EVENT] time={} pod={} type={} reason={} message={} count={}".format(
                ts,
                inv.get("name", ""),
                it.get("type", ""),
                it.get("reason", ""),
                (it.get("message", "") or "").replace("\n", " "),
                _event_count(it),
            )
        )
