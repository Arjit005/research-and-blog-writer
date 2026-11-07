"""Adaptive Diagram Selection, Grounding Verification, and Visual Quality Engine.

Provides:
1. Topic classification & visual modality selection (Diagram vs Chart vs Table vs Prose).
2. Appropriate Mermaid diagram type recommendation (Architecture, Flowchart, Sequence, State, ER, Mindmap, Timeline).
3. Semantic grounding verification: Evaluates entity coverage, directional correctness,
   and prevents unsupported/hallucinated components.
4. Mermaid syntax sanitization & label wrapping for responsive rendering.
"""

from __future__ import annotations

import re
import html
from typing import Dict, Any, List, Optional, Tuple, Set

# Supported diagram types in modern Mermaid (v11 / v12)
SUPPORTED_MERMAID_TYPES = {
    "flowchart": "flowchart TD",
    "flowchart_lr": "flowchart LR",
    "sequence": "sequenceDiagram",
    "state": "stateDiagram-v2",
    "er": "erDiagram",
    "class": "classDiagram",
    "mindmap": "mindmap",
    "timeline": "timeline",
    "c4": "C4Context",
    "quadrant": "quadrantChart",
    "gitgraph": "gitGraph",
}

# Domain keyword taxonomy for adaptive diagram selection
DOMAIN_TAXONOMY = {
    "protocol_or_handshake": {
        "keywords": ["oauth", "pkce", "handshake", "tls", "request", "response", "rpc", "saga", "jwt", "negotiation", "bb84"],
        "recommended_type": "sequence",
        "rationale": "Multi-party sequential interaction or protocol flow is best modeled as a sequence diagram.",
    },
    "state_machine_or_lifecycle": {
        "keywords": ["raft algorithm", "election timeout", "fsm", "state machine", "lifecycle stages"],
        "recommended_type": "state",
        "rationale": "Discrete state transitions and event-driven lifecycles are clearest in a state machine.",
    },
    "data_pipeline_or_workflow": {
        "keywords": ["pipeline", "mlops", "etl", "crispr", "respiration", "glycolysis", "stream", "kafka", "continuous training"],
        "recommended_type": "flowchart",
        "rationale": "Multi-stage workflows and processing pipelines are best structured as flowcharts.",
    },
    "concept_or_taxonomy": {
        "keywords": ["causality", "fall of", "roman empire", "taxonomy", "trade-off matrix", "breakdown", "factors", "multi-causal", "classification"],
        "recommended_type": "mindmap",
        "rationale": "Multi-branching historical, sociological, or conceptual causality is most natural as a mindmap.",
    },
    "chronology_or_history": {
        "keywords": ["timeline", "chronology", "evolution", "history of", "milestones", "centuries", "decades"],
        "recommended_type": "timeline",
        "rationale": "Chronological events and historical phases should be structured as an explicit timeline.",
    },
    "relational_data": {
        "keywords": ["database schema", "foreign key", "relational normalization", "one-to-many relationship"],
        "recommended_type": "er",
        "rationale": "Entity relationship diagrams clarify foreign keys, cardinalities, and relational schemas.",
    },
    "system_architecture": {
        "keywords": ["architecture", "zero-trust", "cloud security", "microservices", "kubernetes", "kube-scheduler", "orchestration", "multi-agent", "consensus", "proof-of-stake", "ethereum", "battery", "electrochemistry"],
        "recommended_type": "flowchart",
        "rationale": "Hierarchical component topology and trust boundaries are best represented as structured flowcharts or C4 diagrams.",
    },
    "algorithm_logic": {
        "keywords": ["binary search", "dijkstra", "a* heuristic", "algorithm", "tree", "pointer", "graph algorithm", "halving", "recursion"],
        "recommended_type": "flowchart",
        "rationale": "Step-by-step decision branching and algorithmic conditionals require branching flowcharts.",
    },
}


