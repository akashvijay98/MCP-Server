# k8s_monitor_server.py
from mcp.server.fastmcp import FastMCP
from kubernetes import client, config

# Initialize the MCP server
mcp = FastMCP("K8s-Health-Monitor")

# Load your local ~/.kube/config 
# (If running in-cluster later, switch to config.load_incluster_config())
try:
    config.load_kube_config()
except Exception as e:
    print(f"Failed to load kubeconfig: {e}")

v1 = client.CoreV1Api()

@mcp.tool()
def get_pod_health(namespace: str = "default") -> str:
    """Get the name, status phase, and restart count of all pods in a namespace."""
    try:
        pods = v1.list_namespaced_pod(namespace)
        if not pods.items:
            return f"No pods found in namespace '{namespace}'."
        
        results = []
        for p in pods.items:
            # Extract restart count safely
            restarts = 0
            if p.status.container_statuses:
                restarts = sum(c.restart_count for c in p.status.container_statuses)
                
            results.append(
                f"Pod: {p.metadata.name} | Status: {p.status.phase} | Restarts: {restarts}"
            )
            
        return "\n".join(results)
    except Exception as e:
        return f"Error connecting to Kubernetes API: {str(e)}"

# You can add more @mcp.tool() functions here (e.g., get_node_metrics, get_events)

@mcp.tool()
def get_pod_logs(pod_name: str, namespace: str = "default", tail_lines: int = 100) -> str:
    """Fetch the recent log outputs of a specific pod to debug application-level crashes."""
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name, 
            namespace=namespace, 
            tail_lines=tail_lines
        )
        return logs if logs else f"Logs for pod '{pod_name}' are empty."
    except Exception as e:
        return f"Error fetching logs for pod '{pod_name}': {str(e)}"

@mcp.tool()
def list_namespace_pods(namespace: str = "default") -> str:
    """List all pods in a given namespace with their status, readiness, IP, and node assignment."""
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        if not pods.items:
            return f"No pods found in namespace '{namespace}'."

        # Table header
        headers = f"{'NAME':<45} {'READY':<8} {'STATUS':<15} {'IP':<15} {'NODE':<20}\n"
        separator = "-" * 105 + "\n"
        lines = [headers, separator]

        for pod in pods.items:
            name = pod.metadata.name
            status = pod.status.phase or "Unknown"
            pod_ip = pod.status.pod_ip or "None"
            node_name = pod.spec.node_name or "None"

            # Calculate ready containers (e.g., 1/1, 2/2)
            total_containers = len(pod.spec.containers) if pod.spec.containers else 0
            ready_containers = 0
            if pod.status.container_statuses:
                ready_containers = sum(1 for c in pod.status.container_statuses if c.ready)
            
            ready_str = f"{ready_containers}/{total_containers}"

            # Truncate long pod names slightly to keep table formatting clean if needed
            display_name = (name[:42] + "...") if len(name) > 45 else name
            
            lines.append(f"{display_name:<45} {ready_str:<8} {status:<15} {pod_ip:<15} {node_name:<20}")

        return "".join(lines)
    except Exception as e:
        return f"Error listing pods in namespace '{namespace}': {str(e)}"

@mcp.tool()
def get_namespace_events(namespace: str = "default") -> str:
    """Retrieve recent Kubernetes event logs for the namespace to diagnose scheduling or life-cycle errors (e.g., ImagePullBackOff)."""
    try:
        events = v1.list_namespaced_event(namespace)
        if not events.items:
            return f"No events found in namespace '{namespace}'."
        
        results = []
        # Sort events by last timestamp to see recent issues first
        sorted_events = sorted(
            events.items, 
            key=lambda x: x.last_timestamp if x.last_timestamp else datetime.min, 
            reverse=True
        )
        
        for event in sorted_events[:20]:  # Limit to top 20 recent events
            results.append(
                f"[{event.type}] {event.reason} on {event.involved_object.kind}/{event.involved_object.name}: {event.message}"
            )
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching events for namespace '{namespace}': {str(e)}"

@mcp.tool()
def restart_deployment(deployment_name: str, namespace: str = "default") -> str:
    """Triggers a rolling restart of a deployment by patching its template annotation with a fresh timestamp."""
    try:
        # Emulate `kubectl rollout restart` by updating an annotation value
        now = datetime.utcnow().isoformat() + "Z"
        body = {
            'spec': {
                'template': {
                    'metadata': {
                        'annotations': {
                            'kubectl.kubernetes.io/restartedAt': now
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=body)
        return f"Successfully triggered rolling restart for deployment '{deployment_name}' in namespace '{namespace}'."
    except Exception as e:
        return f"Error restarting deployment '{deployment_name}': {str(e)}"

if __name__ == "__main__":
    mcp.run()
