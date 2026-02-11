# chaos_runner/discover/pods.py
from chaos_runner.tools.k8s import sh, get_pod_ip
from chaos_runner import config

def find_pods_by_label(label_kv: str):
    """
    根据 `key: value` 格式的 label 查询符合条件的所有 Pod。
    例如 label_kv = "app.kubernetes.io/component: dupf-pod-upu-3"
    返回 [{"pod": pod_name, "ip": pod_ip}, ...] 列表。
    """
    if ":" not in label_kv:
        raise RuntimeError("label must be in 'key: value' format")
    key, value = [part.strip() for part in label_kv.split(":", 1)]
    # 查询匹配该 label 的 Pod 名称
    raw = sh(
        f"kubectl -n {config.NS_TARGET} get pod -l {key}={value} "
        "-o jsonpath='{.items[*].metadata.name}'"
    )
    names = [n for n in raw.strip().split() if n]
    pods = []
    for pod in names:
        ip = get_pod_ip(config.NS_TARGET, pod)
        pods.append({"pod": pod, "ip": ip})
    return pods

