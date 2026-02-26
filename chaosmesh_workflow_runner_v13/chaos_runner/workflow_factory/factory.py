# -*- coding: utf-8 -*-
from chaos_runner.workflow_factory.targets import resolve_targets
from chaos_runner.workflow_factory.renderers import get as get_renderer

# import renderers to register
from chaos_runner.workflow_factory.renderers import parallel_podkill  # noqa:F401
from chaos_runner.workflow_factory.renderers import podkill_then_network  # noqa:F401
from chaos_runner.workflow_factory.renderers import parallel_stress  # noqa:F401

def build(case, config):
    resolved = resolve_targets(case)
    name = (case.get("renderer") or "").strip()
    if not name:
        raise RuntimeError("case.renderer is required")
    wf_yaml = get_renderer(name)(case, resolved, config)
    return wf_yaml, resolved
