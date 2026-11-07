"""Ground-truth 25-topic evaluation dataset for adaptive diagram generation and visual quality auditing."""

TOPIC_EVALUATION_DATASET = [
    {
        "id": "TOPIC-01",
        "topic": "Zero-Trust Cloud Security Architecture",
        "category": "Cloud Security",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Identity Provider", "Policy Decision Point", "Policy Enforcement Point", "Microsegmentation"],
        "expected_relationships": ["Continuous verification before granting access to resources", "Least privilege policy enforcement"],
        "prohibited_elements": ["Perimeter-only firewall with implicit internal trust", "Static bypass credentials"],
        "sample_grounded_mermaid": """flowchart TD
    User([Subject / Workload]) --> PEP[Policy Enforcement Point]
    PEP <-->|Evaluate Context| PDP[Policy Decision Point]
    PDP <-->|Verify Claims| IdP[(Identity Provider / MFA)]
    PDP <-->|Threat Intel| CDM[(Continuous Diagnostics)]
    PEP -->|Encrypted mTLS| Resource[Microsegmentation & Protected Workload]
""",
    },
    {
        "id": "TOPIC-02",
        "topic": "zk-SNARK vs zk-STARK Cryptographic Proofs",
        "category": "Zero-Knowledge Proofs",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Prover", "Verifier", "Arithmetic Circuit", "Trusted Setup", "FRI Protocol"],
        "expected_relationships": ["Prover generates proof without revealing witness", "STARK uses transparent FRI without trusted setup"],
        "prohibited_elements": ["STARK requires trusted setup", "Verifier learns witness secret"],
        "sample_grounded_mermaid": """flowchart LR
    subgraph zkSNARK [zk-SNARK Architecture]
        Circ[Arithmetic Circuit Representation] --> SNARK_P[Prover]
        CRS[Common Reference String / Trusted Setup] --> SNARK_P
        SNARK_P -->|Succinct Proof| SNARK_V[Verifier]
    end
    subgraph zkSTARK [zk-STARK Architecture]
        FRI[Transparent FRI Protocol / No Setup] --> STARK_P[Prover]
        STARK_P -->|Quantum Resistant Proof| STARK_V[Verifier]
    end
""",
    },
    {
        "id": "TOPIC-03",
        "topic": "Hierarchical Multi-Agent Consensus Architecture",
        "category": "Multi-Agent AI",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Orchestrator Agent", "Specialist Subagents", "Shared Memory", "Consensus Arbiter"],
        "expected_relationships": ["Orchestrator assigns subtasks", "Arbiter validates consensus before final answer"],
        "prohibited_elements": ["Single prompt monolithic agent", "Unbounded infinite deliberation loop"],
        "sample_grounded_mermaid": """flowchart TD
    UserGoal([User Research Goal]) --> Orch[Orchestrator Agent]
    Orch --> WorkerA[Specialist Subagents: Agent A]
    Orch --> WorkerB[Specialist Subagents: Agent B]
    WorkerA <--> Memory[(Shared Memory Semantic Blackboard)]
    WorkerB <--> Memory
    WorkerA --> Arbiter{Consensus Arbiter}
    WorkerB --> Arbiter
    Arbiter -->|Majority Agreement| Output([Verified Synthesis])
""",
    },
    {
        "id": "TOPIC-04",
        "topic": "Event-Driven Microservices with Saga Pattern",
        "category": "Microservices",
        "expected_diagram_type": "sequence",
        "required_entities": ["Order Service", "Payment Service", "Inventory Service", "Event Broker"],
        "expected_relationships": ["Event triggers next service", "Failure triggers compensating transaction"],
        "prohibited_elements": ["Blocking Two-Phase Commit 2PC across microservices"],
        "sample_grounded_mermaid": """sequenceDiagram
    autonumber
    actor Customer
    participant Order as Order Service
    participant Broker as Event Broker
    participant Payment as Payment Service
    participant Inventory as Inventory Service

    Customer->>Order: Create Order
    Order->>Broker: Publish OrderCreatedEvent
    Broker->>Payment: Handle Payment
    alt Payment Succeeded
        Payment->>Broker: Publish PaymentSucceededEvent
        Broker->>Inventory: Reserve Stock
    else Payment Failed
        Payment->>Broker: Publish PaymentFailedEvent
        Broker->>Order: Trigger Compensating Cancellation
    end
""",
    },
    {
        "id": "TOPIC-05",
        "topic": "Binary Search Algorithm Mechanics",
        "category": "Algorithmic / CS",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Sorted Array", "Low Index", "High Index", "Mid Element", "Target Comparison"],
        "expected_relationships": ["Array must be sorted", "Halves search interval every iteration"],
        "prohibited_elements": ["Linear unsorted sequential scan", "Sorting elements inside loop"],
        "sample_grounded_mermaid": """flowchart TD
    Start([Sorted Array & Target]) --> Init[Low = 0, High = N - 1]
    Init --> Check{Low <= High?}
    Check -->|No| NotFound([Return -1: Not Found])
    Check -->|Yes| CalcMid[Mid = Low + High / 2]
    CalcMid --> Compare{Arr Mid == Target?}
    Compare -->|Equal| Found([Return Mid Index])
    Compare -->|Target < Mid| AdjHigh[High = Mid - 1]
    Compare -->|Target > Mid| AdjLow[Low = Mid + 1]
    AdjHigh --> Check
    AdjLow --> Check
""",
    },
    {
        "id": "TOPIC-06",
        "topic": "Dijkstra's Shortest Path vs A* Heuristic Search",
        "category": "Graph Algorithms",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Priority Queue", "Min Distance", "Adjacency List", "Heuristic Function"],
        "expected_relationships": ["Dijkstra evaluates g(n) cost", "A* incorporates f(n) = g(n) + h(n)"],
        "prohibited_elements": ["Negative weight cycle handling with basic Dijkstra"],
        "sample_grounded_mermaid": """flowchart TD
    StartNode([Start Node]) --> PQ[(Priority Queue / Min-Heap)]
    PQ --> Pop[Extract Node with Min Distance]
    Pop --> TargetCheck{Is Target?}
    TargetCheck -->|Yes| Path([Shortest Path Reached])
    TargetCheck -->|No| Relax[Adjacency List: Relax Neighbor Edges]
    Relax --> ScoreCalc[Dijkstra: cost g | A*: Heuristic Function f = g + h]
    ScoreCalc --> PushPQ[Push Updated Distances to PQ]
    PushPQ --> PQ
""",
    },
    {
        "id": "TOPIC-07",
        "topic": "End-to-End MLOps Pipeline & Continuous Training",
        "category": "ML Pipelines",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Feature Store", "Data Validation", "Model Training", "Model Registry", "Drift Monitor"],
        "expected_relationships": ["Raw data validated before training", "Drift trigger restarts continuous training"],
        "prohibited_elements": ["Deploying directly without validation gate"],
        "sample_grounded_mermaid": """flowchart LR
    Data[(Raw Data Lake)] --> Val[Data Validation & Great Expectations]
    Val --> FS[(Feature Store)]
    FS --> Train[Distributed Training / GPU]
    Train --> Eval{Evaluation Gate}
    Eval -->|Pass| Reg[(Model Registry)]
    Reg --> Serve[Serving Endpoint / Canary]
    Serve --> Monitor[Drift & Performance Monitor]
    Monitor -->|Data Drift Detected| Train
""",
    },
    {
        "id": "TOPIC-08",
        "topic": "Transformer Self-Attention Layer Computations",
        "category": "Neural Networks",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Input Embeddings", "Query Matrix", "Key Matrix", "Value Matrix", "Softmax", "Scaled Dot-Product"],
        "expected_relationships": ["Q and K multiply then scale", "Softmax applies to attention weights before V multiply"],
        "prohibited_elements": ["Recurrent hidden state loops inside self-attention"],
        "sample_grounded_mermaid": """flowchart TD
    Input([Input Embeddings X]) --> Proj[Linear Projections]
    Proj --> Q[Query Matrix Q]
    Proj --> K[Key Matrix K]
    Proj --> V[Value Matrix V]
    Q & K --> MatMul1[Scaled Dot-Product MatMul Q * K^T]
    MatMul1 --> Scale[Scale / sqrt dk]
    Scale --> Softmax[Softmax Attention Weights]
    Softmax & V --> MatMul2[MatMul Weights * V]
    MatMul2 --> Out([Output Context Vectors])
""",
    },
    {
        "id": "TOPIC-09",
        "topic": "Distributed Consensus with Raft Algorithm",
        "category": "Distributed Databases",
        "expected_diagram_type": "state",
        "required_entities": ["Follower", "Candidate", "Leader", "Election Timer", "Heartbeat RPC"],
        "expected_relationships": ["Follower timeout transitions to Candidate", "Candidate with majority votes becomes Leader"],
        "prohibited_elements": ["Multiple active leaders simultaneously in same term"],
        "sample_grounded_mermaid": """stateDiagram-v2
    [*] --> Follower
    Follower --> Candidate: Election Timer Timeout Elapsed
    Candidate --> Candidate: Split Vote / New Term
    Candidate --> Leader: Receives Votes from Majority
    Leader --> Follower: Heartbeat RPC or Discovers Higher Term
    Candidate --> Follower: Discovers Current Leader
    Leader --> [*]: Shutdown
""",
    },
    {
        "id": "TOPIC-10",
        "topic": "Mitigating OAuth 2.0 PKCE Authorization Code Interception",
        "category": "Cybersecurity",
        "expected_diagram_type": "sequence",
        "required_entities": ["Client App", "Authorization Server", "Code Verifier", "Code Challenge", "Token Endpoint"],
        "expected_relationships": ["Client sends challenge in auth request", "Client sends verifier to token endpoint to prove ownership"],
        "prohibited_elements": ["Storing plain client secret in public mobile app", "Skipping SHA256 code challenge check"],
        "sample_grounded_mermaid": """sequenceDiagram
    autonumber
    participant App as Mobile/SPA Client
    participant AS as Authorization Server
    participant RS as Resource Server

    App->>App: Generate code_verifier & code_challenge (S256)
    App->>AS: /authorize?code_challenge=xyz&method=S256
    AS-->>App: Auth Code (redirect)
    App->>AS: /token?code=123&code_verifier=secret
    Note over AS: Verify SHA256(verifier) == challenge
    AS-->>App: Access Token + ID Token
    App->>RS: Request Data (Bearer Token)
    RS-->>App: Protected Resource
""",
    },
    {
        "id": "TOPIC-11",
        "topic": "Ethereum Proof-of-Stake Consensus & Finality",
        "category": "Blockchain",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Beacon Chain", "Validator Committee", "Slot Proposal", "Casper FFG Attestation", "Finalized Epoch"],
        "expected_relationships": ["Validator proposes block in slot", "Supermajority 2/3 attestations finalize epoch"],
        "prohibited_elements": ["Proof of Work mining difficulty nonce hashes"],
        "sample_grounded_mermaid": """flowchart LR
    Slot[Slot: Selected Proposer] --> Block[Proposes Beacon Block]
    Block --> Comm[Validator Committee]
    Comm -->|LMD-GHOST Vote| Head[Head of Chain]
    Comm -->|Casper FFG Vote| Epoch[Epoch Boundary 32 Slots]
    Epoch -->|2/3 Supermajority| Justified[Justified Checkpoint]
    Justified -->|Consecutive Epoch| Finalized([Finalized State])
""",
    },
    {
        "id": "TOPIC-12",
        "topic": "Global Carbon Cycle & Atmospheric Feedbacks",
        "category": "Climate Change",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Atmospheric CO2", "Oceans Sink", "Terrestrial Biosphere", "Fossil Emissions", "Carbon Flux"],
        "expected_relationships": ["Combustion increases atmospheric carbon", "Ocean absorbs CO2 causing acidification"],
        "prohibited_elements": ["Atmospheric carbon disappearing without natural sink"],
        "sample_grounded_mermaid": """flowchart TD
    Fossil[Fossil Fuel Combustion & Industry] -->|Carbon Flux| Atmos[Atmospheric CO2 Reservoir]
    Atmos <-->|Photosynthesis / Respiration| Land[Terrestrial Biosphere]
    Atmos <-->|Solubility / Biological Pump| Ocean[Ocean Carbon Sink]
    Ocean -->|Acidification Impact| Marine[Marine Ecosystems]
    Atmos -->|Radiative Forcing| Warming([Global Temperature Rise])
""",
    },
    {
        "id": "TOPIC-13",
        "topic": "Fall of the Western Roman Empire Causality Matrix",
        "category": "Historical Events",
        "expected_diagram_type": "mindmap",
        "required_entities": ["Economic Inflation", "Barbarian Invasions", "Military Decentralization", "Political Instability"],
        "expected_relationships": ["Multi-causal factors leading to 476 CE fall of Ravenna"],
        "prohibited_elements": ["Monocausal single event explanation", "Modern nuclear or drone anachronisms"],
        "sample_grounded_mermaid": """mindmap
  root((Fall of Western Roman Empire 476 CE))
    Military Factors
      Foederati Reliance
      Loss of Discipline
      Barbarian Invasions
    Economic Pressures
      Debasement of Coinage
      Trade Disruption
      Heavy Taxation
    Political Crises
      Succession Civil Wars
      Division of East and West
      Capital Shift from Rome
""",
    },
    {
        "id": "TOPIC-14",
        "topic": "Fractional Reserve Banking & Liquidity Mechanisms",
        "category": "Economic Systems",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Depositor", "Commercial Bank", "Reserve Requirement", "Loan Creation", "Money Multiplier"],
        "expected_relationships": ["Bank holds reserve fraction and loans remaining amount"],
        "prohibited_elements": ["100% full reserve assumption", "Bank burning deposit assets"],
        "sample_grounded_mermaid": """flowchart LR
    Dep([Initial Depositor: $1,000]) --> Bank[Commercial Bank]
    Bank -->|10% Reserve| Res[(Central Bank Vault: $100)]
    Bank -->|90% Excess Reserve| Loan[Borrower Loan: $900]
    Loan --> Dep2[Merchant Secondary Deposit: $900]
    Dep2 --> Multiplier([Money Supply Multiplier Effect])
""",
    },
    {
        "id": "TOPIC-15",
        "topic": "CRISPR-Cas9 Gene Editing Workflow",
        "category": "Scientific Workflows",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Guide RNA", "Cas9 Endonuclease", "PAM Sequence", "Double-Strand Break", "DNA Repair"],
        "expected_relationships": ["gRNA directs Cas9 to target locus adjacent to PAM", "DNA cleavage induces cellular repair (NHEJ or HDR)"],
        "prohibited_elements": ["Non-specific enzymatic digestion without PAM recognition"],
        "sample_grounded_mermaid": """flowchart LR
    Design[Design sgRNA Target] --> Complex[Cas9 + sgRNA Ribonucleoprotein]
    Complex --> PAM[PAM NGG Recognition on DNA]
    PAM --> Unwind[DNA Strand Unwinding & sgRNA Hybridization]
    Unwind --> Cleave[Double-Strand Break DSB Generation]
    Cleave --> Repair{Cellular Repair Pathway}
    Repair -->|NHEJ Error-Prone| KO([Gene Knockout / Indel])
    Repair -->|HDR with Donor| Edit([Precise Gene Insertion])
""",
    },
    {
        "id": "TOPIC-16",
        "topic": "Relational SQL vs Document NoSQL Trade-off Matrix",
        "category": "Comparative Tech",
        "expected_diagram_type": "mindmap",
        "required_entities": ["Relational SQL", "Document NoSQL", "ACID Guarantees", "Horizontal Sharding", "Schema Flexibility"],
        "expected_relationships": ["SQL emphasizes strict consistency", "NoSQL emphasizes partition tolerance"],
        "prohibited_elements": ["Claim that SQL databases cannot scale horizontally", "Zero ACID in modern document stores"],
        "sample_grounded_mermaid": """mindmap
  root((Database Architectural Paradigms))
    Relational SQL
      Strict Schema Normalization
      ACID Transactions
      Complex Multi-Table Joins
      Vertical Scaling Focus
    Document NoSQL
      Polymorphic JSON Documents
      Dynamic Schemas
      Horizontal Sharding by Key
      BASE Eventual Consistency
""",
    },
    {
        "id": "TOPIC-17",
        "topic": "TLS 1.3 Handshake Protocol Flow",
        "category": "Network Security",
        "expected_diagram_type": "sequence",
        "required_entities": ["Client", "Server", "ClientHello", "KeyShare", "ServerHello", "EncryptedExtensions"],
        "expected_relationships": ["Key exchange completes in 1-RTT", "Application data sent immediately after handshake"],
        "prohibited_elements": ["2-RTT RSA static key exchange (removed in TLS 1.3)"],
        "sample_grounded_mermaid": """sequenceDiagram
    autonumber
    participant Client
    participant Server

    Client->>Server: ClientHello (Supported Ciphers + KeyShare ECDH)
    Server->>Client: ServerHello (Selected Cipher + KeyShare ECDH)
    Note over Client,Server: Shared Secret Derived (1-RTT)
    Server->>Client: {EncryptedExtensions + Certificate + Finished}
    Client->>Server: {Finished}
    Client->>Server: [Encrypted Application Data]
    Server->>Client: [Encrypted Application Data]
""",
    },
    {
        "id": "TOPIC-18",
        "topic": "Deep Reinforcement Learning with PPO (Proximal Policy Optimization)",
        "category": "Machine Learning",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Environment", "Policy Network", "Value Function", "Clipped Objective", "Advantage Estimation"],
        "expected_relationships": ["Clipped surrogate loss limits step size to prevent catastrophic policy collapse"],
        "prohibited_elements": ["Unbounded policy update", "Q-table tabular lookup without neural network"],
        "sample_grounded_mermaid": """flowchart TD
    Env[Environment] -->|State s_t| Actor[Policy Network pi_theta]
    Env -->|State s_t| Critic[Critic: Value Function V_phi]
    Actor -->|Action a_t| Env
    Env -->|Reward r_t| GAE[Advantage Estimation: GAE A_t]
    Critic --> GAE
    GAE & Actor --> Ratio[Probability Ratio r_theta]
    Ratio --> Clip[Clipped Objective: clip r 1-eps 1+eps]
    Clip --> Opt[SGD Policy Update with Trust Region Penalty]
    Opt --> Actor
""",
    },
    {
        "id": "TOPIC-19",
        "topic": "Quantum Key Distribution (QKD) BB84 Protocol",
        "category": "Quantum Information",
        "expected_diagram_type": "sequence",
        "required_entities": ["Alice", "Bob", "Quantum Channel", "Public Classical Channel", "Basis Sifting"],
        "expected_relationships": ["Qubits sent over quantum link", "Basis comparison occurs over authenticated classical link"],
        "prohibited_elements": ["Cloning unknown quantum state", "Faster than light transmission"],
        "sample_grounded_mermaid": """sequenceDiagram
    autonumber
    participant Alice
    participant QC as Quantum Channel (Photons)
    participant CC as Public Classical Channel
    participant Bob

    Alice->>QC: Transmit Qubits in Random Bases (+ or x)
    QC->>Bob: Receive & Measure in Random Bases
    Alice->>CC: Announce Chosen Bases for Basis Sifting
    Bob->>CC: Confirm Matching Bases
    Note over Alice,Bob: Sifted Key Retained
    Alice->>CC: Compare Test Sample for Eavesdropping
    Note over Alice,Bob: Privacy Amplification -> Secret Key
""",
    },
    {
        "id": "TOPIC-20",
        "topic": "Git Internals: Blobs, Trees, Commits, and References",
        "category": "Developer Tooling",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Blob Object", "Tree Object", "Commit Object", "HEAD Reference"],
        "expected_relationships": ["Commit points to Root Tree and Parent Commit", "Tree points to Blobs and Subtrees"],
        "prohibited_elements": ["Storing line-by-line diffs as primary git objects (Git stores snapshots)"],
        "sample_grounded_mermaid": """flowchart TD
    HEAD[HEAD Ref] --> Main[refs/heads/main]
    Main --> Commit2[Commit 2: SHA-c2]
    Commit2 -->|Parent| Commit1[Commit 1: SHA-c1]
    Commit2 -->|Tree Pointer| TreeRoot[Root Tree: SHA-t2]
    TreeRoot --> Blob1[Blob: README.md]
    TreeRoot --> SubTree[Subtree: src/]
    SubTree --> Blob2[Blob: main.py]
""",
    },
    {
        "id": "TOPIC-21",
        "topic": "High-Throughput Stream Processing with Apache Kafka",
        "category": "Distributed Systems",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Producers", "Topic Partitions", "Consumer Groups", "Leader Broker", "ISR Replication"],
        "expected_relationships": ["Messages partitioned by hash", "Consumers in group divide partitions without conflict"],
        "prohibited_elements": ["Shared mutable queue with out-of-order intra-partition consumption"],
        "sample_grounded_mermaid": """flowchart LR
    P[Producers] -->|Hash Key| Topic{Kafka Topic: Orders}
    subgraph Brokers [Kafka Cluster]
        Topic --> P0[Topic Partitions 0: Leader Broker 1]
        Topic --> P1[Topic Partitions 1: Leader Broker 2]
        P0 -.->|ISR Replication| Follower0[(ISR Follower Replica)]
    end
    subgraph ConsumerGroup [Consumer Groups A]
        P0 --> C1[Consumer Instance 1]
        P1 --> C2[Consumer Instance 2]
    end
""",
    },
    {
        "id": "TOPIC-22",
        "topic": "Solid State Battery Electrochemistry Mechanisms",
        "category": "Materials Science",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Solid Electrolyte", "Lithium Metal Anode", "Cathode Material", "Dendrite Barrier"],
        "expected_relationships": ["Li+ ions migrate through ceramic/polymer solid matrix", "Solid electrolyte physically suppresses dendrites"],
        "prohibited_elements": ["Volatile liquid organic carbonate solvents in all-solid-state cells"],
        "sample_grounded_mermaid": """flowchart LR
    Anode[Lithium Metal Anode] <-->|Li+ Ion Transport| SE[Solid Electrolyte Matrix / Ceramic]
    SE <-->|Interfacial Charge Transfer| Cathode[High-Nickel Composite Cathode]
    SE -.->|Mechanical Barrier| Dendrite[Dendrite Suppression Zone]
    Anode -->|External Electron Flow e-| Circuit([External Circuit / Workload]) --> Cathode
""",
    },
    {
        "id": "TOPIC-23",
        "topic": "Cellular Respiration: Glycolysis to Oxidative Phosphorylation",
        "category": "Biochemistry",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Glucose", "Glycolysis", "Pyruvate", "Krebs Cycle", "Electron Transport Chain", "ATP Synthase"],
        "expected_relationships": ["Glycolysis occurs in cytoplasm producing pyruvate", "ETC creates proton gradient powering ATP synthase"],
        "prohibited_elements": ["Oxidative phosphorylation occurring without oxygen terminal acceptor in aerobic respiration"],
        "sample_grounded_mermaid": """flowchart TD
    Glucose([Glucose C6H12O6]) -->|Cytoplasm| Glyco[Glycolysis: Net 2 ATP + 2 NADH]
    Glyco --> Pyruvate[Pyruvate Oxidation]
    Pyruvate -->|Matrix| Krebs[Krebs Cycle: 2 ATP + NADH + FADH2]
    Krebs -->|Inner Mitochondrial Membrane| ETC[Electron Transport Chain Complex I-IV]
    ETC -->|Proton Gradient H+| Synthase[ATP Synthase]
    Synthase --> ATP([~30-32 ATP Output])
""",
    },
    {
        "id": "TOPIC-24",
        "topic": "Container Orchestration Scheduling with Kubernetes Kube-Scheduler",
        "category": "Cloud Infrastructure",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Unscheduled Pod", "API Server", "Filtering Phase", "Scoring Phase", "Binding Node"],
        "expected_relationships": ["Filtering eliminates ineligible nodes", "Scoring ranks eligible nodes to select the highest-scoring host"],
        "prohibited_elements": ["Kubelet scheduling cluster-wide pods", "Skipping filtering predicates"],
        "sample_grounded_mermaid": """flowchart TD
    Pod([Unscheduled Pod in etcd]) --> API[kube-apiserver]
    API --> Sched[kube-scheduler]
    Sched --> Filter[1. Filtering: Predicates / Resource Checks]
    Filter --> Score[2. Scoring: Priorities / Affinity Weights]
    Score --> Select[3. Select Highest Ranked Worker Node]
    Select --> Bind[4. Create Binding Object]
    Bind --> API
    API --> Kubelet[Worker Kubelet Launches Container]
""",
    },
    {
        "id": "TOPIC-25",
        "topic": "Comparative Evaluation: Monolith vs Modular Monolith vs Microservices",
        "category": "Software Architecture",
        "expected_diagram_type": "flowchart",
        "required_entities": ["Monolith", "Modular Monolith", "Microservices", "Network Latency", "Deployment Autonomy"],
        "expected_relationships": ["Monolith has in-process calls without network overhead", "Microservices offer deployment autonomy at network latency cost"],
        "prohibited_elements": ["Claim that microservices are unconditionally faster", "Ignoring distributed failure modes"],
        "sample_grounded_mermaid": """flowchart LR
    Need[Architecture Decision] --> Scale{Primary Scaling Constraint?}
    Scale -->|Team < 15 / Early Stage| Mono[Traditional Monolith: Rapid Iteration]
    Scale -->|Codebase Growth / Strict Boundaries| ModMono[Modular Monolith: In-Process Boundaries]
    Scale -->|Multi-Team Autonomy / Polyglot| Micro[Microservices: Independent Deployments]
    Micro --> Tradeoff[Trade-off: Network RPC Latency & Observability Overhead]
""",
    },
]
