# -*- coding: utf-8 -*-
NS_TARGET = "ns-dupf"

RC_SVC_NAME = "dupf-registry-center"
RC_API_PORT = 8158
#RC_CLUSTER_API_PATH = "/api/paas/v1/cluster"
#RC_HEALTH_API_PATH = "/api/paas/v1/maintenance/rc/health"
RC_CLUSTER_API_PATH = "/api/paas/v1/maintenance/rc/cluster"
WF_NAMESPACE = "default"
DEFAULT_WAIT_SECONDS = 25
DELETE_WORKFLOW_AFTER = True

OAM_CONTAINER = "lmt-cli"
LMT_PASSWORD = "Chinatelecom@123"
LMT_TABLE = "upfGetTalkerRole"
LMT_USER = "jtckpt"
LMT_IP = "127.0.0.1"
LMT_PORT = 8153
UPC_PODNAME_HINT = "upc"

DDB_EXEC_POD = "dupf-ddb-shd-0-0"
REDIS_PORT = 17380
REDIS_AUTH = 'px!2eZ{ys[r3d5eR'
EXPECTED_MASTER_COUNT = 3

# -----------------------------------------------------------------------------
# SDB configuration
#
# The SDB (slave/master Redis instance) used by some DUPF deployments runs a
# separate Redis cluster on its own set of pods.  To discover its master and
# slave roles and to query sentinel information, the discovery routines below
# need to know the pod name prefix, the Redis port and authentication, and
# where the Sentinel processes are listening.  These defaults match the
# examples provided in the documentation; adjust them if your deployment uses
# different values.

# Prefix of pod names belonging to the SDB statefulset.  All pods whose
# metadata.name contains this substring (case‑insensitive) will be considered
# SDB pods by the discovery logic.  For example, a pod named
# "dupf-sdb-0" will match the default prefix "dupf-sdb".
SDB_POD_PREFIX = "dupf-sdb"

# Port on which the SDB Redis server exposes its control interface.  The
# discovery code connects to this port inside each SDB pod to run
# ``redis-cli info replication`` and determine the role (master or slave).
SDB_PORT = 17369

# Authentication password for connecting to the SDB Redis server via
# ``redis-cli``.  If your environment uses a different password, update this
# value accordingly.  Note that this value is only used when executing
# ``redis-cli`` inside SDB pods and is not exposed outside the cluster.
SDB_AUTH = "hB#yq72Q6}8D]S2g"

# Prefix of pod names running Redis Sentinel for the SDB cluster.  Sentinel
# pods typically follow a ``dupf-sdb-sentinel-N`` naming convention.  The
# discovery logic uses this prefix to locate sentinel pods in the target
# namespace when gathering sentinel status.
SDB_SENTINEL_POD_PREFIX = "dupf-sdb-sentinel"

# Port on which Redis Sentinel is listening inside each sentinel pod.  The
# sentinel discovery routine uses this port to run ``redis-cli info sentinel``.
SDB_SENTINEL_PORT = 26380

# 在 config.py 中添加
#UPC_LABEL_KV = "app.kubernetes.io/component: dupf-pod-upc"
#RC_LABEL_KV = "app.kubernetes.io/component: dupf-registry-center"


# HTTP timeout(seconds) and retries for querying RC cluster API
RC_HTTP_TIMEOUT = 5
RC_HTTP_RETRIES = 2
RC_HTTP_RETRY_BACKOFF_SECONDS = 0.5
