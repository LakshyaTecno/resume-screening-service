# KEDA autoscaling, explained

Notes on `charts/resume-screening-service/templates/keda-scaledobject.yaml`.
**Honesty up front, same as the AWS Terraform**: this was written and
statically validated (`helm lint`, `helm template`), never applied against
a live KEDA install. Reasoning below.

## Why this wasn't verified with a real cluster, unlike Helm/ArgoCD earlier

Earlier in this project, Helm and ArgoCD both got a genuine hands-on pass —
a real `kind` cluster, a real install, watched it actually work. KEDA's
`aws-sqs-queue` scaler is different in one important way: to prove
anything meaningful, it has to actually authenticate to AWS and read a
real queue's depth. Installing KEDA's operator into a `kind` cluster would
only prove "the CRDs exist" — it can't prove "autoscaling works" without
real AWS credentials, which this environment doesn't have. That's the same
constraint the DynamoDB/Lambda/SQS Terraform already ran into, and it gets
the same honest treatment: correct, reviewed, syntax-validated — not
claimed as end-to-end proven.

## What a `ScaledObject` actually is

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
spec:
  scaleTargetRef:
    name: ...-worker
  minReplicaCount: 2
  maxReplicaCount: 6
  triggers:
    - type: aws-sqs-queue
      metadata:
        queueURL: ...
        queueLength: "5"
```

Not a Kubernetes built-in — `keda.sh/v1alpha1` is a CRD the KEDA operator
installs. Once applied, **KEDA creates and manages a real
`HorizontalPodAutoscaler` for you**, the exact same object kind
`templates/hpa.yaml` creates directly — KEDA is a layer that generates
HPAs from richer trigger types (queue depth, cron schedules, Kafka lag,
dozens of others) instead of the plain CPU/memory metrics vanilla HPA is
limited to.

**Why this can't coexist with the existing CPU-based `hpa.yaml`**: a
Kubernetes Deployment can only have one HPA targeting it at a time. Enable
both `autoscaling.enabled` (the original CPU-based HPA) and
`autoscaling.keda.enabled` together, and one of the two HPAs Kubernetes
ends up with conflicts with the other — `values.yaml` documents this
explicitly as "enable at most one."

## `identityOwner: operator` — the one deliberate choice worth explaining

```yaml
identityOwner: operator
```

KEDA's `aws-sqs-queue` scaler supports a few ways to authenticate to AWS.
`operator` means: use whatever IAM identity the KEDA operator pod itself
runs as (e.g. an IRSA role on a real EKS cluster) — not a `TriggerAuthentication`
resource holding static access keys. This is the same "prefer IRSA over
static credentials" preference already stated in `values.yaml`'s `secrets`
block for the worker itself — applied consistently here rather than
introducing a second, weaker pattern just for KEDA.

## Reusing existing values, not duplicating them

```yaml
queueURL: {{ .Values.config.sqsQueueUrl | quote }}
awsRegion: {{ .Values.config.awsRegion | quote }}
```

Both already exist in `values.yaml` — the same queue URL the worker itself
consumes from, the same region the worker's `boto3` clients use. The
`ScaledObject` reads them rather than needing its own copies, so there's
one place to update if either ever changes, not two that could drift
apart.

## What real verification would look like, for the record

1. Install KEDA's operator into a real cluster: `helm install keda
   kedacore/keda -n keda --create-namespace`
2. `helm upgrade` this chart with `--set autoscaling.keda.enabled=true`
   pointed at a real, populated SQS queue
3. `kubectl get hpa` — confirm KEDA created the underlying HPA
4. Push real messages onto the queue past `queueLength`, watch
   `kubectl get pods -w` actually add replicas

Step 3 is the boundary between what this repo can and can't currently
prove — steps 1-2 need no AWS credentials at all and would work today;
step 4 needs a real, populated SQS queue this environment doesn't have.
