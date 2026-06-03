import os
from typing import Optional

from elasticsearch import Elasticsearch
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Elasticsearch-Log-Searcher")


def get_es_client() -> Elasticsearch:
    """Helper to lazily initialize the Elasticsearch client from environment variables."""
    es_host = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    es_user = os.getenv("ELASTICSEARCH_USER", "elastic")
    es_pass = os.getenv("ELASTICSEARCH_PASSWORD", "changeme")

    # Some environments have an ES 8.x cluster but a newer Python client that sends
    # `compatible-with=9` media-type headers by default. Allow overriding.
    es_compatible_with = os.getenv("ELASTICSEARCH_COMPATIBLE_WITH", "8").strip()
    compat_media_type = (
        f"application/vnd.elasticsearch+json; compatible-with={es_compatible_with}"
    )

    return Elasticsearch(
        es_host,
        basic_auth=(es_user, es_pass),
        verify_certs=False,  # Useful if using internal K8s cluster IPs or self-signed certs
        headers={
            "Accept": compat_media_type,
            "Content-Type": compat_media_type,
        },
    )


@mcp.tool()
def search_java_logs(
    query: str,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    max_results: int = 50,
) -> str:
    """
    Search through the centralized, indexed Java logs in Elasticsearch.
    Use this to look for specific errors, exceptions, tracking IDs, or logs from a specific pod.
    """
    es = get_es_client()

    must_clauses = [{"match_phrase": {"message": query}}]

    if namespace:
        must_clauses.append({"term": {"kubernetes.namespace.keyword": namespace}})

    if pod_name:
        must_clauses.append({"term": {"kubernetes.pod_name.keyword": pod_name}})

    search_body = {
        "query": {"bool": {"must": must_clauses}},
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": max_results,
    }

    try:
        # Targets the default logstash pattern created by your fluent-bit pipeline
        response = es.search(index="java-app-logs-*", body=search_body)
        hits = response["hits"]["hits"]

        if not hits:
            ns_label = namespace or "None"
            pod_label = pod_name or "None"
            return (
                f"No logs found matching context: '{query}' "
                f"(Namespace filter: {ns_label}, Pod filter: {pod_label})"
            )

        results = []
        for hit in hits:
            source = hit["_source"]
            p_name = source.get("kubernetes", {}).get("pod_name", "unknown-pod")
            ts = source.get("@timestamp", "unknown-time")
            level = source.get("level", "INFO").upper()
            msg = source.get("message", "")

            log_line = f"[{ts}] [{p_name}] {level:<5} | {msg}"

            # Unpack the Java stack trace field if your structured JSON logger caught one
            if "stack_trace" in source:
                log_line += f"\nStack Trace:\n{source['stack_trace']}"

            results.append(log_line)

        return "\n---\n".join(results)

    except Exception as e:
        return f"Error connecting to Elasticsearch: {str(e)}"


@mcp.tool()
def get_log_error_summary(namespace: str = "default", last_hours: int = 24) -> str:
    """
    Get a high-level summary of error counts grouped by pod name over a recent timeframe.
    Helps locate unstable pods across the cluster instantly.
    """
    es = get_es_client()

    search_body = {
        "size": 0,  # We only care about the aggregations, not individual rows
        "query": {
            "bool": {
                "must": [
                    {"term": {"level.keyword": "ERROR"}},
                    {"term": {"kubernetes.namespace.keyword": namespace}},
                ],
                "filter": [{"range": {"@timestamp": {"gte": f"now-{last_hours}h"}}}],
            }
        },
        "aggs": {
            "errors_by_pod": {
                "terms": {"field": "kubernetes.pod_name.keyword", "size": 10}
            }
        },
    }

    try:
        response = es.search(index="java-app-logs-*", body=search_body)
        buckets = response["aggregations"]["errors_by_pod"]["buckets"]

        if not buckets:
            return (
                f"Zero ERROR-level logs found in namespace '{namespace}' over the last {last_hours} hours."
            )

        headers = f"{'POD NAME':<50} {'ERROR COUNT':<12}\n"
        separator = "-" * 62 + "\n"
        lines = [headers, separator]

        for bucket in buckets:
            lines.append(f"{bucket['key']:<50} {bucket['doc_count']:<12}")

        return "".join(lines)

    except Exception as e:
        return f"Error fetching error metrics from Elasticsearch: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
