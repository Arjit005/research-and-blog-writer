"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Pause, Play, RotateCcw, Sparkles, GitBranch, FileCheck2 } from "lucide-react";

type EngineStage = "gather" | "synthesize" | "publish";

interface StageMeta {
  id: EngineStage;
  step: string;
  label: string;
  agent: string;
  summary: string;
  accentHex: number;
  ringSpeed: number;
  spread: number;
  icon: typeof Sparkles;
}

const STAGES: StageMeta[] = [
  {
    id: "gather",
    step: "01",
    label: "Research",
    agent: "Research Analyst",
    summary: "Crawls live sources, verifies citations & extracts key claims",
    accentHex: 0x7dd3fc,
    ringSpeed: 0.35,
    spread: 1.15,
    icon: Sparkles,
  },
  {
    id: "synthesize",
    step: "02",
    label: "Architect",
    agent: "Technical Architect",
    summary: "Builds Mermaid & D2 diagrams + structured visual evidence",
    accentHex: 0xa78bfa,
    ringSpeed: 0.6,
    spread: 0.78,
    icon: GitBranch,
  },
  {
    id: "publish",
    step: "03",
    label: "Publish",
    agent: "Lead Writer & Auditor",
    summary: "Drafts publication-ready Markdown, KaTeX & passes quality audit",
    accentHex: 0x34d399,
    ringSpeed: 0.22,
    spread: 0.52,
    icon: FileCheck2,
  },
];

interface PremiumHeroProps {
  className?: string;
}

const NODE_COUNT = 28;

