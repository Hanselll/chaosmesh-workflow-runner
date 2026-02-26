# ChaosMesh Workflow Runner v13

`chaosmesh_workflow_runner_v13` 是一套 **基于 Chaos Mesh Workflow 的高阶实验编排工具**，用于在 Kubernetes 环境中自动生成/执行混沌用例（Workflow YAML），覆盖 **网络故障（delay/loss/partition）**、**PodKill**、**ContainerKill**，并支持 **角色感知目标解析（master/leader/talker 等）**。

---

## 1. 运行方式

```bash
# 在项目根目录
python3 -m chaos_runner.runner --case chaos_runner/cases/xxx.yaml
```

常用字段：

- `wait_seconds`: runner 等待 workflow 运行的时间（秒）
- `cleanup`: 是否在等待结束后删除 workflow（true/false）

> ⚠️ 你的 `network.duration / deadline_seconds` 很长时，`wait_seconds` 必须足够大，否则 runner 会在网络故障尚未结束时清理 workflow。

---

## 2. Case 通用语法（所有 renderer 共享）

每个用例是一个 YAML 文件，推荐结构如下：

```yaml
name: <case-name>

workflow:
  name: <workflow-name>
  namespace: <workflow-namespace>   # 一般是 default

renderer: <renderer-name>           # 见下文“3. Renderers”

targets:
  - id: <target-id>
    finder: <finder-name>
    # finder=by_label 时需要额外提供 label
    # label: "key: value"

# 以下 section 是否需要，由 renderer 决定：
network: {...}
kill: {...}

wait_seconds: 60
cleanup: true
```

---

## 3. Targets 语法（finder 列表与参数）

`targets` 用于声明“逻辑目标”，runner 会在运行时解析出具体 Pod（以及 IP 等信息），并交给 renderer 生成 Workflow。

### 3.1 target 基本格式

```yaml
targets:
  - id: upc_talker
    finder: upc_talker
```

### 3.2 支持的 finder 一览（v13）

| finder | 返回类型 | 说明 | 额外字段 |
|---|---|---|---|
| `upc_talker` | dict | 解析 UPC talker Pod | 无 |
| `upc_non_talkers` | list[dict] | 解析非 talker 的 UPC pods | 无 |
| `upc_pods` | list[dict] | 解析所有 UPC pods | 无 |
| `rc_leader` | dict | 解析 RC leader | 无 |
| `rc_followers` | list[dict] | 解析 RC follower 列表 | 无 |
| `rc_pods` | list[dict] | 解析所有 RC pods | 无 |
| `rc_etcd_leader` | dict | 解析 RC 依赖的 etcd leader | 无 |
| `etcd_followers` | list[dict] | 解析 etcd follower 列表 | 无 |
| `etcd_pods` | list[dict] | 解析所有 etcd pods | 无 |
| `ddb_masters` | list[dict] | 解析 DDB（Redis Cluster）masters | 无 |
| `ddb_non_masters` | list[dict] | 解析 DDB 非 master pods | 无 |
| `sdb_master` | dict | 解析 SDB 当前 master（单主 + 多从） | 无 |
| `sdb_slaves` | list[dict] | 解析 SDB slave 列表 | 无 |
| `sdb_sentinel_info` | dict | 解析 SDB sentinel 的 `info sentinel`（包含 master_address 等） | 无 |
| `by_label` | list[dict] | 根据 label 找 pods | `label: "key: value"` |

`dict` 典型结构：`{"pod": "<pod-name>", "ip": "<pod-ip>"}`  
`list[dict]` 为上述 dict 的列表。

#### finder=by_label 示例

```yaml
- id: mq
  finder: by_label
  label: "app.kubernetes.io/component: dupf-pod-mq-proxy"
```

> 注意：`label` 必须是 `"key: value"` 形式（有冒号）。  
> 部分 renderer 的 `network.labels` 支持 `"key=value"`，但 **targets.by_label 不支持**。

---

## 4. Expand 语法（精细控制“从列表目标里选哪些 Pod”）

当某个 target 解析结果是 `list[dict]` 时（例如 `ddb_masters`、`sdb_slaves`、`by_label`），你可以用 `expand` 指定选取策略。

目前支持：

### 4.1 全选（all）

