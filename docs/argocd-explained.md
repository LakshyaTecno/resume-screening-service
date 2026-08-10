# ArgoCD, explained

Notes on `argocd/application.yaml`, written after actually installing real
ArgoCD on a local `kind` cluster and watching it sync this repo for real —
every cross-reference below points at something that genuinely happened,
not a hypothetical.

## Jenkins vs. ArgoCD, the one-sentence version

Jenkins sits *outside* a cluster and pushes changes in (needs cluster
credentials). ArgoCD lives *inside* the cluster it manages and reaches *out*
to pull from git — nothing external ever gets standing access to the
cluster. See the diagram from that conversation for the full comparison.

## `apiVersion` / `kind: Application`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
```
`Application` isn't a built-in Kubernetes object — ArgoCD adds it via a
CustomResourceDefinition. Proof: the very first line of the ArgoCD install
output was `customresourcedefinition.apiextensions.k8s.io/applications.argoproj.io created`.
That's what makes `kind: Application` valid at all.

## `metadata`

```yaml
metadata:
  name: resume-screening-service
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
```
This object lives in the `argocd` namespace (where ArgoCD's own pods run) —
not in `resume-screening`, where the actual app ends up. It's ArgoCD's
internal bookkeeping. `finalizers` means "run cleanup before actually
deleting this" — without it, deleting the Application would leave the
Deployments/Service it created behind, orphaned; with it, deletion cascades.

## `spec.project`

```yaml
spec:
  project: default
```
ArgoCD's own permission-boundary concept, for restricting which
repos/clusters/namespaces a team's Applications can touch. `default` is the
unrestricted catch-all.

## `spec.source` — where the desired state comes from

```yaml
  source:
    repoURL: CHANGE_ME
    targetRevision: main
    path: charts/resume-screening-service
    helm:
      valueFiles:
        - values.yaml
      parameters:
        - name: image.tag
          value: latest
```
`repoURL: CHANGE_ME` is exactly what had to be swapped for the real GitHub
URL during the hands-on run. `path` is why ArgoCD only cares about
`charts/resume-screening-service` and ignores everything else in this same
repo (`app/`, `docs/`, `infra/terraform/`). `helm.parameters` is the same
override mechanism as `--set` — the demo also needed `image.repository` and
`image.tag: local` added, since it wasn't using a real GHCR image.

**Why `image.tag: latest` is discouraged for real use**: ArgoCD only
watches *git*, not your image registry. Push a new image under the same
`latest` tag with no new commit, and Argo has no way to notice anything
changed — pin to something git-visible instead (e.g. the CI-built commit
SHA).

## `spec.destination`

```yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: resume-screening
```
`server: https://kubernetes.default.svc` means "this same cluster ArgoCD
runs in" (it could point at a different remote cluster instead — how one
ArgoCD installation manages many clusters). `namespace: resume-screening`
is the **exact namespace that caused the real Postgres DNS bug** during the
hands-on run — the app pods couldn't resolve `postgres` because the
throwaway database had been deployed into `default` instead.

## `spec.syncPolicy`

```yaml
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```
- `selfHeal: true` — the exact mechanism from the Jenkins comparison,
  as a real config value: manual cluster drift gets reverted automatically.
- `CreateNamespace=true` — why the `resume-screening` namespace appeared on
  its own during the demo, with no `kubectl create namespace` run by hand.
- `prune: true` — resources removed from the chart later get deleted from
  the cluster too, instead of left orphaned.
- `retry` — up to 5 attempts with growing delays (5s, 10s, 20s..., capped
  at 3 minutes) if a sync attempt fails transiently.

## Hands-on: what actually happened

- Installed real ArgoCD (`kubectl apply ... install.yaml`, hit and fixed a
  known `--server-side` CRD-size gotcha).
- Applied a locally-adapted copy of this Application (real `repoURL`
  pointing at `https://github.com/LakshyaTecno/resume-screening-service.git`,
  local image overrides) — not the committed file verbatim, since the
  committed one still has the `CHANGE_ME` placeholder intentionally, as a
  template for real future use.
- `kubectl -n argocd get application resume-screening-service` showed
  `SYNC STATUS: Synced` — proof ArgoCD reached out to the real GitHub repo
  and pulled it, without us ever running `helm install` or `kubectl apply`
  on the app itself.
- Hit a real namespace-scoped DNS bug (Postgres in the wrong namespace),
  diagnosed via `kubectl logs`, fixed by redeploying Postgres into the
  correct namespace.
- API pods reached `1/1 Running`; worker pods correctly crash-looped
  (missing `SQS_QUEUE_URL`, by design, no real AWS available locally).
