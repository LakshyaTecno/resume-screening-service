# Helm chart, explained file by file

Notes from walking through `charts/resume-screening-service/` one file at a
time. Written for someone new to Docker/Kubernetes/Helm — plain language
first, YAML second.

## Folder map

```
charts/resume-screening-service/
├── Chart.yaml              <- chart metadata
├── values.yaml              <- the settings
└── templates/               <- the shape, with placeholders
    ├── _helpers.tpl
    ├── configmap.yaml
    ├── secret.yaml
    ├── deployment-api.yaml
    ├── deployment-worker.yaml
    ├── service.yaml
    └── hpa.yaml
```

Helm's whole job: combine `values.yaml` (the settings) with `templates/*`
(the shape, full of `{{ }}` placeholders) into real Kubernetes YAML, then
hand that to the cluster.

```
values.yaml  ─┐
               ├─▶  helm  ─▶  real Kubernetes YAML  ─▶  cluster
templates/*  ─┘
```

- `helm template` — stops after "real Kubernetes YAML." Just prints the
  output, never touches a cluster. This is what we ran to verify the chart.
- `helm install` / `helm upgrade` — does the whole pipeline, all the way to
  the cluster, and makes the objects actually exist.

---

## `Chart.yaml` — identity card, not configuration

```yaml
apiVersion: v2
name: resume-screening-service
description: AI microservice for resume parsing, candidate-job matching, and resume ranking
type: application
version: 0.1.0
appVersion: "0.1.0"
```

Doesn't affect how the app runs at all — just tells Helm what this chart is
called and its version. Two version numbers, easy to confuse:
- `version` — the **chart's** version (bump when the Helm files themselves change)
- `appVersion` — the version of **the app** this chart currently deploys (a label only, nothing reads it automatically)

## `values.yaml` — the actual settings

The one real "knobs and dials" file. Every value here can be overridden at
install time (`--set key=value`) without touching any other file.

```yaml
image:
  repository: ghcr.io/CHANGE_ME/resume-screening-service
  tag: latest
  pullPolicy: IfNotPresent
```
Which Docker image to run. Our CI workflow pushes to GHCR — `CHANGE_ME`
would point at wherever that image actually landed.

```yaml
api:
  replicaCount: 2
worker:
  replicaCount: 2
```
"Run 2 pods" for each. `api` and `worker` are separate blocks because
they're two separate Deployments — even though both run the *same* Docker
image, just with a different startup command.

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```
`requests` = what Kubernetes reserves for scheduling ("does some node have
room?"). `limits` = the hard ceiling before Kubernetes kills/restarts the
pod. `100m` = 0.1 of a CPU core. The worker gets more memory than the API on
purpose — it's the one doing LLM parsing work.

```yaml
service:
  type: ClusterIP
  port: 80
```
`ClusterIP` = reachable inside the cluster only, not exposed to the
internet (that would be a different `type`, e.g. `LoadBalancer`).

```yaml
config:
  appName: "Resume Screening Service"
  databaseUrl: "postgresql://postgres:postgres@postgres:5432/resume_screening"
  ...
```
Every setting from `app/config.py`, restated here so it can be injected as
environment variables. Becomes the `ConfigMap` template.

```yaml
secrets:
  pineconeApiKey: ""
  awsAccessKeyId: ""
  awsSecretAccessKey: ""