```yaml
expand: all
```

### 4.2 随机选 N 个（random）

```yaml
expand:
  mode: random
  count: 1
  # seed: 123   # 可选：便于复现
```

### 4.3 按下标选（indices）

```yaml
expand:
  mode: indices
  indices: [0, 2]
```

---

## 5. Network 通用语法（支持 delay / loss / partition）

在支持 NetworkChaos 的 renderer 中，`network` 通常具有以下字段：

```yaml
network:
  # 生效时长（两种写法都支持，deadline_seconds 优先）
  duration: 180
  # deadline_seconds: 180

  direction: both            # both / from / to（Chaos Mesh 语义）

  # action/actions（二选一）
  actions: [delay, loss]     # 或 [partition] / [delay] / [loss]
  # action: both             # 等价于 actions: [delay, loss]

  delay:
    latency: 300ms
    jitter: 10ms

  loss:
    loss: "10"
    correlation: "0"         # v13 内部字段名是 correlation（旧 case 里写 corr 也常见，但建议统一）

  selectors:
    from: <target-id>
    to: <target-id>

  # labels 可选（v13 支持不填，自动用 resolved pods 精确选择）
  labels:
    from: "key=value"        # 或 "key: value"
    to: "key=value"          # 或 "key: value"
```

---

## 6. Kill 通用语法（PodKill / ContainerKill）

不同 renderer 支持的 kill 类型不同，请看“7. Renderers 语法”。

### 6.1 kill.items 通用字段

```yaml
kill:
  items:
    - target: <target-id>
      delay: 0               # 支持 0 / "200ms" / "1s" / 1(秒) / 0.5(秒)
      expand: ...            # target 是 list 时可用
```

---

## 7. Renderers：支持的 case 类型与完整语法

v13 内置 renderer：

- `parallel_podkill`
- `network_then_parallel_podkill`
- `network_parallel_containerkill`
- `parallel_stress`（并行注入 CPU/内存压力）
- `parallel_cpu_stress`（并行注入 CPU 压力）
- `parallel_memory_stress`（并行注入内存压力）
- `podkill_then_network`（旧风格，字段不同）

下面给出每类 renderer 的**完整语法**与**典型示例**。

---

### 7.1 renderer = `parallel_podkill`

**用途**：只做 PodKill；可对多个目标并行 kill，并支持每个目标独立 delay/expand。

#### 语法

```yaml
renderer: parallel_podkill

targets: [...]   # 必填

kill:
  items:
    - target: <target-id>     # dict 或 list
      delay: 0                # 支持 0/"200ms"/"1s"/1/0.5
      expand: ...             # 当 target 解析为 list 时必填（all/random/indices）
```

#### 示例：kill talker + kill 所有 ddb masters（延迟 5s）

```yaml
name: example_parallel_podkill
workflow:
  name: wf-example-parallel-kill
  namespace: default

renderer: parallel_podkill

targets:
  - id: upc
    finder: upc_talker
  - id: ddb
    finder: ddb_masters

kill:
  items:
    - target: upc
      delay: 0
    - target: ddb
      expand: all
      delay: 5

wait_seconds: 30
cleanup: true
```

---

### 7.2 renderer = `network_then_parallel_podkill`  ✅（推荐：网络故障期间并行 PodKill）

**用途**：先注入 NetworkChaos（可 delay/loss/partition），并在网络故障生效期间并行 PodKill。  
**v13 特性**：`network.labels` **可不填**，自动使用 resolved pods 精确选择（避免“只想隔离 master 却误伤所有 sdb”）。

#### 语法

```yaml
renderer: network_then_parallel_podkill

targets: [...]    # 必填

network:
  duration: 180                   # 或 deadline_seconds
  direction: both
  actions: [delay, loss, partition]  # 可选：delay / loss / partition / 组合
  delay: {latency: 100ms, jitter: 10ms}
  loss:  {loss: "1", correlation: "0"}

  selectors:
    from: <target-id>             # 必填：引用 targets 里的 id
    to: <target-id>               # 必填

  # labels: 可选（不填则用 resolved pods）
  # labels:
  #   from: "k=v" 或 "k: v"
  #   to: "k=v" 或 "k: v"

kill:
  items:
    - target: <target-id>         # 必填
      delay: "200ms"              # 必填（允许 0）
      expand: ...                 # target 为 list 时必填（all/random/indices）
```

