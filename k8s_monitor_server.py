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

if __name__ == "__main__":
    mcp.run()
