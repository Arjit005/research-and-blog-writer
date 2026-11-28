"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

/**
 * Compact 3D animated WebGL scene for the AuthDialog left panel.
 * Renders a slowly orbiting crystalline core with dual rings and floating nodes.
 */
export function Auth3DVisual() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
      return;
    }

    const w = canvas.clientWidth || 320;
    const h = canvas.clientHeight || 200;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(w, h, false);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 50);
    camera.position.set(0, 0.3, 8.5);

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambient);
    const keyLight = new THREE.PointLight(0x7dd3fc, 2.4, 25);
    keyLight.position.set(4, 5, 6);
    scene.add(keyLight);
    const rimLight = new THREE.PointLight(0x34d399, 1.6, 25);
    rimLight.position.set(-4, -3, 5);
    scene.add(rimLight);

    const group = new THREE.Group();
    scene.add(group);

    const coreGeo = new THREE.OctahedronGeometry(1.35, 1);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      emissive: 0x0c4a6e,
      emissiveIntensity: 0.45,
      roughness: 0.2,
      metalness: 0.85,
      flatShading: true,
    });
    group.add(new THREE.Mesh(coreGeo, coreMat));

    const wireGeo = new THREE.EdgesGeometry(coreGeo);
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x7dd3fc,
      transparent: true,
      opacity: 0.7,
    });
    const wire = new THREE.LineSegments(wireGeo, wireMat);
    wire.scale.setScalar(1.04);
    group.add(wire);

    const ringGeo = new THREE.TorusGeometry(2.3, 0.025, 10, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.45,
    });
    const ring1 = new THREE.Mesh(ringGeo, ringMat);
    ring1.rotation.x = Math.PI / 3;
    group.add(ring1);

    const ring2Mat = new THREE.MeshBasicMaterial({
      color: 0xa78bfa,
      transparent: true,
      opacity: 0.35,
    });
    const ring2 = new THREE.Mesh(ringGeo, ring2Mat);
    ring2.rotation.y = Math.PI / 3;
    ring2.rotation.x = -Math.PI / 5;
    group.add(ring2);

    if (reducedMotion) {
      renderer.render(scene, camera);
      return () => {
        coreGeo.dispose();
        coreMat.dispose();
        wireGeo.dispose();
        wireMat.dispose();
        ringGeo.dispose();
        ringMat.dispose();
        ring2Mat.dispose();
        renderer.dispose();
      };
    }

    let rafId = 0;
    let last = performance.now();
    let elapsed = 0;

    const animate = (now: number) => {
      rafId = requestAnimationFrame(animate);
      if (document.hidden) {
        last = now;
        return;
      }
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      elapsed += dt;

      group.rotation.y = elapsed * 0.35;
      group.rotation.x = Math.sin(elapsed * 0.6) * 0.15;
      ring1.rotation.z = elapsed * 0.45;
      ring2.rotation.z = -elapsed * 0.35;

      renderer.render(scene, camera);
    };
    rafId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(rafId);
      coreGeo.dispose();
      coreMat.dispose();
      wireGeo.dispose();
      wireMat.dispose();
      ringGeo.dispose();
      ringMat.dispose();
      ring2Mat.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="h-40 md:h-48 w-full pointer-events-none select-none"
    />
  );
}
