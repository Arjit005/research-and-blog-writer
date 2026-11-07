import os
import json
import database as db
from core.visual_extractor import extract_visual_artifacts_from_markdown

os.environ["AUTH_DEV_MODE"] = "true"

def seed_qa_data():
    u = db.get_or_create_user("qa_tester@example.com")
    uid = u["id"]

    content = """# Enterprise Quantum Computing Architecture and Benchmarks

## Executive Summary
This empirical study evaluates topological resilience and gate fidelities across current NISQ quantum processing modalities.

## System Topology
```mermaid
flowchart TD
    subgraph Control Layer
        A[Pulse Arbitrary Waveform Generator] --> B[Cryogenic Attenuators]
    end
    subgraph Dilution Refrigerator (10 mK)
        B --> C[Superconducting Transmon Array]
        C --> D[Josephson Parametric Amplifier]
    end
    subgraph Readout
        D --> E[Heterodyne Demodulation]
        E --> F[Quantum State Tomography]
    end
```

## Empirical Gate Fidelity Analysis
Benchmark evaluations across physical qubit modalities demonstrate distinct coherence horizons.

```chart
{
  "chart_type": "bar",
  "title": "Single and Two-Qubit Gate Fidelity (%)",
  "data": [
    {"label": "Transmon Xmon", "value": 99.85},
    {"label": "Trapped 171Yb+", "value": 99.94},
    {"label": "Silicon Spin Qubit", "value": 99.20},
    {"label": "Neutral Atom Array", "value": 99.60},
    {"label": "Photonic Dual-Rail", "value": 99.10}
  ],
  "x_axis_label": "Modality",
  "y_axis_label": "Fidelity (%)",
  "description": "State-of-the-art randomized benchmarking fidelities gathered in Q1 2026.",
  "units": "%",
  "data_source": "National Metrology Institute and NIST Quantum Consortium",
  "methodology": "Randomized Clifford benchmarking protocol with interleaved gate insertion."
}
```

## Decoherence Timeline
Evolution of coherence times (T1 relaxation lifetime) across cryogenic holding cycles:

```chart
{
  "chart_type": "line",
  "title": "Cryogenic Coherence Evolution (microseconds)",
  "data": [
    {"label": "Cycle 1", "value": 120},
    {"label": "Cycle 2", "value": 135},
    {"label": "Cycle 3", "value": 142},
    {"label": "Cycle 4", "value": 158},
    {"label": "Cycle 5", "value": 165}
  ],
  "description": "Mean T1 relaxation lifetime monitored across continuous refrigeration cycles.",
  "units": "us",
  "data_source": "Cryogenic Telemetry System",
  "methodology": "Inversion recovery sequence measurement."
}
```

## Dilution Instrumentation
![Dilution Refrigerator Infrastructure](https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=1200 "Millikelvin Cryostat Architecture")

The cryostat core maintains base operating temperatures under 15 mK during continuous microwave pulse sequencing.
"""

    art_id = db.save_article("Enterprise Quantum Computing Architecture and Benchmarks", content, user_id=uid)
    print("Saved article ID:", art_id)

    artifacts = extract_visual_artifacts_from_markdown(content, article_id=art_id, user_id=uid)

    for v in artifacts["visuals"]:
        vid = db.save_research_visual(
            user_id=uid,
            article_id=art_id,
            visual_type=v["visual_type"],
            origin_type=v["origin_type"],
            title=v["title"],
            caption=v["caption"],
            description=v.get("description"),
            source_url=v.get("source_url"),
            source_title=v.get("source_title"),
            license_information=v.get("license_information"),
            alt_text=v.get("alt_text"),
            thumbnail_url=v.get("thumbnail_url"),
            media_content=v.get("media_content"),
            file_format=v.get("file_format", "png"),
            metadata_json=v.get("metadata_json"),
        )
        print("Saved visual ID:", vid, v["title"])
        
        # Link sample evidence claim
        db.link_visual_evidence(
            user_id=uid,
            visual_id=vid,
            article_id=art_id,
            claim_id="CLM-001",
            report_section="Dilution Instrumentation",
            evidence_status="verified",
            citation_url="https://doi.org/10.1038/s41586-024-00123-x"
        )

    for c in artifacts["charts"]:
        cid = db.save_research_chart(
            user_id=uid,
            article_id=art_id,
            title=c["title"],
            description=c.get("description"),
            chart_type=c["chart_type"],
            structured_data=c["structured_data"],
            data_source=c.get("data_source"),
            units=c.get("units"),
            methodology=c.get("methodology"),
        )
        print("Saved chart ID:", cid, c["title"])

if __name__ == "__main__":
    seed_qa_data()