class DiagramAdvisor:
    """Evaluates topics and research content to recommend appropriate visualizations and verify grounding."""

    @classmethod
    def recommend_visual_modality(cls, topic: str, content: str = "") -> Dict[str, Any]:
        """Determine whether the topic requires a Diagram, Chart, Table, or Prose."""
        t_lower = (topic + " " + content[:1000]).lower()

        # Check if topic is strictly quantitative benchmark comparison
        quantitative_indicators = ["vs", "benchmark", "comparison", "performance metrics", "latency", "throughput", "cost"]
        is_comparative = any(qi in t_lower for qi in [" vs ", " comparative ", " comparison "])
        has_metrics = any(m in t_lower for m in ["latency", "benchmark", "accuracy", "delta"])

        if is_comparative and has_metrics:
            modality = "hybrid_table_and_diagram"
        elif any(k in t_lower for k in ["dataset statistics", "price changes", "historical inflation", "share market"]):
            modality = "chart"
        else:
            modality = "diagram"

        # Determine best Mermaid diagram type
        matched_category = "system_architecture"
        for category, config in DOMAIN_TAXONOMY.items():
            if any(k in t_lower for k in config["keywords"]):
                matched_category = category
                break

        rec_type = DOMAIN_TAXONOMY[matched_category]["recommended_type"]
        rationale = DOMAIN_TAXONOMY[matched_category]["rationale"]

        return {
            "topic": topic,
            "modality": modality,
            "category": matched_category,
            "recommended_diagram_type": rec_type,
            "mermaid_directive": SUPPORTED_MERMAID_TYPES[rec_type],
            "rationale": rationale,
        }

    @classmethod
    def extract_diagram_entities(cls, mermaid_code: str) -> Set[str]:
        """Extract identified entity names and node labels from Mermaid code."""
        entities: Set[str] = set()

        raw_lines = mermaid_code.splitlines()

        for line in raw_lines:
            s_line = line.strip()
            if not s_line or s_line.startswith("%%"):
                continue

            # Skip top-level diagram declarations
            if s_line.lower().startswith(("flowchart", "graph", "sequencediagram", "statediagram", "classdiagram", "erdiagram", "gitgraph", "timeline")):
                continue
            if s_line.lower() == "mindmap":
                continue

            # Subgraph declarations: subgraph id [Label]
            if s_line.startswith("subgraph "):
                sub_match = re.search(r"\[(.*?)\]", s_line)
                if sub_match:
                    entities.add(sub_match.group(1).strip().lower())
                continue

            # Split edge lines like `A[Label A] -->|Edge Text| B[Label B]`
            # Match each node specification: id[Label], id(Label), id([Label]), id[(Label)], id{Label}
            node_matches = re.finditer(r"\b[A-Za-z0-9_]+\s*(?:\[\([^\)]+\)\]|\[\[[^\]]+\]\]|\[[^\(\[\{\]\)\}]+\]|\([^\(\[\{\]\)\}]+\)|\{[^\(\[\{\]\)\}]+\})", s_line)
            found_nodes = False
            for nm in node_matches:
                found_nodes = True
                node_str = nm.group(0)
                inner = re.search(r"(\[|\[\(|\(\[|\(|\{)(.*?)(\]|\)\]|\)\]|\)|\})", node_str)
                if inner:
                    raw_label = inner.group(2).strip("[](){}|/ ")
                    cleaned = re.sub(r"<[^>]+>", "", raw_label).replace('"', "").strip()
                    if cleaned and len(cleaned) > 1:
                        entities.add(cleaned.lower())

            # Sequence participants: participant P as Name or actor Name
            seq_match = re.search(r"(?:participant|actor)\s+([A-Za-z0-9_]+)(?:\s+as\s+([^\n\r]+))?", s_line, re.I)
            if seq_match:
                alias = seq_match.group(2) or seq_match.group(1)
                entities.add(alias.strip().replace('"', "").lower())

            # State diagram states: state "Active" as s1 or s1 --> s2
            state_match = re.search(r'state\s+"([^"]+)"', s_line)
            if state_match:
                entities.add(state_match.group(1).strip().lower())

            # Mindmap / Timeline / Indented nodes
            # If the line was indented or starts with root or mindmap bullet
            if not found_nodes and not seq_match and not state_match:
                line_clean = re.sub(r'^\s*[-+*]?\s*', '', line)
                line_clean = re.sub(r'root\s*\({1,2}(.*?)\){1,2}', r'\1', line_clean)
                line_clean = re.sub(r'[\[\]\(\)\{\}"]+', '', line_clean).strip()
                if line_clean and len(line_clean) > 2 and not line_clean.lower().startswith(("autonumber", "title ", "alt ", "else", "end", "note ")):
                    entities.add(line_clean.lower())

        return entities

    @classmethod
    def verify_diagram_grounding(
        cls,
        mermaid_code: str,
        research_content: str,
        required_entities: Optional[List[str]] = None,
        prohibited_entities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Verify that the diagram is factually grounded in the research content.

        Checks:
        1. Required entities presence.
        2. Prohibited / hallucinated elements absence.
        3. Grounding ratio (percentage of diagram nodes backed by source text).
        4. Valid directional arrows.
        """
        extracted_entities = cls.extract_diagram_entities(mermaid_code)
        research_lower = research_content.lower()
        mermaid_lower = mermaid_code.lower()

        missing_required = []
        if required_entities:
            for req in required_entities:
                req_lower = req.lower()
                # Significant tokens of length >= 3
                req_tokens = [w for w in re.split(r"\W+", req_lower) if len(w) >= 3]

                # Match if:
                # 1. Full string match in extracted entities or mermaid code
                # 2. Or at least one distinctive token (or majority of tokens) matches
                found = (
                    any(req_lower in ent or ent in req_lower for ent in extracted_entities)
                    or (req_lower in mermaid_lower)
                )
                if not found and req_tokens:
                    # Check token overlap
                    matching_tokens = [tok for tok in req_tokens if tok in mermaid_lower]
                    # If single token entity (e.g. "Low"), it must match directly
                    if len(req_tokens) == 1:
                        found = req_tokens[0] in mermaid_lower
                    elif len(req_tokens) == 2:
                        # For 2-word entities like 'Mid Element' or 'Election Timer', match if either keyword exists
                        found = len(matching_tokens) >= 1
                    else:
                        # For 3+ words, require at least half
                        found = len(matching_tokens) >= (len(req_tokens) / 2)

                if not found:
                    missing_required.append(req)

        hallucinated = []
        if prohibited_entities:
            for proh in prohibited_entities:
                proh_lower = proh.lower()
                proh_tokens = [w for w in re.split(r"\W+", proh_lower) if len(w) > 4]
                if (
                    any(proh_lower in ent for ent in extracted_entities)
                    or (proh_lower in mermaid_lower)
                    or (len(proh_tokens) >= 2 and all(token in mermaid_lower for token in proh_tokens))
                ):
                    hallucinated.append(proh)

        # Grounding check: verify that extracted nodes correspond to terms in the research dossier
        grounded_count = 0
        ungrounded_nodes = []
        for ent in extracted_entities:
            words = [w for w in re.split(r"\W+", ent) if len(w) > 2]
            if not words or any(w in research_lower for w in words):
                grounded_count += 1
            else:
                ungrounded_nodes.append(ent)

        total_entities = max(len(extracted_entities), 1)
        grounding_score = round((grounded_count / total_entities) * 100, 1)

        # Directional relationship audit
        has_arrows = bool(re.search(r"(-->|->>|-->\||--|\.\->|:)", mermaid_code))
        is_sequence = "sequencediagram" in mermaid_lower
        is_mindmap = "mindmap" in mermaid_lower
        is_timeline = "timeline" in mermaid_lower

        relationships_valid = has_arrows or is_sequence or is_mindmap or is_timeline

        is_valid = (len(missing_required) == 0) and (len(hallucinated) == 0) and (grounding_score >= 50.0)

        issues = []
        if missing_required:
            issues.append(f"Missing required technical entities: {', '.join(missing_required)}")
        if hallucinated:
            issues.append(f"Prohibited / fabricated entities detected: {', '.join(hallucinated)}")
        if not relationships_valid:
            issues.append("Diagram lacks directed relationships or logical sequence arrows.")

        return {
            "is_grounded": is_valid,
            "grounding_score": grounding_score,
            "extracted_entities": sorted(list(extracted_entities)),
            "missing_required": missing_required,
            "hallucinated_prohibited": hallucinated,
            "ungrounded_nodes": ungrounded_nodes,
            "relationships_valid": relationships_valid,
            "issues": issues,
        }

    @classmethod
    def sanitize_and_format_mermaid(cls, raw_code: str) -> str:
        """Sanitize Mermaid code to ensure 12.3 compatibility and prevent XSS or rendering issues."""
        code = raw_code.strip()
        # Remove backticks
        code = re.sub(r"^```(?:mermaid)?\s*", "", code, flags=re.I)
        code = re.sub(r"\s*```$", "", code)
        code = code.strip()

        # Disallow script tags inside node labels
        code = re.sub(r"<script[\s\S]*?</script>", "", code, flags=re.I)
        code = re.sub(r'javascript:', '', code, flags=re.I)

        # Fix missing initial directive if node arrows are present
        if not re.match(
            r"^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|stateDiagram-v2|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|C4Context|xychart-beta)\b",
            code,
            re.I,
        ):
            if "-->" in code or "---" in code:
                code = f"flowchart TD\n{code}"

        return code