#### 示例 A：Sentinel ↔ 当前 SDB Master 分区 + 并行 kill master

```yaml
name: sdb-brain-split-and-kill-master
workflow:
  name: sdb-brain-split-and-kill-master
  namespace: default

renderer: network_then_parallel_podkill

targets:
  - id: sdb_master
    finder: sdb_master
  - id: sdb_sentinels
    finder: by_label
    label: "app.kubernetes.io/instance: dupf-sdb-sentinel"

network:
  duration: 500
  actions: [partition]
  direction: both
  selectors:
    from: sdb_sentinels
    to: sdb_master
  # labels 不填：自动使用 resolved pods 精确选择

kill:
  items:
    - target: sdb_master
      delay: 0

wait_seconds: 520
cleanup: true
```

#### 示例 B：delay+loss 网络退化 + 随机 kill 一个 UPC 非 talker（30s 网络故障保持）

```yaml
name: upc-net-impair-then-kill-nontalker
workflow:
  name: upc-net-impair-then-kill-nontalker
  namespace: default

renderer: network_then_parallel_podkill

targets:
  - id: upc_non_talkers
    finder: upc_non_talkers
  - id: rc
    finder: rc_leader

network:
  duration: 30
  actions: [delay, loss]
  delay: {latency: 200ms, jitter: 10ms}
  loss:  {loss: "5", correlation: "0"}
  direction: both
  selectors:
    from: upc_non_talkers
    to: rc
  # 若你想用 labels 做“整组”而非精确 pods，可填 labels

kill:
  items:
    - target: upc_non_talkers
      expand:
        mode: random
        count: 1
      delay: 1

wait_seconds: 60
cleanup: true
```

---

### 7.3 renderer = `network_parallel_containerkill` ✅（网络故障 + 并行 ContainerKill）

**用途**：网络故障（delay/loss/partition）与容器 kill（PodChaos.container-kill）并行执行；支持每个 Pod 独立 delay，并支持 `containerMap` 精确指定每个 Pod kill 哪些容器。

> 说明：该 renderer 的 `kill` 可以不写（只做网络故障），但若 `kill.items` 为空，生成的 workflow 会包含一个空的 kill-parallel（某些 Dashboard 版本可能不友好）。

#### 语法

```yaml
renderer: network_parallel_containerkill

targets: [...]    # network.selectors 引用的目标必须存在

network:
  duration: 180
  actions: [delay, loss, partition]
  direction: both
  selectors:
    from: <target-id>          # 必填
    to: <target-id>            # 必填
  # labels 可选：不填则用 resolved pods

kill:
  containerNames: [<c1>, <c2>]     # 可选：全局默认容器名
  items:
    - target: <target-id>
      delay: "200ms"
      expand: ...                 # list target 可选
      containerNames: [<c1>]      # 可选：覆盖全局默认
      containerMap:               # 可选：按 Pod 精确指定容器
        <pod-a>: [<c1>, <c2>]
        <pod-b>: [<c1>]
```

#### 示例 A：只做 Sentinel ↔ Master 分区（不写 kill）

```yaml
name: sdb-partition-sentinel-master
workflow:
  name: sdb-partition-sentinel-master
  namespace: default

renderer: network_parallel_containerkill

targets:
  - id: sdb_master
    finder: sdb_master
  - id: sdb_sentinels
    finder: by_label
    label: "app.kubernetes.io/instance: dupf-sdb-sentinel"

network:
  duration: 180
  actions: [partition]
  direction: both
  selectors:
    from: sdb_sentinels
    to: sdb_master

wait_seconds: 15
cleanup: true
```

#### 示例 B：网络退化 + 随机 kill 一个 mq 容器

```yaml
name: net-mq-containerkill
workflow:
  name: net-mq-containerkill
  namespace: default

renderer: network_parallel_containerkill

targets:
  - id: upc
    finder: upc_talker
  - id: mq
    finder: by_label
    label: "app.kubernetes.io/component: dupf-pod-mq-proxy"

network:
  duration: 30
  actions: [delay, loss]
  delay: {latency: 300ms, jitter: 10ms}
  loss:  {loss: "10", correlation: "0"}
  direction: both
  selectors:
    from: upc
    to: mq
  # labels 可不填：会用 resolved pods

kill:
  items:
    - target: mq
      expand: {mode: random, count: 1}
      delay: "200ms"
      containerNames: ["mq-proxy-main"]

wait_seconds: 60
cleanup: true
```

