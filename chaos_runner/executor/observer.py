# -*- coding: utf-8 -*-
import json
from datetime import datetime, timezone

import yaml

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


def extract_podchaos_target_pods(wf_yaml_text, namespace):
    """Extract pods that are selected by PodChaos templates only."""
    doc = yaml.safe_load(wf_yaml_text) or {}
    out = set()
    templates = ((doc.get("spec") or {}).get("templates") or [])
    for tpl in templates:
        if (tpl or {}).get("templateType") != "PodChaos":
            continue
        podchaos = (tpl.get("podChaos") or {})
        pods = ((podchaos.get("selector") or {}).get("pods") or {}).get(namespace)
        if isinstance(pods, list):
            for p in pods:
                if isinstance(p, str) and p:
                    out.add(p)
    return sorted(out)


def extract_target_pods_from_resolved(resolved):
    """Extract pod names from resolved target outputs for role-state scope."""
    out = set()
    for v in (resolved or {}).values():
        if isinstance(v, dict):
            pod = v.get("pod")
            if pod:
                out.add(pod)
            continue
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("pod"):
                    out.add(it.get("pod"))
    return sorted(out)


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


def _get_all_pod_status_map(namespace):
    data = json.loads(sh("kubectl -n {} get pod -o json".format(namespace)))
    out = {}
    for it in data.get("items", []):
        name = ((it.get("metadata") or {}).get("name") or "").strip()
        if not name:
            continue
        status = ((it.get("status") or {}).get("phase") or "")
        node = ((it.get("spec") or {}).get("nodeName") or "")
        out[name] = {"status": status, "node": node}
    return out


def _component_of_pod(name):
    low = (name or "").lower()
    if "ddb" in low:
        return "ddb"
    if "etcd" in low:
        return "etcd"
    if "registry" in low or "-rc-" in low or "dupf-rc" in low:
        return "rc"
    if "upc" in low or "upu" in low:
        return "upc"
    if "sdb" in low:
        return "sdb"
    return "other"


def _find_oam_pod(namespace):
    data = json.loads(sh("kubectl -n {} get pod -o json".format(namespace)))
    for it in data.get("items", []):
        name = ((it.get("metadata") or {}).get("name") or "")
        deletion_ts = ((it.get("metadata") or {}).get("deletionTimestamp") or "")
        if "oam" in name and not deletion_ts:
            return name
    raise RuntimeError("Cannot find oam pod in {}".format(namespace))


def _collect_role_state(involved_components):
    role = {}

    if "ddb" in involved_components:
        role["ddb"] = {
            "masters": ddb_discover.find_ddb_masters(),
            "slaves": ddb_discover.find_ddb_non_masters(),
        }

    if "rc" in involved_components or "etcd" in involved_components:
        rc_cluster, rc_url = rc_discover.fetch_rc_cluster()
        role["rc_source_url"] = rc_url
        if "rc" in involved_components:
            role["rc"] = {
                "leader": rc_discover.find_rc_leader(rc_cluster),
                "followers": rc_discover.find_rc_followers(rc_cluster),
            }
        if "etcd" in involved_components:
            role["etcd"] = {
                "leader": rc_discover.find_etcd_leader(rc_cluster),
                "followers": rc_discover.find_etcd_followers(rc_cluster),
            }

    return role


def _extract_balanced_json(text):
    s = text or ""
    start = -1
    stack = []
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if start < 0:
            if ch in "[{":
                start = i
                stack = [ch]
                in_str = False
                esc = False
            continue

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch in "[{":
            stack.append(ch)
            continue
        if ch in "]}":
            if not stack:
                continue
            left = stack[-1]
            if (left == "[" and ch == "]") or (left == "{" and ch == "}"):
                stack.pop()
                if not stack:
                    return s[start : i + 1]
    return None


def _parse_lmt_output(output):
    txt = (output or "").strip()
    if not txt:
        return None

    # first pass: parse each line
    for ln in txt.splitlines():
        t = ln.strip()
        if not t:
            continue
        if t.startswith("{") or t.startswith("["):
            try:
                return json.loads(t)
            except Exception:
                pass

    # second pass: parse a balanced json block from the fragment
    blk = _extract_balanced_json(txt)
    if blk:
        try:
            return json.loads(blk)
        except Exception:
            return None
    return None


