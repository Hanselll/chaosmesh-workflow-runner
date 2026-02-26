# -*- coding: utf-8 -*-
import random

from chaos_runner.workflow_factory.renderers import register
from chaos_runner.workflow_factory.renderers.value_resolver import resolve_duration


def _select_targets(resolved, target_id, expand_cfg):
    val = resolved.get(target_id)
    if val is None:
        raise RuntimeError("unknown target id: {}".format(target_id))

    if isinstance(val, dict):
        return [val]

    if not isinstance(val, list):
        raise RuntimeError("unsupported target type: {} for {}".format(type(val), target_id))

    if expand_cfg == "all":
        return val

    if isinstance(expand_cfg, dict):
        if "indices" in expand_cfg:
            idxs = expand_cfg.get("indices") or []
            if not idxs:
                raise RuntimeError("stress.expand.indices must be a non-empty list")
            out = []
            for i in idxs:
                if not isinstance(i, int) or i < 0 or i >= len(val):
                    raise RuntimeError("stress.expand.indices has invalid index {} (len={})".format(i, len(val)))
                out.append(val[i])
            return out

        if (expand_cfg.get("mode") or "").lower() == "random":
            count = int(expand_cfg.get("count", 1))
            if count < 1 or count > len(val):
                raise RuntimeError("stress.expand.count must be in [1, {}]".format(len(val)))
            seed = expand_cfg.get("seed")
            if seed is not None:
                random.seed(seed)
            return random.sample(val, count)

    raise RuntimeError("target {} is a list; set stress.expand to all/random/indices".format(target_id))


def _render_cpu(workflow_name, workflow_ns, target_ns, pod_names, deadline, stress_cfg):
    workers = int(stress_cfg.get("workers", 1))
    load = int(stress_cfg.get("load", 80))
    if workers < 1:
        raise RuntimeError("stress.cpu.workers must be >=1")
    if load < 1 or load > 100:
        raise RuntimeError("stress.cpu.load must be in 1..100")

    return """apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: \"{wf}\"
  namespace: \"{wfn}\"
spec:
  entry: {wf}
  templates:
    - name: {wf}
      templateType: StressChaos
      deadline: {deadline}
      stressChaos:
        mode: all
        selector:
          namespaces:
            - {ns}
          pods:
            {ns}:
{pods}
        stressors:
          cpu:
            workers: {workers}
            load: {load}
""".format(
        wf=workflow_name,
        wfn=workflow_ns,
        ns=target_ns,
        deadline=deadline,
        pods="\n".join(["              - {}".format(p) for p in pod_names]),
        workers=workers,
        load=load,
    )


def _render_memory(workflow_name, workflow_ns, target_ns, pod_names, deadline, stress_cfg):
    workers = int(stress_cfg.get("workers", 1))
    size = str(stress_cfg.get("size", "256MB"))
    if workers < 1:
        raise RuntimeError("stress.memory.workers must be >=1")

    return """apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: \"{wf}\"
  namespace: \"{wfn}\"
spec:
  entry: {wf}
  templates:
    - name: {wf}
      templateType: StressChaos
      deadline: {deadline}
      stressChaos:
        mode: all
        selector:
          namespaces:
            - {ns}
          pods:
            {ns}:
{pods}
        stressors:
          memory:
            workers: {workers}
            size: \"{size}\"
""".format(
        wf=workflow_name,
        wfn=workflow_ns,
        ns=target_ns,
        deadline=deadline,
        pods="\n".join(["              - {}".format(p) for p in pod_names]),
        workers=workers,
        size=size,
    )


def _render(case, resolved, config, mode):
    wf = case.get("workflow") or {}
    wf_name = wf.get("name") or case.get("name") or "wf"
    wf_ns = wf.get("namespace") or config.WF_NAMESPACE
    ns = config.NS_TARGET

    stress = case.get("stress") or {}
    target_id = stress.get("target")
    if not target_id:
        raise RuntimeError("stress.target is required")

    duration = resolve_duration(stress.get("duration", "30s"), field_name="stress.duration", default="30s")
    selected = _select_targets(resolved, target_id, stress.get("expand"))
    pod_names = [x.get("pod") for x in selected if isinstance(x, dict) and x.get("pod")]
    if not pod_names:
        raise RuntimeError("stress.target resolves to empty pod list")

    if mode == "cpu":
        return _render_cpu(wf_name, wf_ns, ns, pod_names, duration, stress.get("cpu") or {})
    return _render_memory(wf_name, wf_ns, ns, pod_names, duration, stress.get("memory") or {})


@register("cpu_stress_single_role")
def render_cpu_stress(case, resolved, config):
    return _render(case, resolved, config, mode="cpu")


@register("memory_stress_single_role")
def render_memory_stress(case, resolved, config):
    return _render(case, resolved, config, mode="memory")