export function PremiumHero({ className = "" }: PremiumHeroProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stage, setStage] = useState<EngineStage>("gather");
  const [paused, setPaused] = useState(false);
  const [ready, setReady] = useState(false);

  const stageRef = useRef<EngineStage>(stage);
  const pausedRef = useRef<boolean>(paused);
  const orbitRef = useRef({ rotX: 0.18, rotY: 0, dragging: false, lastX: 0, lastY: 0 });

  useEffect(() => {
    stageRef.current = stage;
  }, [stage]);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  const handleResetCamera = useCallback(() => {
    orbitRef.current.rotX = 0.18;
    orbitRef.current.rotY = 0;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      setReady(true);
      return;
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(canvas.clientWidth || 560, canvas.clientHeight || 280, false);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      46,
      (canvas.clientWidth || 560) / (canvas.clientHeight || 280),
      0.1,
      100
    );
    camera.position.set(0, 0.5, 16);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);
    const keyLight = new THREE.PointLight(0x7dd3fc, 2.2, 40);
    keyLight.position.set(6, 8, 10);
    scene.add(keyLight);
    const rimLight = new THREE.PointLight(0xa78bfa, 1.8, 40);
    rimLight.position.set(-7, -5, 8);
    scene.add(rimLight);

    // Central 3D Synthesis Core (Icosahedron + Wireframe)
    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    const coreGeo = new THREE.IcosahedronGeometry(2.1, 1);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      emissive: 0x1e293b,
      emissiveIntensity: 0.4,
      roughness: 0.25,
      metalness: 0.85,
      flatShading: true,
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    rootGroup.add(coreMesh);

    const wireGeo = new THREE.EdgesGeometry(coreGeo);
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x7dd3fc,
      transparent: true,
      opacity: 0.65,
    });
    const wireMesh = new THREE.LineSegments(wireGeo, wireMat);
    wireMesh.scale.setScalar(1.03);
    rootGroup.add(wireMesh);

    // Orbital Rings
    const ringGeo1 = new THREE.TorusGeometry(3.8, 0.03, 12, 72);
    const ringMat1 = new THREE.MeshBasicMaterial({
      color: 0x7dd3fc,
      transparent: true,
      opacity: 0.45,
    });
    const ring1 = new THREE.Mesh(ringGeo1, ringMat1);
    ring1.rotation.x = Math.PI / 3;
    rootGroup.add(ring1);

    const ringGeo2 = new THREE.TorusGeometry(4.8, 0.025, 12, 72);
    const ringMat2 = new THREE.MeshBasicMaterial({
      color: 0xa78bfa,
      transparent: true,
      opacity: 0.3,
    });
    const ring2 = new THREE.Mesh(ringGeo2, ringMat2);
    ring2.rotation.y = Math.PI / 4;
    ring2.rotation.x = -Math.PI / 5;
    rootGroup.add(ring2);

    // Constellation Nodes (Research Sources)
    const nodeGeo = new THREE.SphereGeometry(0.11, 12, 12);
    const nodeMat = new THREE.MeshStandardMaterial({
      color: 0x7dd3fc,
      emissive: 0x38bdf8,
      emissiveIntensity: 0.7,
      roughness: 0.2,
    });

    interface NodeItem {
      mesh: THREE.Mesh;
      basePos: THREE.Vector3;
      phase: number;
    }
    const nodes: NodeItem[] = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      const m = new THREE.Mesh(nodeGeo, nodeMat);
      const r = 4.6 + (i % 3) * 1.1;
      const phi = Math.acos(-1 + (2 * i) / NODE_COUNT);
      const theta = Math.sqrt(NODE_COUNT * Math.PI) * phi;
      const base = new THREE.Vector3(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.sin(phi) * Math.sin(theta) * 0.75,
        r * Math.cos(phi)
      );
      m.position.copy(base);
      rootGroup.add(m);
      nodes.push({ mesh: m, basePos: base, phase: i * 0.45 });
    }

    setReady(true);

    const onResize = () => {
      if (!canvas) return;
      const w = canvas.clientWidth || 560;
      const h = canvas.clientHeight || 280;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
      if (reducedMotion) renderer.render(scene, camera);
    };
    window.addEventListener("resize", onResize);

    if (reducedMotion) {
      renderer.render(scene, camera);
      return () => {
        window.removeEventListener("resize", onResize);
        renderer.dispose();
      };
    }

    let rafId = 0;
    let lastTime = performance.now();
    let elapsed = 0;
    let currentSpread = 1.15;

    const animate = (now: number) => {
      rafId = requestAnimationFrame(animate);
      if (document.hidden) {
        lastTime = now;
        return;
      }
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;

      const activeMeta = STAGES.find((s) => s.id === stageRef.current) || STAGES[0];
      wireMat.color.lerp(new THREE.Color(activeMeta.accentHex), 0.08);
      ringMat1.color.lerp(new THREE.Color(activeMeta.accentHex), 0.08);
      nodeMat.color.lerp(new THREE.Color(activeMeta.accentHex), 0.08);
      keyLight.color.lerp(new THREE.Color(activeMeta.accentHex), 0.08);

      currentSpread += (activeMeta.spread - currentSpread) * 0.06;

      if (!pausedRef.current) {
        elapsed += dt;
        if (!orbitRef.current.dragging) {
          orbitRef.current.rotY += dt * activeMeta.ringSpeed * 0.55;
        }
        coreMesh.rotation.y = elapsed * 0.25;
        wireMesh.rotation.y = elapsed * 0.25;
        ring1.rotation.z = elapsed * activeMeta.ringSpeed;
        ring2.rotation.z = -elapsed * activeMeta.ringSpeed * 0.7;
      }

      rootGroup.rotation.x += (orbitRef.current.rotX - rootGroup.rotation.x) * 0.1;
      rootGroup.rotation.y += (orbitRef.current.rotY - rootGroup.rotation.y) * 0.1;

      for (const n of nodes) {
        const pulse = 1 + Math.sin(elapsed * 1.8 + n.phase) * 0.06;
        n.mesh.position
          .copy(n.basePos)
          .multiplyScalar(currentSpread * pulse);
      }

      renderer.render(scene, camera);
    };
    rafId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", onResize);
      coreGeo.dispose();
      coreMat.dispose();
      wireGeo.dispose();
      wireMat.dispose();
      ringGeo1.dispose();
      ringMat1.dispose();
      ringGeo2.dispose();
      ringMat2.dispose();
      nodeGeo.dispose();
      nodeMat.dispose();
      renderer.dispose();
    };
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    orbitRef.current.dragging = true;
    orbitRef.current.lastX = e.clientX;
    orbitRef.current.lastY = e.clientY;
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!orbitRef.current.dragging) return;
    const dx = e.clientX - orbitRef.current.lastX;
    const dy = e.clientY - orbitRef.current.lastY;
    orbitRef.current.lastX = e.clientX;
    orbitRef.current.lastY = e.clientY;
    orbitRef.current.rotY += dx * 0.008;
    orbitRef.current.rotX = Math.max(
      -0.8,
      Math.min(0.8, orbitRef.current.rotX + dy * 0.008)
    );
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    orbitRef.current.dragging = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore if not captured
    }
  };

  const activeStage = STAGES.find((s) => s.id === stage) || STAGES[0];

  return (
    <div className={`relative w-full ${className}`}>
      {/* 3D Interactive Diorama Stage */}
      <div className="relative h-64 w-full overflow-hidden rounded-2xl border border-border/70 bg-gradient-to-b from-surface-raised/80 to-surface/60 shadow-inner">
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-label="Interactive 3D Research-to-Story Engine — drag to orbit"
          className={`h-full w-full cursor-grab active:cursor-grabbing transition-opacity duration-500 ${
            ready ? "opacity-100" : "opacity-0"
          }`}
        />

        {/* Top-left floating 3D stage badge */}
        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full border border-border/80 bg-surface/85 px-3 py-1 text-[11px] font-medium text-foreground backdrop-blur-md shadow-sm">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
          <span className="font-mono text-[10px] text-accent">{activeStage.step}</span>
          <span>{activeStage.agent}</span>
        </div>

        {/* Top-right 3D camera controls */}
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            title={paused ? "Resume 3D orbit" : "Pause 3D orbit"}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/80 bg-surface/85 text-muted-foreground backdrop-blur-md transition hover:border-border-strong hover:text-foreground"
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={handleResetCamera}
            title="Reset 3D camera"
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/80 bg-surface/85 text-muted-foreground backdrop-blur-md transition hover:border-border-strong hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Bottom-left drag hint */}
        <div className="pointer-events-none absolute bottom-2.5 left-3 text-[10px] font-mono text-muted-foreground/80">
          Drag to orbit · {activeStage.summary}
        </div>
      </div>

      {/* Interactive 3-Stage Pipeline Switcher */}
      <div className="mt-3 grid grid-cols-3 gap-2">
        {STAGES.map((s) => {
          const Icon = s.icon;
          const isActive = s.id === stage;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setStage(s.id)}
              aria-pressed={isActive}
              className={`group flex items-center gap-2 rounded-xl border px-3 py-2 text-left transition-all ${
                isActive
                  ? "border-accent/60 bg-accent-soft text-foreground shadow-sm"
                  : "border-border/70 bg-surface/60 text-muted-foreground hover:border-border-strong hover:text-foreground"
              }`}
            >
              <Icon
                className={`h-3.5 w-3.5 shrink-0 ${
                  isActive ? "text-accent" : "text-muted-foreground group-hover:text-foreground"
                }`}
              />
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold">
                  {s.step}. {s.label}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