---

### 7.4 renderer = `parallel_stress` / `parallel_cpu_stress` / `parallel_memory_stress` ✅（按角色单独打 CPU/内存压力）

**用途**：对指定 role 解析出的 Pod 注入 StressChaos，可按 item 选择 `cpu` / `memory` / `both`，并支持每个目标独立 delay/expand。

#### 语法

```yaml
renderer: parallel_stress   # 或 parallel_cpu_stress / parallel_memory_stress

targets: [...]

stress:
  mode: cpu                 # case 默认模式；可选 cpu/memory/both
  deadline: 60s             # 单次 stress 生效时长，支持 60 / "60s"
  items:
    - target: <target-id>
      delay: 0
      expand: ...           # target 是 list 时必填
      mode: memory          # 可覆盖默认 mode
      cpu:                  # mode 包含 cpu 时生效
        workers: 1
        load: 100
      memory:               # mode 包含 memory 时生效
        workers: 1
        size: 256MB
```

#### 示例：仅对 `rc_leader` 注入 CPU 压力；对 `rc_followers` 随机 1 个注入内存压力

```yaml
name: rc-role-stress
workflow:
  name: wf-rc-role-stress
  namespace: default

renderer: parallel_stress

targets:
  - id: leader
    finder: rc_leader
  - id: followers
    finder: rc_followers

stress:
  mode: cpu
  deadline: 90s
  items:
    - target: leader
      delay: 0
      cpu:
        workers: 2
        load: 80
    - target: followers
      mode: memory
      expand:
        mode: random
        count: 1
      delay: 3s
      memory:
        workers: 1
        size: 512MB

wait_seconds: 120
cleanup: true
```

---

### 7.5 renderer = `podkill_then_network`（旧风格：先 kill 再网络）

**用途**：先并行 kill 两个目标（固定写法：kill.targets 里放两个 id），再注入网络 delay+loss。  
⚠️ 该 renderer 的 `network` 字段与其他 renderer 不一致，属于历史兼容。

#### 语法

```yaml
renderer: podkill_then_network

targets: [...]   # 需要至少包含 kill.targets 中引用的两个 target id

kill:
  targets: [<target-a>, <target-b>]   # 必须 ≥2，通常是 [upc_talker, rc_leader]

network:
  deadline_sec: 60
  direction: both
  upc_label_kv: "key: value"          # 注意这里必须是 key: value
  rc_label_kv:  "key: value"
  latency: "100ms"
  jitter: "10ms"
  loss: "1"
  corr: "0"
```

#### 示例

```yaml
name: example_podkill_then_network
workflow:
  name: upc-rc-concurrency
  namespace: default

renderer: podkill_then_network

targets:
  - id: upc_talker
    finder: upc_talker
  - id: rc_leader
    finder: rc_leader

kill:
  targets: [upc_talker, rc_leader]

network:
  deadline_sec: 60
  direction: both
  upc_label_kv: "app.kubernetes.io/component: dupf-pod-upc"
  rc_label_kv: "app.kubernetes.io/component: dupf-registry-center"
  latency: "100ms"
  jitter: "10ms"
  loss: "1"
  corr: "0"

wait_seconds: 80
cleanup: true
```

---

## 8. 选型建议（用哪个语法最合适）

- 想做 **“网络故障期间并行 kill”**：优先用 `network_then_parallel_podkill`
- 想做 **“网络故障 + container-kill”**：用 `network_parallel_containerkill`
- 只想并行 kill 一批 pods：用 `parallel_podkill`
- 老用例兼容：`podkill_then_network`（不建议新写）

---

## 9. v13 关键增强点（你最关心的）

- NetworkChaos 支持 `partition`
- `network.labels` 可不填：自动 fallback 到 resolved pods（精确到 Pod 名）
- 解决“master/slave label 相同导致误伤整组”的问题（例如只隔离 SDB master）

