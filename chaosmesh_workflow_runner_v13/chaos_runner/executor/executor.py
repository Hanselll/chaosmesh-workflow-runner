# -*- coding: utf-8 -*-
import time
from chaos_runner.tools.k8s import kubectl_apply, kubectl_delete_workflow

def run_workflow(yaml_path, wf_namespace, wf_name, wait_seconds, cleanup=True):
    kubectl_apply(yaml_path)
    time.sleep(int(wait_seconds))
    if cleanup:
        kubectl_delete_workflow(wf_namespace, wf_name)
