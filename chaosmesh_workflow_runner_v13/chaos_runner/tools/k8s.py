# -*- coding: utf-8 -*-
import subprocess, json

def sh(cmd, check=True):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if check and p.returncode != 0:
        raise RuntimeError("Command failed: {}\nrc={}\nstdout:\n{}\nstderr:\n{}\n".format(cmd, p.returncode, out, err))
    return out

def kubectl_apply(path):
    return sh("kubectl apply -f {}".format(path))

def kubectl_delete_workflow(namespace, name):
    return sh("kubectl -n {} delete workflow {} --ignore-not-found".format(namespace, name), check=False)

def get_service_cluster_ip(namespace, svc_name):
    ip = sh("kubectl -n {} get svc {} -o jsonpath='{{.spec.clusterIP}}'".format(namespace, svc_name)).strip().strip("'").strip('"')
    if not ip or ip.lower() == "none":
        raise RuntimeError("Service {} in {} has no clusterIP".format(svc_name, namespace))
    return ip

def get_ns_pod_ip_map(namespace):
    data = json.loads(sh("kubectl -n {} get pod -o json".format(namespace)))
    m={}
    for it in data.get("items", []):
        ip = (it.get("status") or {}).get("podIP", "")
        name = (it.get("metadata") or {}).get("name", "")
        if ip and name:
            m[ip]=name
    return m

def find_pod_by_ip_allns(ip):
    data = json.loads(sh("kubectl get pod -A -o json"))
    hits=[]
    for it in data.get("items", []):
        if (it.get("status") or {}).get("podIP") == ip:
            hits.append(((it.get("metadata") or {}).get("namespace",""),
                         (it.get("metadata") or {}).get("name",""),
                         (it.get("spec") or {}).get("nodeName","")))
    return hits

def exec_in_pod(namespace, pod_name, command_sh_lc):
    return sh("kubectl exec -n {ns} {pod} -- sh -lc '{c}'".format(ns=namespace, pod=pod_name, c=command_sh_lc))

def _sh(cmd):
    out = subprocess.check_output(cmd, shell=True).decode("utf-8", errors="ignore").strip()
    return out.strip("'").strip('"')

def get_pod_ip(namespace, pod):
    return _sh("kubectl -n {} get pod {} -o jsonpath='{{.status.podIP}}'".format(namespace, pod))
