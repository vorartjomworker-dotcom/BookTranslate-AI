# BookTranslate AI Helm chart

This chart is the Stage 10 production Kubernetes target. It deploys the stateless BookTranslate API, frontend and three independent worker pools. PostgreSQL, Redis and S3-compatible object storage are external dependencies and should use managed or clustered production services.

## Required infrastructure

- Kubernetes with an Ingress controller;
- external PostgreSQL reachable from the namespace;
- external Redis reachable from the namespace;
- S3-compatible object storage;
- a TLS Secret for the public host;
- an externally managed Kubernetes Secret named by `secrets.existingSecret`;
- optional Prometheus Operator for `ServiceMonitor`;
- optional KEDA for Redis queue-depth autoscaling.

The chart never creates production credentials. See `values.yaml` for the required Secret keys.

## Install

```bash
helm lint deploy/helm/booktranslate
helm upgrade --install booktranslate deploy/helm/booktranslate \
  --namespace booktranslate --create-namespace \
  --set backend.image.tag=v0.11.0 \
  --set frontend.image.tag=v0.11.0 \
  --set ingress.host=translate.example.com \
  --set secrets.existingSecret=booktranslate-secrets \
  --atomic --wait
```

The Alembic migration runs as a `pre-install,pre-upgrade` Helm hook before application rollout.

## Queue autoscaling

KEDA is disabled by default. When enabled, the chart creates a Redis List `ScaledObject` for each worker deployment and observes BookTranslate queue keys:

```text
booktranslate:queue:translation
booktranslate:queue:vision
booktranslate:queue:figure-render
```

Configure `keda.redisAddress` as `host:port` and place the Redis password in the external Secret key named by `keda.redisPasswordSecretKey`.

## Network and availability

The chart includes:

- HPA for backend/frontend;
- optional KEDA for worker pools;
- PodDisruptionBudgets for serving pods;
- ingress-only NetworkPolicy;
- readiness/liveness probes;
- optional authenticated Prometheus `ServiceMonitor`;
- TLS Ingress routing for `/api`, `/scim`, health endpoints and the frontend.

Egress is intentionally not denied in V1 because workers need external PostgreSQL, Redis, S3, OIDC and LLM/Vision providers whose CIDRs can be deployment-specific. Restrict egress at the cluster/CNI layer once those destinations are known.

## Secrets and SCIM

When SCIM is enabled, configure `SCIM_ENABLED=true` and an independent bearer token in the external Secret. The SCIM base path is `/scim/v2`.

OIDC browser sessions use independent expiring access/refresh tokens. SCIM deactivation revokes all active sessions for the affected user.

## Deployment workflow

`.github/workflows/deploy-production.yml` is a manual workflow bound to the protected GitHub `production` environment. It expects a `KUBE_CONFIG_B64` environment secret, pulls the previously published OCI chart and performs an atomic Helm deployment. No cluster credential is stored in the repository.
