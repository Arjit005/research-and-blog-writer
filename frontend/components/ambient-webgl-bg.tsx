"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

/**
 * Full-viewport spatial WebGL backdrop rendering floating 3D manuscript folios,
 * a subtle perspective architectural grid, and depth-sorted citation nodes.
 * Synchronizes with light/dark theme and respects prefers-reduced-motion.
 */
export function AmbientWebGLBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: "low-power",
      });
    } catch {
      return;
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(window.innerWidth, window.innerHeight, false);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      48,
      window.innerWidth / window.innerHeight,
      0.1,
      120
    );
    camera.position.set(0, 2.5, 24);

    // Theme-aware palette helper
    const getPalette = () => {
      const isLight =
        document.documentElement.getAttribute("data-theme") === "light";
      return isLight
        ? {
            folio: 0x0d6e66,
            folioOpacity: 0.08,
            wire: 0x0d6e66,
            wireOpacity: 0.14,
            grid: 0x94a3b8,
            gridOpacity: 0.14,
            node: 0x0d6e66,
            nodeAlt: 0xe86544,
          }
        : {
            folio: 0x7dd3fc,
            folioOpacity: 0.06,
            wire: 0x7dd3fc,
            wireOpacity: 0.14,
            grid: 0x334155,
            gridOpacity: 0.22,
            node: 0x7dd3fc,
            nodeAlt: 0xa78bfa,
          };
    };

    let palette = getPalette();

    // Perspective architectural grid floor
    const gridHelper = new THREE.GridHelper(60, 30, palette.grid, palette.grid);
    gridHelper.position.y = -9;
    const gridMat = gridHelper.material as THREE.Material;
    gridMat.transparent = true;
    gridMat.opacity = palette.gridOpacity;
    scene.add(gridHelper);

    // Floating 3D manuscript folios
    const folioGroup = new THREE.Group();
    const folioGeo = new THREE.PlaneGeometry(2.4, 3.2);
    const folioEdgesGeo = new THREE.EdgesGeometry(folioGeo);
    const folioFillMat = new THREE.MeshBasicMaterial({
      color: palette.folio,
      transparent: true,
      opacity: palette.folioOpacity,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const folioWireMat = new THREE.LineBasicMaterial({
      color: palette.wire,
      transparent: true,
      opacity: palette.wireOpacity,
    });

    interface FolioItem {
      mesh: THREE.Group;
      baseY: number;
      speed: number;
      phase: number;
      rotSpeed: number;
    }
    const folios: FolioItem[] = [];
    for (let i = 0; i < 12; i++) {
      const g = new THREE.Group();
      const fill = new THREE.Mesh(folioGeo, folioFillMat);
      const wire = new THREE.LineSegments(folioEdgesGeo, folioWireMat);
      g.add(fill);
      g.add(wire);

      const angle = (i / 12) * Math.PI * 2;
      const radius = 9 + (i % 3) * 4.5;
      g.position.set(
        Math.cos(angle) * radius,
        (Math.random() - 0.5) * 10,
        Math.sin(angle) * radius * 0.6 - 6
      );
      g.rotation.set(
        (Math.random() - 0.5) * 0.4,
        (Math.random() - 0.5) * 0.8,
        (Math.random() - 0.5) * 0.25
      );

      folioGroup.add(g);
      folios.push({
        mesh: g,
        baseY: g.position.y,
        speed: 0.25 + Math.random() * 0.35,
        phase: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.12,
      });
    }
    scene.add(folioGroup);

    // Depth-sorted citation light nodes
    const nodeCount = 42;
    const nodePos = new Float32Array(nodeCount * 3);
    for (let i = 0; i < nodeCount; i++) {
      nodePos[i * 3] = (Math.random() - 0.5) * 34;
      nodePos[i * 3 + 1] = (Math.random() - 0.5) * 18;
      nodePos[i * 3 + 2] = (Math.random() - 0.5) * 18 - 4;
    }
    const pointsGeo = new THREE.BufferGeometry();
    pointsGeo.setAttribute("position", new THREE.BufferAttribute(nodePos, 3));
    const pointsMat = new THREE.PointsMaterial({
      color: palette.nodeAlt,
      size: 0.16,
      transparent: true,
      opacity: 0.55,
    });
    const points = new THREE.Points(pointsGeo, pointsMat);
    scene.add(points);

    // Observe theme changes
    const observer = new MutationObserver(() => {
      palette = getPalette();
      folioFillMat.color.setHex(palette.folio);
      folioFillMat.opacity = palette.folioOpacity;
      folioWireMat.color.setHex(palette.wire);
      folioWireMat.opacity = palette.wireOpacity;
      gridMat.opacity = palette.gridOpacity;
      pointsMat.color.setHex(palette.nodeAlt);
      if (reducedMotion) renderer.render(scene, camera);
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });

    const onResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight, false);
      if (reducedMotion) renderer.render(scene, camera);
    };
    window.addEventListener("resize", onResize);

    // Render once for reduced motion
    if (reducedMotion) {
      renderer.render(scene, camera);
      return () => {
        observer.disconnect();
        window.removeEventListener("resize", onResize);
        folioGeo.dispose();
        folioEdgesGeo.dispose();
        folioFillMat.dispose();
        folioWireMat.dispose();
        pointsGeo.dispose();
        pointsMat.dispose();
        renderer.dispose();
      };
    }

    let rafId = 0;
    let lastTime = performance.now();
    let elapsed = 0;

    const animate = (now: number) => {
      rafId = requestAnimationFrame(animate);
      if (document.hidden) {
        lastTime = now;
        return;
      }
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;
      elapsed += dt;

      folioGroup.rotation.y = elapsed * 0.035;
      points.rotation.y = -elapsed * 0.02;

      for (const f of folios) {
        f.mesh.position.y = f.baseY + Math.sin(elapsed * f.speed + f.phase) * 0.55;
        f.mesh.rotation.y += f.rotSpeed * dt;
      }

      renderer.render(scene, camera);
    };
    rafId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(rafId);
      observer.disconnect();
      window.removeEventListener("resize", onResize);
      folioGeo.dispose();
      folioEdgesGeo.dispose();
      folioFillMat.dispose();
      folioWireMat.dispose();
      pointsGeo.dispose();
      pointsMat.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 h-full w-full opacity-80"
    />
  );
}