def _try_parse_json_string(val):
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s or (not s.startswith("{") and not s.startswith("[")):
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _normalize_lmt_obj(obj):
    """Recursively decode JSON-string fields for easier log reading."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            parsed = _try_parse_json_string(v)
            out[k] = _normalize_lmt_obj(parsed if parsed is not None else v)
        return out
    if isinstance(obj, list):
        return [_normalize_lmt_obj(x) for x in obj]
    return obj


def _pretty_json_lines(obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    return text.splitlines()


def _render_lmt_compact(command, parsed):
    title = command.replace("lmt-cli list", "").strip()
    if parsed is None:
        return ["{} => <parse-failed>".format(title)]

    normalized = _normalize_lmt_obj(parsed)
    lines = []

    if isinstance(normalized, dict):
        c = normalized.get("currentItemCount")
        t = normalized.get("totalItems")
        p = normalized.get("pageIndex")
        meta = []
        if c is not None:
            meta.append("currentItemCount={}".format(c))
        if t is not None:
            meta.append("totalItems={}".format(t))
        if p is not None:
            meta.append("pageIndex={}".format(p))
        lines.append("{}{}".format(title, (" => " + ", ".join(meta)) if meta else ""))

        records = normalized.get("records")
        if isinstance(records, list):
            for i, rec in enumerate(records, 1):
                lines.append("  record[{}]:".format(i))
                for ln in _pretty_json_lines(rec):
                    lines.append("    {}".format(ln))
            return lines

    if isinstance(normalized, list):
        lines.append("{} => count={}".format(title, len(normalized)))
        for i, item in enumerate(normalized, 1):
            lines.append("  item[{}]:".format(i))
            for ln in _pretty_json_lines(item):
                lines.append("    {}".format(ln))
        return lines

    lines.append("{}:".format(title))
    for ln in _pretty_json_lines(normalized):
        lines.append("  {}".format(ln))
    return lines


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
    ret = run_lmt_commands_in_container(
        namespace,
        oam_pod,
        config.OAM_CONTAINER,
        config.LMT_IP,
        config.LMT_PORT,
        config.LMT_USER,
        config.LMT_PASSWORD,
        commands,
    )

    rows = []
    for item in ret.get("results") or []:
        raw = item.get("output", "")
        cleaned = _clean_lmt_table_output(raw, item.get("command", ""))
        if not cleaned:
            cleaned = _fallback_lmt_text(raw)
        rows.append({"command": item.get("command"), "table_text": cleaned})

    return {"oam_pod": oam_pod, "rows": rows, "raw_output": ret.get("raw_output", "")}


def _parse_rfc3339(ts):
    t = (ts or "").strip()
    if not t:
        return None
    # Keep compatibility with Python 3.6 where datetime.fromisoformat is unavailable.
    if t.endswith("Z"):
        t = t[:-1]
    try:
        return datetime.strptime(t, "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        pass
    try:
        # e.g. 2026-03-04T17:43:20
        return datetime.strptime(t, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clean_lmt_table_output(text, command):
    out = []
    for ln in (text or "").splitlines():
        s = (ln or "").rstrip()
        if not s.strip():
            continue
        # remove echoed command / shell prompt / marker lines
        if command and s.strip() == command.strip():
            continue
        if "__CMD_BEGIN_" in s or "__CMD_END_" in s:
            continue
        if s.lstrip().startswith("root@") or s.lstrip().startswith("bash-"):
            continue
        if s.strip().lower() == "echo":
            continue
        out.append(s)
    return "\n".join(out).strip()


def _fallback_lmt_text(text):
    """Best-effort fallback to avoid empty LMT blocks in logs."""
    out = []
    for ln in (text or "").splitlines():
        s = (ln or "").strip()
        if not s:
            continue
        if "__CMD_BEGIN_" in s or "__CMD_END_" in s:
            continue
        out.append((ln or "").rstrip())
    return "\n".join(out).strip()


def _table_name(command):
    c = (command or "").strip()
    if c.startswith("lmt-cli list"):
        c = c[len("lmt-cli list") :].strip()
    c = c.replace("--format table", "").strip()
    return c


def _collect_target_events_rows(namespace, pod_names, since_time=None):
    out = sh(
        "kubectl get events -n {} -o=custom-columns="
        "LASTSEEN:.lastTimestamp,TYPE:.type,REASON:.reason,OBJECT_KIND:.involvedObject.kind,"
        "OBJECT_NAME:.involvedObject.name,MESSAGE:.message --no-headers".format(namespace),
        check=False,
    )
    pods = set(pod_names)
    rows = []
    for line in (out or "").splitlines():
        if not line.strip():
            continue
        cols = line.split(None, 5)
        if len(cols) < 6:
            continue
        last, typ, reason, kind, obj_name, msg = cols
        if kind != "Pod" or obj_name not in pods:
            continue
        if since_time:
            ts = _parse_rfc3339(last)
            if ts and ts < since_time:
                continue
        rows.append(
            {
                "LASTSEEN": last,
                "TYPE": typ,
                "REASON": reason,
                "OBJECT_KIND": kind,
                "OBJECT_NAME": obj_name,
                "MESSAGE": msg,
            }
        )
    return rows


def _log_pod_table(case_log, title, pod_status_map):
    case_log.log(title)
    case_log.log("  {:<48} {:<12} {}".format("POD", "PHASE", "NODE"))
    case_log.log("  {}".format("-" * 110))
    for pod in sorted(pod_status_map.keys()):
        row = pod_status_map[pod]
        case_log.log("  {:<48} {:<12} {}".format(pod, row.get("status", ""), row.get("node", "")))


def _log_replacements(case_log, replacements, title="[POST] Pod Replacement Mapping"):
    if not replacements:
        return
    case_log.log(title)
    for old_name in sorted(replacements.keys()):
        item = replacements[old_name]
        case_log.log(
            "  {} -> {}@{}".format(
                old_name,
                item.get("new_name", "<unknown>"),
                (item.get("row") or {}).get("node", "<unknown-node>"),
            )
        )


def _log_role_state(case_log, title, role_state):
    case_log.log(title)
    if role_state.get("ddb"):
        ddb = role_state["ddb"]
        case_log.log("  DDB masters: {}".format(", ".join(["{}({})".format(x.get("pod"), x.get("ip")) for x in ddb.get("masters", [])]) or "<none>"))
        case_log.log("  DDB slaves : {}".format(", ".join(["{}({})".format(x.get("pod"), x.get("ip")) for x in ddb.get("slaves", [])]) or "<none>"))
    if role_state.get("rc"):
        rc = role_state["rc"]
        leader = rc.get("leader") or {}
        case_log.log("  RC leader  : {}({})".format(leader.get("pod", ""), leader.get("ip", "")))
        case_log.log("  RC followers: {}".format(", ".join(["{}({})".format(x.get("pod"), x.get("ip")) for x in rc.get("followers", [])]) or "<none>"))
    if role_state.get("etcd"):
        etcd = role_state["etcd"]
        leader = etcd.get("leader") or {}
        case_log.log("  ETCD leader: {}({})".format(leader.get("pod", ""), leader.get("ip", "")))
        case_log.log("  ETCD followers: {}".format(", ".join(["{}({})".format(x.get("pod"), x.get("ip")) for x in etcd.get("followers", [])]) or "<none>"))


def _log_lmt_snapshot(case_log, lmt_state, phase):
    case_log.log("[{}] LMT Business Snapshot (oam={})".format(phase, lmt_state.get("oam_pod", "")))
    for row in (lmt_state.get("rows") or []):
        title = _table_name(row.get("command", ""))
        table = row.get("table_text", "")
        case_log.log("  [{}]".format(title))
        case_log.log("{}".format(table if table else "    <empty; raw=/tmp/lmt_raw_pty_multi.txt>"))


def collect_pre_case_state(namespace, podchaos_target_pods, role_source_pods, case_log):
    run_start = datetime.now(timezone.utc)
    if not podchaos_target_pods:
        case_log.log("[PRE] podchaos selected pods is empty")
    involved_components = sorted({_component_of_pod(p) for p in (role_source_pods or []) if _component_of_pod(p) != "other"})

    pod_status = _get_pod_status_map(namespace, podchaos_target_pods)
    role_state = _collect_role_state(involved_components)
    lmt_state = _collect_lmt(namespace)

    case_log.log("[PRE] podchaos selected pods count={} components={}".format(len(podchaos_target_pods), involved_components))
    _log_pod_table(case_log, "[PRE] Pod Status", pod_status)
    _log_role_state(case_log, "[PRE] Component Overall Role State", role_state)
    _log_lmt_snapshot(case_log, lmt_state, "PRE")

    return {
        "target_pods": podchaos_target_pods,
        "role_source_pods": role_source_pods,
        "pre_pod_status": pod_status,
        "involved_components": involved_components,
        "run_start": run_start,
        "pre_lmt_state": lmt_state,
    }


def collect_post_case_state(namespace, pre_state, case_log):
    target_pods = pre_state.get("target_pods") or []
    involved_components = pre_state.get("involved_components") or []

    pod_status = _get_pod_status_map(namespace, target_pods)
    role_state = _collect_role_state(involved_components)
    lmt_state = _collect_lmt(namespace)

    post_all_map = _get_all_pod_status_map(namespace)
    replacements = _build_replacement_map(pre_state.get("pre_pod_status") or {}, pod_status, post_all_map)
    post_display_map = dict(pod_status)
    for old_name, item in replacements.items():
        new_name = item.get("new_name")
        row = item.get("row") or {}
        if new_name and new_name not in post_display_map:
            post_display_map[new_name] = {"status": row.get("status"), "node": row.get("node")}

    _log_pod_table(case_log, "[POST] Pod Status", post_display_map)
    _log_replacements(case_log, replacements)

    case_log.log("[COMPARE] Pod PRE -> POST")
    case_log.log("  {:<48} {:<35} {:<35}".format("POD", "PRE(phase@node)", "POST(phase@node)"))
    case_log.log("  {}".format("-" * 130))
    pre_map = pre_state.get("pre_pod_status") or {}
    all_pods = sorted(set(pre_map.keys()) | set(pod_status.keys()))
    for pod in all_pods:
        pr = pre_map.get(pod) or {}
        po = pod_status.get(pod) or {}
        note = ""
        if not po and pod in replacements:
            repl = replacements[pod]
            po = {"status": (repl.get("row") or {}).get("status"), "node": (repl.get("row") or {}).get("node")}
            note = "  -> replaced_by={}".format(repl.get("new_name"))
        pre_txt = _fmt_phase_node(pr)
        post_txt = _fmt_phase_node(po)
        case_log.log("  {:<48} {:<35} {:<35}{}".format(pod, pre_txt, post_txt, note))

    _log_role_state(case_log, "[POST] Component Overall Role State", role_state)
    _log_lmt_snapshot(case_log, lmt_state, "POST")

    event_pods = set(target_pods)
    for item in replacements.values():
        if item.get("new_name"):
            event_pods.add(item.get("new_name"))
    runtime_events = _collect_target_events_rows(namespace, sorted(event_pods), since_time=pre_state.get("run_start"))
    case_log.log("[POST] Runtime Target Events")
    case_log.log("  LASTSEEN TYPE REASON OBJECT_KIND OBJECT_NAME MESSAGE")
    for r in runtime_events:
        case_log.log("  {LASTSEEN} {TYPE} {REASON} {OBJECT_KIND} {OBJECT_NAME} {MESSAGE}".format(**r))


def _fmt_phase_node(row):
    if not row:
        return "<missing>"
    phase = (row.get("status") or "<unknown-phase>").strip()
    node = (row.get("node") or "<unknown-node>").strip()
    return "{}@{}".format(phase, node)


def _stable_pod_key(name):
    p = (name or "").strip().split("-")
    # Deployment/ReplicaSet pods usually end with '-<hash>-<suffix>'
    if len(p) >= 3:
        tail1 = p[-1]
        tail2 = p[-2]
        if tail1.isalnum() and tail2.isalnum() and len(tail1) >= 4 and len(tail2) >= 6:
            return "-".join(p[:-2])
    return (name or "").strip()


def _find_replacement_pod(pre_pod, post_all_map, used_new_pods):
    key = _stable_pod_key(pre_pod)
    cands = []
    for name, row in post_all_map.items():
        if name in used_new_pods:
            continue
        if _stable_pod_key(name) != key:
            continue
        cands.append((name, row))
    if not cands:
        return None
    # Prefer running pod
    cands.sort(key=lambda x: (0 if (x[1].get("status") == "Running") else 1, x[0]))
    return cands[0]


def _build_replacement_map(pre_map, post_target_map, post_all_map):
    used_new = set()
    out = {}
    for pod in sorted(pre_map.keys()):
        if pod in post_target_map:
            continue
        repl = _find_replacement_pod(pod, post_all_map, used_new)
        if not repl:
            continue
        new_name, new_row = repl
        used_new.add(new_name)
        out[pod] = {"new_name": new_name, "row": new_row}
    return out
