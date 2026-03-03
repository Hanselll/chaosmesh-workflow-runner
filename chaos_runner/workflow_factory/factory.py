# -*- coding: utf-8 -*-
import importlib

from chaos_runner.workflow_factory.targets import resolve_targets
from chaos_runner.workflow_factory.renderers import get as get_renderer


# Best-effort preload built-in renderers; missing files won't break runner startup.
for _m in (
    "parallel_podkill",
    "podkill_then_network",
    "network_then_parallel_podkill",
    "network_parallel_containerkill",
    "pod_stress",
    "modular_chaos",
):
    try:
        importlib.import_module("chaos_runner.workflow_factory.renderers.{}".format(_m))
    except ModuleNotFoundError:
        pass


def build(case, config):
    resolved = resolve_targets(case)
    name = (case.get("renderer") or "").strip()
    if not name:
        raise RuntimeError("case.renderer is required")
    wf_yaml = get_renderer(name)(case, resolved, config)
    return wf_yaml, resolved
