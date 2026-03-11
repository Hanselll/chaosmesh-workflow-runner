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


def find_pods_by_label_prefix(label_kv_prefix: str):
    """
    根据 `key: prefix` 形式匹配 label 值前缀，返回符合条件的 Pod 列表。

    例如 `app.kubernetes.io/component: dupf-pod-upu-` 可以匹配
    `dupf-pod-upu-1`、`dupf-pod-upu-2` ...。
    返回 [{"pod": pod_name, "ip": pod_ip}, ...] 列表。
    """
    if ":" not in label_kv_prefix:
        raise RuntimeError("label prefix must be in 'key: prefix' format")
    key, prefix = [part.strip() for part in label_kv_prefix.split(":", 1)]

    # 先按 key 过滤，避免拉取 namespace 全量 Pod。
    cmd = (
        f"kubectl -n {config.NS_TARGET} get pod -l {key} "
        f"-o jsonpath='{{range .items[*]}}{{.metadata.name}}\\t{{index .metadata.labels \"{key}\"}}\\n{{end}}'"
    )
    raw = sh(cmd)

    pods = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        pod = parts[0].strip()
        val = parts[1].strip() if len(parts) > 1 else ""
        if val.startswith(prefix):
            ip = get_pod_ip(config.NS_TARGET, pod)
            pods.append({"pod": pod, "ip": ip})
    return pods
