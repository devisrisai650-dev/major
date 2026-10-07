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
