# -*- coding: utf-8 -*-
import random
import re
from chaos_runner.workflow_factory.renderers import register


def _format_duration(v, default_value):
    if v is None or v == "":
        return default_value
    if isinstance(v, (int, float)):
        return "{}s".format(v)
    s = str(v).strip()
    if re.match(r"^\d+(\.\d+)?$", s):
        return "{}s".format(s)
    if re.match(r"^\d+(\.\d+)?(ns|us|ms|s|m|h)$", s, re.IGNORECASE):
        return s
    raise RuntimeError("invalid duration value: {}".format(v))


def _is_zero_delay(delay):
    s = str(delay).strip().lower()
    if s in ("0", "0s", "0ms", "0us", "0ns", "0m", "0h"):
        return True
    m = re.match(r"^(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)$", s)
    if m:
        try:
            return float(m.group(1)) == 0.0
        except ValueError:
            return False
    return False


def _select_targets(tid, val, expand_cfg):
    if isinstance(val, dict):
        return [val]
    if not isinstance(val, list):
        raise RuntimeError("unsupported target type: {} for {}".format(type(val), tid))

    if expand_cfg is None:
        raise RuntimeError("target {} is list; please set expand (all / random+count / indices)".format(tid))
    if expand_cfg == "all":
        return val

    if isinstance(expand_cfg, dict):
        if "indices" in expand_cfg:
            idxs = expand_cfg.get("indices") or []
            if not isinstance(idxs, list) or not idxs:
                raise RuntimeError("expand.indices must be a non-empty list for target {}".format(tid))
            out = []
            for i in idxs:
                if not isinstance(i, int):
                    raise RuntimeError("expand.indices must be int list for target {}".format(tid))
                if i < 0 or i >= len(val):
                    raise RuntimeError("expand.indices {} out of range (len={}) for target {}".format(i, len(val), tid))
                out.append(val[i])
            return out

        mode = (expand_cfg.get("mode") or "").lower()
        if mode == "random":
            count = int(expand_cfg.get("count", 1))
            if count < 1:
                raise RuntimeError("expand.count must be >=1 for target {}".format(tid))
            if count > len(val):
                raise RuntimeError("expand.count={} > available {} for target {}".format(count, len(val), tid))
            seed = expand_cfg.get("seed")
            if seed is not None:
                random.seed(seed)
            return random.sample(val, count)

    raise RuntimeError("invalid expand for target {}: {}".format(tid, expand_cfg))


def _build_cpu_stressor(cpu_cfg):
    workers = int(cpu_cfg.get("workers", 1))
    load = int(cpu_cfg.get("load", 100))
    return """          cpu:
            workers: {workers}
            load: {load}""".format(workers=workers, load=load)


def _build_memory_stressor(memory_cfg):
    workers = int(memory_cfg.get("workers", 1))
    size = str(memory_cfg.get("size", "256MB"))
    return "          memory:\n            workers: {workers}\n            size: \"{size}\"".format(workers=workers, size=size)


def _build_stressors(item, fallback_mode):
    mode = (item.get("mode") or fallback_mode or "cpu").lower()
    cpu_cfg = item.get("cpu") or {}
    memory_cfg = item.get("memory") or {}

    if mode == "cpu":
        return _build_cpu_stressor(cpu_cfg)
    if mode == "memory":
        return _build_memory_stressor(memory_cfg)
    if mode in ("cpu+memory", "memory+cpu", "both"):
        return "\n".join([
            _build_cpu_stressor(cpu_cfg),
            _build_memory_stressor(memory_cfg),
        ])
    raise RuntimeError("unsupported stress mode: {} (supported: cpu, memory, both)".format(mode))


@register("parallel_stress")
@register("parallel_cpu_stress")
@register("parallel_memory_stress")
def render(case, resolved, config):
    wf = case.get("workflow") or {}
    wf_name = wf.get("name") or case.get("name") or "wf"
    wf_ns = wf.get("namespace") or config.WF_NAMESPACE
    ns = config.NS_TARGET

    stress = case.get("stress") or {}
    default_mode = (stress.get("mode") or "").strip().lower()
    if not default_mode:
        if case.get("renderer") == "parallel_cpu_stress":
            default_mode = "cpu"
        elif case.get("renderer") == "parallel_memory_stress":
            default_mode = "memory"
        else:
            default_mode = "cpu"

    stress_deadline = _format_duration(stress.get("deadline", stress.get("deadline_seconds", 60)), "60s")

    items = stress.get("items") or []
    if not items:
        raise RuntimeError("stress.items is empty")

    plan = []
    for it in items:
        tid = it.get("target")
        if not tid:
            raise RuntimeError("stress.items[].target is required")
        target_val = resolved.get(tid)
        if target_val is None:
            raise RuntimeError("unknown target id: {}".format(tid))
        pods = _select_targets(tid, target_val, it.get("expand"))
        delay = _format_duration(it.get("delay", 0), "0s")
        stressors = _build_stressors(it, default_mode)

        for p in pods:
            pod_name = p.get("pod") if isinstance(p, dict) else None
            if not pod_name:
                raise RuntimeError("target {} has invalid pod item: {}".format(tid, p))
            plan.append({"pod": pod_name, "delay": delay, "stressors": stressors})

    branches = []
    templates = []

    for i, it in enumerate(plan):
        b = "branch-{}".format(i)
        branches.append(b)
        children = ["stress-{}".format(i)]
        if not _is_zero_delay(it["delay"]):
            templates.append("""
    - name: wait-{i}
      templateType: Suspend
      deadline: {delay}
""".format(i=i, delay=it["delay"]))
            children = ["wait-{}".format(i), "stress-{}".format(i)]

        templates.append("""
    - name: {b}
      templateType: Serial
      children:
        - {children}

    - name: stress-{i}
      templateType: StressChaos
      deadline: {deadline}
      stressChaos:
        mode: all
        selector:
          namespaces:
            - {ns}
          pods:
            {ns}:
              - {pod}
        stressors:
{stressors}
""".format(
            b=b,
            children="\n        - ".join(children),
            i=i,
            deadline=stress_deadline,
            ns=ns,
            pod=it["pod"],
            stressors=it["stressors"],
        ))

    return """apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: \"{wf}\"
  namespace: \"{wfn}\"
spec:
  entry: {wf}
  templates:
    - name: {wf}
      templateType: Parallel
      children:
        - {branches}

{templates}
""".format(
        wf=wf_name,
        wfn=wf_ns,
        branches="\n        - ".join(branches),
        templates="".join(templates).rstrip("\n"),
    )