```
Same idea, but for things that must never sit in plain git history. Left
blank on purpose — supplied at install time (`--set secrets.xxx=...`) or,
better, via an external-secrets operator.

**Key thing to remember**: `values.yaml` does nothing by itself. It's just
data. The `templates/` files are what actually *read* these values and turn
them into real Kubernetes YAML.

---

## `templates/_helpers.tpl` — shared snippets, not a Kubernetes object

The leading underscore is a real Helm convention: **Helm skips any file
starting with `_` when rendering output.** So this file produces nothing by
itself — it's a small library of reusable snippets other template files call
into.

```
{{- define "resume-screening-service.name" -}}
{{- .Chart.Name -}}
{{- end -}}
```
`{{- define "..." -}} ... {{- end -}}` = "define a reusable function with
this name." `.Chart.Name` is a built-in variable Helm hands to every
template — whatever `name:` was in `Chart.yaml`.

(The `-` right after `{{` is whitespace trimming, a Go template quirk — it
just keeps the rendered YAML free of stray blank lines. Doesn't change the
logic.)

```
{{- define "resume-screening-service.fullname" -}}
{{- .Release.Name -}}-{{- include "resume-screening-service.name" . -}}
{{- end -}}
```
- **`.Release.Name`** — another built-in, but not from `Chart.yaml`. It's
  whatever name *you* pick when you actually install: `helm install
  <release-name> ...`. Lets the same chart be installed multiple times
  (`staging`, `prod`, ...) without name collisions.
- **`include "name" .`** — how you *call* a defined snippet from elsewhere.
  The trailing `.` passes along everything Helm currently knows (values,
  release info, chart info) into that snippet.

So `fullname` = `<release name>-<chart name>`. This is exactly what we saw
when we ran `helm template test-release charts/resume-screening-service` —
every resource came out named like `test-release-resume-screening-service-api`.
That prefix is this function.

```
{{- define "resume-screening-service.labels" -}}
app.kubernetes.io/name: {{ include "resume-screening-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "resume-screening-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "resume-screening-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
```
Two label sets, because of a Kubernetes rule: the labels a **Service** uses
to find its Pods (its `selector`) must never change once the object exists.
The full `labels` set can safely include more descriptive, changeable info
(like chart version); `selectorLabels` stays a small, stable subset used
specifically for matching. This is the actual mechanism behind "the Service
selects the Pods" from the architecture diagram.

---

## `templates/deployment-api.yaml` — ties everything together

```yaml
apiVersion: apps/v1
kind: Deployment
```
Every Kubernetes object needs these two lines: schema version, and what
*kind* of object this is. `Deployment` = the "keeps N pods alive" object.

```yaml
metadata:
  name: {{ include "resume-screening-service.fullname" . }}-api
  labels:
    {{- include "resume-screening-service.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
```
`fullname` gives `test-release-resume-screening-service`, `-api` appends —
matches what we saw in the rendered output. New syntax: **`|`** is a pipe,
same idea as a Unix shell pipe — feed the output of `include "...labels" .`
into `nindent 4`. YAML is whitespace-sensitive, so splicing a multi-line
block into another YAML file needs exact indentation, or it breaks —
`nindent 4` = newline + indent every line 4 spaces. The extra
`app.kubernetes.io/component: api` line is what distinguishes this file from
`deployment-worker.yaml` (which carries `component: worker` instead),
despite both using the same shared `labels` helper.

```yaml
spec:
  replicas: {{ .Values.api.replicaCount }}
```
Straight from `values.yaml` → `2`. This *is* "2 pods" from the diagram.

```yaml
  selector:
    matchLabels:
      {{- include "resume-screening-service.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:
    metadata:
      labels:
        {{- include "resume-screening-service.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api
```
`selector.matchLabels` is how the Deployment knows which pods are "its"
pods — by label matching. **Gotcha worth remembering**: `template.metadata.labels`
must *exactly* match `selector.matchLabels`. `template` here is the actual
pod blueprint, stamped out `replicas` times — if the two label sets ever
drift apart, the Deployment creates pods it doesn't recognize as its own and
gets stuck in a loop.

```yaml
    spec:
      containers:
        - name: api
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
```
The payoff of Part 1 (Docker) — "go pull *this* image and run it."
`containers` is a list because a pod technically *can* run more than one,
though ours only has the one.

```yaml
          ports:
            - name: http
              containerPort: {{ .Values.api.port }}
```
`8000` — same port `uvicorn` listens on inside the Dockerfile's `CMD`.
Naming it `http` lets other fields refer to it by name instead of repeating
`8000` and risking drift.

```yaml
          envFrom:
            - configMapRef:
                name: {{ include "resume-screening-service.fullname" . }}-config
            - secretRef:
                name: {{ include "resume-screening-service.fullname" . }}-secret
```
`envFrom` dumps *every* key from that ConfigMap/Secret in as environment
variables, instead of listing them one by one. This is exactly how
`app/config.py`'s pydantic-settings (which reads env vars) gets populated in
a real cluster.

```yaml
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
```
Kubernetes automatically, repeatedly calls `GET /health` inside the running
pod — the same request we manually `curl`'d earlier and got
`{"status":"ok",...}` back. Two different questions:
- **liveness** — is this pod still working, or should Kubernetes restart it?
- **readiness** — is this pod ready for traffic *right now*? (can be alive
  but still warming up — the Service only routes to pods passing this)

```yaml
          resources:
            {{- toYaml .Values.api.resources | nindent 12 }}
```
`.Values.api.resources` is a whole nested block (`requests`/`limits`), not a
single value — `toYaml` converts the entire structure to YAML text, and
`nindent 12` slots it in at the right depth.

---

## `templates/service.yaml`

```yaml
apiVersion: v1
kind: Service
```
Notice: `v1`, not `apps/v1` like the Deployment. `Service` is a core,
foundational Kubernetes object, whereas `Deployment` belongs to the newer
`apps` API group — different object *kinds* can live in different API
groups/versions.

```yaml
metadata:
  name: {{ include "resume-screening-service.fullname" . }}
```
Notice what's missing compared to the Deployment: no `-api`/`-worker`
suffix, just plain `fullname`. Deliberate — **there's only one Service in
this whole chart**, because only the API receives incoming traffic. The
worker never gets called over the network (it pulls work from SQS itself),
so there's nothing for a Service to route to.

```yaml
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
```
Two different ports, and the gap matters:
- **`port: 80`** — what other things *inside the cluster* dial to reach this
  Service. Like a phone extension.
- **`targetPort: http`** — where the call actually gets forwarded once it
  lands. This is the payoff of naming that port `http` back in
  `deployment-api.yaml` — instead of hardcoding `8000` again, it says
  "whatever port is named `http` on the target pod." Change the app's port
  once, in one place, both files stay in sync.

```yaml
  selector:
    {{- include "resume-screening-service.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: api
```
The "Service selects the Pods" line from the diagram, made real. Only pods
carrying `selectorLabels` **and** `component: api` receive traffic. Nothing
in the worker's YAML has to say "don't send me traffic" — it's automatically
excluded because its pods carry `component: worker` instead, and never
match this selector.

---

## `templates/deployment-worker.yaml` — same shape as the API, spot the differences

Nearly a clone of `deployment-api.yaml` — same object kind, same helper
calls, same structure. What's actually different is where the meaning is:

| | `deployment-api.yaml` | `deployment-worker.yaml` |
|---|---|---|
| name suffix | `-api` | `-worker` |
| label | `component: api` | `component: worker` |
| replicas from | `.Values.api.replicaCount` | `.Values.worker.replicaCount` |
| `image:` | same line, same image | **identical line** |
| `command:` | *(none — uses image's default)* | `["python", "-m", "app.worker"]` |
| `ports:` / probes | has both | **has neither** |

Two worth sitting on:

**`command: ["python", "-m", "app.worker"]`** — the actual mechanism behind
"one image, two roles" from the Dockerfile lesson. The Dockerfile's default
`CMD` runs `uvicorn app.main:app`, but Kubernetes lets a Deployment override
that per-object, no second image needed. Same image we inspected earlier;
this file just tells it to run a different Python module —
[app/worker.py](../app/worker.py), the SQS-consuming code from the very
start of this project.

**No `ports:`, no probes** — not a missing feature, it's correct. Those
existed to let something poke `GET /health` over HTTP. The worker never
runs a web server — it just loops, polling SQS. Nothing to open a port for,
nothing to `curl`. It's also *why* `service.yaml`'s selector only matches
`component: api` — even if it accidentally matched worker pods too, there'd
be no HTTP server on the other end to receive traffic.

Everything else (`envFrom`, `resources`) works identically to the API, just
reading `.Values.worker.*` instead of `.Values.api.*`.

## `templates/configmap.yaml` and `templates/secret.yaml` — where `envFrom` actually points

Both are simple: a Kubernetes object that's fundamentally just a list of
key-value pairs.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "resume-screening-service.fullname" . }}-config
data:
  APP_NAME: {{ .Values.config.appName | quote }}
  DEBUG: {{ .Values.config.debug | quote }}
  ...
```
Name is `...-config` — exactly what `deployment-api.yaml`'s
`envFrom.configMapRef.name` points at. Every key here (`APP_NAME`,
`DATABASE_URL`, `OLLAMA_BASE_URL`, ...) is a one-to-one match with a field in
`app/config.py`, uppercased — not a coincidence, `envFrom` dumps these in as
environment variables and pydantic-settings reads env vars by that exact
convention. This ConfigMap *is* the `.env` file, just expressed as a
Kubernetes object.

New syntax: **`| quote`**. YAML guesses types a little too eagerly — without
it, a value like `false` or `2048` could get read as a boolean/number
instead of a string. Env vars are always strings regardless, so `quote`
forces every value to render as text (`"false"`, `"2048"`), no surprises.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "resume-screening-service.fullname" . }}-secret
type: Opaque
stringData:
  PINECONE_API_KEY: {{ .Values.secrets.pineconeApiKey | quote }}
  ...
```
Almost the same file — `kind: Secret` instead of `ConfigMap`, `stringData`
instead of `data`. That naming matters: a Secret's `data` field expects
values that are *already* base64-encoded; `stringData` accepts plain text
and lets Kubernetes encode it automatically on creation — avoids the chart
having to do manual encoding.

**Worth being honest about**: a Kubernetes `Secret` isn't automatically
*encrypted* — by default it just means "not shown in plain text in casual
`kubectl get`/`describe` output" plus separately-controllable access
permissions. Real encryption-at-rest needs the cluster admin to configure
that. Exactly why `values.yaml`'s comment prefers IRSA or an
external-secrets operator over a static key sitting in `stringData` for
anything production-facing.

---

## `templates/hpa.yaml` — the last file

```yaml
{{- if .Values.autoscaling.enabled }}
...
{{- end }}
```
New syntax: an **`if` conditional**. Everything between `if` and `end` only
renders when `.Values.autoscaling.enabled` is `true`. `values.yaml` defaults
this to `false`, so the file renders to nothing by default — confirmed
earlier when `helm template` showed no `HorizontalPodAutoscaler` until we
reran it with `--set autoscaling.enabled=true`.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "resume-screening-service.fullname" . }}-worker
```
Scoped specifically to the **worker**, not the API — deliberate, since the
worker's load surges with SQS queue size while the API's traffic is
comparatively steady.

```yaml
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "resume-screening-service.fullname" . }}-worker
```
A different relationship from label-matching selectors seen everywhere
else: `scaleTargetRef` points at a Deployment **by name, directly** — how
the HPA knows exactly what to scale.

```yaml
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
```
Never fewer than 2 pods, never more than 6; add/remove replicas to keep
average CPU near 70% of each pod's requested `200m`.

**Known gap, worth being able to name**: CPU is a weak proxy for "is the
queue backed up" — a worker can sit mostly CPU-idle while blocked on network
calls to Ollama/Pinecone/S3, meaning this HPA could fail to scale up exactly
when SQS is piling up. The correct signal is queue depth itself
(`ApproximateNumberOfMessagesVisible`), which needs KEDA's `aws-sqs-queue`
scaler feeding `metrics` instead of CPU. Not implemented here - a real,
nameable limitation, not an oversight.

---

## Chart complete

All 8 files covered: `Chart.yaml`, `values.yaml`, `_helpers.tpl`,
`deployment-api.yaml`, `service.yaml`, `deployment-worker.yaml`,
`configmap.yaml`, `secret.yaml`, `hpa.yaml`.

---

## Hands-on: actually installing it (kind)

Deployed this chart for real on a local `kind` cluster (Kubernetes-in-Docker
— each "node" is just another Docker container, visible in `docker ps`
alongside everything else).

```bash
kind create cluster --name resume-screening
kind load docker-image resume-screening-service:local --name resume-screening
# ...applied a throwaway Postgres Deployment+Service manually (kubectl apply,
# no Helm) so the app has something to connect to...
helm install demo charts/resume-screening-service \
  --set image.repository=resume-screening-service \
  --set image.tag=local
```

**Result**: `kubectl get pods` showed exactly what `values.yaml` asked for —
2 API pods, 2 worker pods, named `demo-resume-screening-service-{api,worker}-<hash>`
(the `fullname` helper, live).

- **API pods**: came up `1/1 Running`. Proved it for real with
  `kubectl port-forward svc/demo-resume-screening-service 18080:80` and
  `curl http://127.0.0.1:18080/health` → `200 {"status":"ok",...}`. That
  request crossed every layer from the diagrams: curl → port-forward tunnel
  → Service → Pod (selected by label) → `targetPort: http` → container port
  8000 → uvicorn → FastAPI.
- **Worker pods**: crash-looped, on purpose — first real execution of
  `app/worker.py` anywhere, and it correctly hit its own guard clause:
  `RuntimeError: SQS_QUEUE_URL is not configured`. Confirmed via
  `kubectl logs -l app.kubernetes.io/component=worker`. Not a bug — no real
  SQS queue exists to hand it, so refusing to start is the correct behavior.
- **HPA**: absent from `kubectl get hpa` by default, exactly as expected
  from `autoscaling.enabled: false` in `values.yaml`.
