# FloodAI Kubernetes deployment

This deployment wraps the existing FloodAI API; it does not turn the simulated radio/RIS layer into a physical wireless system.

## Docker Desktop Kubernetes

Build the local image:

    docker build -t floodai-api:latest .

Enable Kubernetes in Docker Desktop, then apply the manifests:

    kubectl apply -f k8s/

Check the deployment:

    kubectl -n floodai get pods
    kubectl -n floodai get svc
    kubectl -n floodai get hpa

Access the API:

    kubectl -n floodai port-forward service/floodai-api 8000:8000

Then open http://localhost:8000.

Access Prometheus:

    kubectl -n floodai port-forward service/prometheus 9090:9090

Access Grafana:

    kubectl -n floodai port-forward service/grafana 3000:3000

The API exposes /metrics for Prometheus. HPA requires a metrics server. For a non-Docker-Desktop cluster, install/configure metrics-server according to the cluster's administration policy.

For production, use an image registry, TLS ingress, non-anonymous Grafana authentication, secrets management, resource tuning, and persistent monitoring storage.


## Authentication, admin, and email alerts

The API now uses a persistent SQLite database for local/single-replica deployments. Apply the namespace first, then the manifests:

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

Create the secret before relying on admin access or email delivery. Use a strong unique admin password and a Google App Password (not your normal Gmail password):

```powershell
kubectl -n floodai create secret generic floodai-auth-secrets \\
  --from-literal=FLOODAI_ADMIN_EMAIL='admin@example.com' \\
  --from-literal=FLOODAI_ADMIN_PASSWORD='REPLACE_WITH_A_LONG_UNIQUE_SECRET' \\
  --from-literal=FLOODAI_SMTP_USER='your-sender@gmail.com' \\
  --from-literal=FLOODAI_SMTP_APP_PASSWORD='YOUR_GOOGLE_APP_PASSWORD' \\
  --from-literal=FLOODAI_EMAIL_FROM='your-sender@gmail.com'
```

For an existing secret, update it with `kubectl create secret generic ... --dry-run=client -o yaml | kubectl apply -f -`. Do not commit real secrets to Git. For public production access, set the external base URL and enable secure cookies behind HTTPS/TLS.

SQLite requires a single API replica so accounts and sessions remain consistent. The HPA is intentionally capped at one replica. Before scaling the API horizontally, migrate users, sessions, audit logs, and alert deduplication to a shared PostgreSQL database and update the storage implementation.

The periodic monitor checks configured regions every five minutes by default. It sends emails only if an upstream assessment supplies a complete official alert, verified official thresholds, a fresh QC-passed gauge, an authoritative source, and a stable event ID. The current project does not yet have those verified thresholds/evidence, so an environmental indicator or simulated result cannot trigger a flood-warning email.