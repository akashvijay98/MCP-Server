---
name: root-cause-analysis
description: Diagnose incidents and produce evidence-driven RCAs for Kubernetes, Java service, pod crash, leader election, quorum, log correlation, and production failure scenarios. Use when asked for RCA, root cause, incident analysis, postmortem evidence, failure diagnosis, or to create or validate golden RCA datasets and LLM-as-judge RCA evaluations.
---

# Root Cause Analysis

## Incident RCA Workflow

1. Identify the target namespace and service, pod, or deployment.
   - If the namespace is missing, use `raft` when the repo or request context is RAFT; otherwise ask once.
   - If the user gives a service or deployment but not a pod, inspect pods in the namespace first.

2. Query Kubernetes MCP first.
   - Call `mcp__k8s_monitor.get_pod_health`.
   - Call `mcp__k8s_monitor.list_namespace_pods`.
   - If a pod is unhealthy, call `mcp__k8s_monitor.get_pod_logs`.
   - If lifecycle, scheduling, image, readiness, or restart issues are plausible, call `mcp__k8s_monitor.get_namespace_events`.

3. Query Elasticsearch MCP second.
   - Use pod name, deployment name, service name, exception text, request IDs, tracking IDs, or terms found in Kubernetes logs.
   - Call `mcp__elasticsearch_logs.get_log_error_summary` for the recent timeframe.
   - Call `mcp__elasticsearch_logs.search_java_logs` with targeted terms.

4. Correlate findings.
   - Establish the incident window and first abnormal signal.
   - Compare pod restarts, readiness, Kubernetes events, application log timestamps, and client symptoms.
   - Separate root cause from symptoms and recovery effects.
   - Prefer concrete evidence over speculation; state missing evidence explicitly.

5. Return RCA output with:
   - Impact
   - Timeline
   - Evidence
   - Most likely root cause
   - Contributing factors
   - Immediate mitigation
   - Longer-term fixes
   - Confidence level
   - Unknowns / next checks

## RCA System Prompt Contract

Use this system prompt when building an RCA agent or evaluation harness:

```text
You are an incident root-cause analysis agent.

Follow this workflow:
1. Identify the target namespace, service, deployment, and pod.
2. Use Kubernetes evidence first: pod health, pod status, pod logs, namespace events.
3. Use Elasticsearch evidence second: error summary and targeted Java log searches.
4. Correlate timestamps across Kubernetes events, pod restarts, readiness, app logs, and client symptoms.
5. Separate root cause from symptoms, mitigations, and recovery effects.
6. Prefer concrete evidence. Mark missing evidence explicitly.
7. Do not claim certainty beyond the evidence.

RAFT-specific rules:
- A 3-node RAFT cluster requires 2 reachable nodes for quorum.
- A single remaining node must not elect itself leader.
- Temporary write failures during leader change are symptoms, not necessarily root cause.
- Repeated elections imply quorum loss, peer reachability failure, network partition, or broken heartbeat behavior unless evidence shows otherwise.

Return only valid JSON matching the provided schema.
Do not include markdown.
Do not include prose outside JSON.
```


## Failure Context Injection Template

Inject failure context as the user message, not inside the system prompt. Use raw operational evidence only; do not include golden expected answers, judge rubrics, or hidden labels in candidate RCA prompts.

```text
RCA FAILURE CONTEXT

Incident ID:
{{incident_id}}

Scenario:
{{scenario}}

Namespace:
{{namespace}}

Target service or deployment:
{{target_service}}

Time window:
{{start_time}} to {{end_time}}

Observed symptom:
{{observed_symptom}}

Kubernetes pod health:
{{pod_health}}

Kubernetes pod inventory:
{{pod_inventory}}

Kubernetes events:
{{k8s_events}}

Relevant pod logs:
{{pod_logs}}

Elasticsearch error summary:
{{es_error_summary}}

Elasticsearch targeted logs:
{{es_logs}}

Client logs:
{{client_logs}}

Known constraints:
{{constraints}}

Candidate causes to evaluate:
{{candidate_causes}}

Required output:
Return only a JSON object matching the Typed RCA JSON Output Schema. Use null or empty arrays when evidence is unavailable. Mark unknowns explicitly instead of inventing details.
```

## Typed RCA JSON Output Schema

