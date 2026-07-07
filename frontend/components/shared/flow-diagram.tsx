"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Fragment } from "react";

import { VIEWPORT } from "@/lib/animations";
import { cn } from "@/lib/utils";

export interface FlowDiagramNode {
  id: string;
  icon: LucideIcon;
  label: string;
}

interface FlowDiagramProps {
  nodes: FlowDiagramNode[];
  className?: string;
}

/** Vertical node flow with an animated "current" pulse travelling the line. */
export function FlowDiagram({ nodes, className }: FlowDiagramProps) {
  return (
    <div className={cn("mx-auto flex max-w-xs flex-col", className)}>
      {nodes.map((node, index) => (
        <Fragment key={node.id}>
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            whileInView={{ opacity: 1, y: 0, scale: 1 }}
            viewport={VIEWPORT}
            transition={{
              type: "spring",
              stiffness: 140,
              damping: 16,
              delay: index * 0.12,
            }}
            className="glass flex items-center gap-3 rounded-2xl px-4 py-3 shadow-soft"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-brand/10 text-brand">
              <node.icon className="size-4" />
            </span>
            <span className="text-sm font-medium">{node.label}</span>
          </motion.div>

          {index < nodes.length - 1 ? (
            <div className="relative mx-auto h-8 w-0.5 overflow-hidden bg-border">
              <motion.span
                aria-hidden
                className="absolute inset-x-0 top-0 h-3 rounded-full bg-brand-gradient"
                initial={{ y: "-100%" }}
                animate={{ y: "300%" }}
                transition={{
                  duration: 1.4,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: index * 0.2,
                }}
              />
            </div>
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}
