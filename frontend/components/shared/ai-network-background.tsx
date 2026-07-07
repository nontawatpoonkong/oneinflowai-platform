"use client";

import { useEffect, useRef } from "react";

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  pulse: number;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

/**
 * Advanced "AI brain" neural background: glowing nodes, dynamic connections,
 * drifting particles, and soft mouse attraction. GPU-light (single canvas,
 * capped counts, DPR clamp) and theme-aware via the --brand CSS variable.
 * Fully paused for prefers-reduced-motion.
 */
export function AINetworkBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    let width = 0;
    let height = 0;
    let raf = 0;
    let nodes: Node[] = [];
    let particles: Particle[] = [];
    const mouse = { x: -9999, y: -9999 };

    const brand = () =>
      getComputedStyle(document.documentElement)
        .getPropertyValue("--brand")
        .trim() || "190 100% 50%";

    function spawnParticle(): Particle {
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        life: Math.random(),
      };
    }

    function resize() {
      if (!canvas || !ctx) return;
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const nodeCount = Math.min(52, Math.floor((width * height) / 26000));
      nodes = Array.from({ length: nodeCount }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: 1.4 + Math.random() * 1.6,
        pulse: Math.random() * Math.PI * 2,
      }));

      const particleCount = Math.min(40, Math.floor((width * height) / 34000));
      particles = Array.from({ length: particleCount }, spawnParticle);
    }

    function frame(t: number) {
      if (!ctx) return;
      const c = brand();
      ctx.clearRect(0, 0, width, height);

      // Particles (soft floating dust).
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.life += 0.005;
        if (p.x < 0 || p.x > width || p.y < 0 || p.y > height) {
          Object.assign(p, spawnParticle());
        }
        const alpha = 0.12 + Math.sin(p.life) * 0.08;
        ctx.fillStyle = `hsl(${c} / ${Math.max(alpha, 0.04)})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 0.8, 0, Math.PI * 2);
        ctx.fill();
      }

      // Nodes: drift + mouse attraction.
      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > width) n.vx *= -1;
        if (n.y < 0 || n.y > height) n.vy *= -1;

        const dx = mouse.x - n.x;
        const dy = mouse.y - n.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 180) {
          n.x += (dx / dist) * 0.5;
          n.y += (dy / dist) * 0.5;
        }
      }

      // Connections.
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 140) {
            ctx.strokeStyle = `hsl(${c} / ${(1 - d / 140) * 0.22})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      // Glowing nodes.
      for (const n of nodes) {
        const glow = 0.6 + Math.sin(t / 900 + n.pulse) * 0.35;
        ctx.fillStyle = `hsl(${c} / ${glow})`;
        ctx.shadowColor = `hsl(${c} / 0.9)`;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;

      raf = requestAnimationFrame(frame);
    }

    function onMove(e: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
    }
    function onLeave() {
      mouse.x = -9999;
      mouse.y = -9999;
    }

    resize();
    frame(0);
    if (reduce) cancelAnimationFrame(raf);

    window.addEventListener("resize", resize);
    if (!reduce) {
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseout", onLeave);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseout", onLeave);
    };
  }, []);

  return (
    <canvas ref={canvasRef} aria-hidden className="absolute inset-0 h-full w-full" />
  );
}
