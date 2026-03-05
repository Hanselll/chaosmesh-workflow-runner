#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, yaml
import os, sys
from datetime import datetime

# ---------------------------------------------------------------------------
# When this script is invoked as ``python3 chaos_runner/runner.py`` from the
# project root, Python's import mechanism does not automatically add the
# parent directory to ``sys.path``. As a result, attempts to import the
# top‑level ``chaos_runner`` package will fail with ``ModuleNotFoundError``.
# To make the package resolvable in this invocation mode, prepend the
# parent directory of this file to ``sys.path``. This ensures that
# ``chaos_runner`` can be imported regardless of how ``runner.py`` is executed.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from chaos_runner import config
from chaos_runner.workflow_factory.factory import build
from chaos_runner.executor.executor import run_workflow
from chaos_runner.executor.observer import (
    CaseLogger,
    collect_pre_case_state,
    collect_post_case_state,
    extract_podchaos_target_pods,
    extract_target_pods_from_resolved,
)
from chaos_runner.workflow_factory.postprocess import expand_network_chaos_to_component_pods
from chaos_runner.tools.k8s import sh

def write_yaml_to_tmp(wf_name, yaml_text):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = "/tmp/{}_{}.yaml".format(wf_name, ts)
    sh("cat > {} << 'EOF'\n{}\nEOF".format(path, yaml_text))
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)

    # ✅ 新增：只生成不执行
    ap.add_argument("--dry-run", action="store_true",
                    help="only generate workflow yaml (write to /tmp) and print resolved targets; do not apply")
    # ✅ 新增：可选输出到指定文件
    ap.add_argument("--out", default="",
                    help="optional: write rendered workflow yaml to this path (instead of /tmp/...)")
    args = ap.parse_args()

    case = yaml.safe_load(open(args.case, "r", encoding="utf-8"))
    wf = case.get("workflow") or {}
    wf_name = wf.get("name") or case.get("name") or "wf"
    wf_ns = wf.get("namespace") or config.WF_NAMESPACE

    wf_yaml, resolved = build(case, config)

    # NetworkChaos pod-group expansion is now opt-in to avoid overriding
    # explicitly resolved finder targets (e.g. shard-scoped DDB pods).
    if bool(case.get("network_expand_to_component_pods", False)):
        wf_yaml = expand_network_chaos_to_component_pods(wf_yaml, config.NS_TARGET)
    case_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    case_log_path = "/tmp/chaos_case_{}_{}.log".format(wf_name, case_ts)
    case_log = CaseLogger(case_log_path)
    case_log.log("case={} namespace={} begin".format(case.get("name"), wf_ns))

    # 写文件：默认 /tmp，也可 --out 指定
    if args.out:
        # 直接写本地文件（不用 sh/cat），更稳
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(wf_yaml)
        path = args.out
    else:
        path = write_yaml_to_tmp(wf_name, wf_yaml)

    print("[INFO] generated:", path)
    print("[INFO] resolved:", resolved)
    print("[INFO] case-log:", case_log_path)
    case_log.log("generated workflow yaml: {}".format(path))
    case_log.log("resolved targets: {}".format(resolved))

    podchaos_target_pods = extract_podchaos_target_pods(wf_yaml, config.NS_TARGET)
    role_source_pods = extract_target_pods_from_resolved(resolved)
    case_log.log("podchaos selected pods: {}".format(podchaos_target_pods))
    case_log.log("role-source target pods: {}".format(role_source_pods))
    pre_state = collect_pre_case_state(config.NS_TARGET, podchaos_target_pods, role_source_pods, case_log)

    # ✅ dry-run：到此结束，不 kubectl apply
    if args.dry_run:
        print("[DRY-RUN] skip run_workflow()")
        case_log.log("dry-run mode, skip workflow apply")
        return

    wait_seconds = int(case.get("wait_seconds", config.DEFAULT_WAIT_SECONDS))
    cleanup = bool(case.get("cleanup", config.DELETE_WORKFLOW_AFTER))

    try:
        run_workflow(path, wf_ns, wf_name, wait_seconds, cleanup=cleanup)
    finally:
        collect_post_case_state(config.NS_TARGET, pre_state, case_log)
        case_log.log("case finished")
    print("[DONE] case:", case.get("name"))

if __name__ == "__main__":
    main()