Use this schema for candidate RCA output when building an RCA agent or evaluation harness. Keep `additionalProperties: false` so output remains machine-checkable.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "incident_id",
    "impact",
    "timeline",
    "evidence",
    "root_cause",
    "contributing_factors",
    "immediate_mitigation",
    "longer_term_fixes",
    "confidence",
    "unknowns",
    "rejected_causes"
  ],
  "properties": {
    "incident_id": { "type": "string" },
    "impact": {
      "type": "object",
      "additionalProperties": false,
      "required": ["summary", "affected_components", "user_visible"],
      "properties": {
        "summary": { "type": "string" },
        "affected_components": {
          "type": "array",
          "items": { "type": "string" }
        },
        "user_visible": { "type": "boolean" }
      }
    },
    "timeline": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["timestamp", "event", "source"],
        "properties": {
          "timestamp": { "type": "string" },
          "event": { "type": "string" },
          "source": { "type": "string" }
        }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["source", "observation", "supports"],
        "properties": {
          "source": { "type": "string" },
          "observation": { "type": "string" },
          "supports": { "type": "string" }
        }
      }
    },
    "root_cause": {
      "type": "object",
      "additionalProperties": false,
      "required": ["summary", "category", "reasoning"],
      "properties": {
        "summary": { "type": "string" },
        "category": {
          "type": "string",
          "enum": [
            "pod_crash",
            "pod_deletion",
            "oomkill",
            "quorum_loss",
            "network_partition",
            "readiness_failure",
            "image_pull_failure",
            "log_unavailability",
            "leader_election_failure",
            "application_exception",
            "resource_exhaustion",
            "configuration_error",
            "unknown"
          ]
        },
        "reasoning": { "type": "string" }
      }
    },
    "contributing_factors": {
      "type": "array",
      "items": { "type": "string" }
    },
    "immediate_mitigation": {
      "type": "array",
      "items": { "type": "string" }
    },
    "longer_term_fixes": {
      "type": "array",
      "items": { "type": "string" }
    },
    "confidence": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "unknowns": {
      "type": "array",
      "items": { "type": "string" }
    },
    "rejected_causes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["cause", "reason_rejected"],
        "properties": {
          "cause": { "type": "string" },
          "reason_rejected": { "type": "string" }
        }
      }
    }
  }
}
```

## RAFT-Specific Checks

- A 3-node RAFT cluster requires 2 reachable nodes for quorum.
- A single remaining node must not elect itself leader.
- After leader pod deletion, the remaining quorum should elect a new leader.
- Client logs may show submit failures or redirects during leadership change, then `OK` submissions after recovery.
- Repeated elections without stable leadership suggest quorum loss, network partition, peer reachability failure, or broken heartbeat behavior.
- Treat pod deletion/restart, image pull failure, readiness failure, and leader election failure as distinct root-cause candidates until evidence resolves them.

## Golden RCA Dataset Workflow

Use this when asked to prepare a golden dataset for RCA validation.

1. Create JSONL with one incident per line. Keep raw evidence realistic and noisy.
2. Include positive and negative labels: expected root cause, required evidence, and explicitly rejected causes.
3. Include enough timestamps to judge timeline quality.
4. Include partial or ambiguous evidence cases, but label the expected confidence.
5. Keep train/eval separation: never include judge rubrics or expected answers in candidate RCA prompts.

Required JSONL shape:

```json
{
  "id": "raft-leader-pod-crash-001",
  "scenario": "Leader pod deleted during active client writes",
  "inputs": {
    "pod_health": "raw kubectl or MCP output",
    "k8s_events": "raw events",
    "node_logs": "raw node logs",
    "client_logs": "raw client logs"
  },
  "expected": {
    "root_cause": "Leader pod raft-node2 was deleted/restarted, causing temporary leadership loss until a new leader was elected.",
    "impact": "Brief write unavailability or redirects until new leader was established.",
    "evidence": ["pod deletion event", "new leader log", "client failures followed by OK submissions"],
    "not_root_cause": ["permanent quorum loss", "client DNS failure"],
    "confidence": "high"
  }
}
```

Useful RAFT scenarios:

- `raft-leader-pod-crash`
- `raft-follower-pod-crash`
- `raft-two-node-quorum-loss`
- `raft-client-targets-dead-leader`
- `raft-election-flapping`
- `raft-node-startup-peer-unreachable`
- `raft-network-partition-leader-isolated`
- `raft-log-replication-stall`
- `raft-readiness-probe-failure`

Validate dataset structure with:

```bash
python3 ~/.codex/skills/root-cause-analysis/scripts/validate_golden_dataset.py path/to/golden.jsonl
```

## LLM-as-Judge Workflow

1. Run the RCA agent on each dataset item using only `inputs` and `scenario`.
2. Save the candidate RCA separately from the golden `expected` answer.
3. Ask the judge model to compare candidate RCA to `expected` using the rubric below.
4. Require JSON-only judge output so scores are machine-checkable.
5. Fail examples when root cause is wrong, required evidence is missing, or unsupported claims are material.

Judge rubric:

```text
Score the candidate RCA against the golden RCA.

Criteria, each 0-5:
- root_cause_score: correct causal diagnosis
- evidence_score: uses required evidence and cites concrete observations
- timeline_score: orders events accurately
- symptom_vs_cause_score: separates symptoms from causes
- impact_score: assesses user/system impact correctly
- actions_score: proposes relevant mitigations and prevention
- unsupported_claims_score: avoids claims not supported by inputs

Return JSON only:
{
  "root_cause_score": number,
  "evidence_score": number,
  "timeline_score": number,
  "symptom_vs_cause_score": number,
  "impact_score": number,
  "actions_score": number,
  "unsupported_claims_score": number,
  "overall_score": number,
  "pass": boolean,
  "reason": "short explanation"
}

Pass when overall_score >= 4.0, root_cause_score >= 4, and unsupported_claims_score >= 4.
```

## Output Style

Be concise and evidence-driven. Include exact pod names, namespace, timestamps, exception names, and relevant event messages where available. Do not restart deployments, scale workloads, delete pods, or mutate cluster state unless the user explicitly asks.
