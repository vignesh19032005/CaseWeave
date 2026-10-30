"use client";

import { useMemo, useState } from "react";

export type GraphEntity = { entity_id: string; canonical_name: string; entity_type: string; aliases: string };
export type GraphRelationship = { from_entity_id: string; to_entity_id: string; relationship_type: string };

const TYPE_COLORS: Record<string, string> = {
  person: "#818cf8",
  device: "#34d399",
  location: "#fbbf24",
  organization: "#f472b6",
};
const TYPE_ORDER = ["person", "device", "location", "organization"];

const W = 560;
const H = 380;

type Edge = { from: string; to: string; types: string[] };

export default function EntityGraph({
  entities,
  relationships,
  highlightIds,
}: {
  entities: GraphEntity[];
  relationships: GraphRelationship[];
  highlightIds: Set<string>;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  // Deterministic layout: one circle, entities grouped by type so people,
  // devices and places sit together; edges cross the middle.
  const positions = useMemo(() => {
    const rank = (t: string) => (TYPE_ORDER.indexOf(t) === -1 ? 99 : TYPE_ORDER.indexOf(t));
    const sorted = [...entities].sort(
      (a, b) => rank(a.entity_type) - rank(b.entity_type) || a.canonical_name.localeCompare(b.canonical_name)
    );
    const r = Math.min(W, H) / 2 - 48;
    const pos: Record<string, { x: number; y: number; angle: number }> = {};
    sorted.forEach((e, i) => {
      const angle = (2 * Math.PI * i) / Math.max(sorted.length, 1) - Math.PI / 2;
      pos[e.entity_id] = { x: W / 2 + r * Math.cos(angle), y: H / 2 + r * Math.sin(angle), angle };
    });
    return pos;
  }, [entities]);

  // Merge parallel relationships between the same pair into one edge.
  const edges = useMemo(() => {
    const map = new Map<string, Edge>();
    for (const rel of relationships) {
      if (!positions[rel.from_entity_id] || !positions[rel.to_entity_id]) continue;
      const key = `${rel.from_entity_id}>${rel.to_entity_id}`;
      const edge = map.get(key) ?? { from: rel.from_entity_id, to: rel.to_entity_id, types: [] };
      if (!edge.types.includes(rel.relationship_type)) edge.types.push(rel.relationship_type);
      map.set(key, edge);
    }
    return [...map.values()];
  }, [relationships, positions]);

  if (entities.length === 0) {
    return <div className="text-xs text-zinc-600">No entities resolved yet.</div>;
  }

  const byId = Object.fromEntries(entities.map((e) => [e.entity_id, e]));
  const focus = selected;
  const isActiveEdge = (e: Edge) => !focus || e.from === focus || e.to === focus;
  const selectedEdges = focus ? edges.filter((e) => e.from === focus || e.to === focus) : [];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label="Entity relationship graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#52525b" />
          </marker>
        </defs>
        {edges.map((e) => {
          const a = positions[e.from];
          const b = positions[e.to];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const len = Math.hypot(dx, dy) || 1;
          const pad = 11;
          const active = isActiveEdge(e);
          return (
            <g key={`${e.from}>${e.to}`} opacity={active ? 1 : 0.08}>
              <line
                x1={a.x + (dx / len) * pad}
                y1={a.y + (dy / len) * pad}
                x2={b.x - (dx / len) * pad}
                y2={b.y - (dy / len) * pad}
                stroke={focus && active ? "#a1a1aa" : "#3f3f46"}
                strokeWidth={focus && active ? 1.6 : 1}
                markerEnd="url(#arrow)"
              />
              {focus && active && (
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 3} fontSize="9" fill="#a1a1aa" textAnchor="middle">
                  {e.types[0]}
                  {e.types.length > 1 ? ` +${e.types.length - 1}` : ""}
                </text>
              )}
            </g>
          );
        })}
        {entities.map((ent) => {
          const p = positions[ent.entity_id];
          const color = TYPE_COLORS[ent.entity_type] || "#a1a1aa";
          const lit = highlightIds.has(ent.entity_id);
          const dim = focus && focus !== ent.entity_id && !edges.some(
            (e) => (e.from === focus && e.to === ent.entity_id) || (e.to === focus && e.from === ent.entity_id)
          );
          const right = Math.cos(p.angle) >= 0;
          return (
            <g
              key={ent.entity_id}
              onClick={() => setSelected(selected === ent.entity_id ? null : ent.entity_id)}
              className="cursor-pointer"
              opacity={dim ? 0.25 : 1}
            >
              {lit && <circle cx={p.x} cy={p.y} r={14} fill="none" stroke="#f87171" strokeWidth={2} />}
              <circle
                cx={p.x}
                cy={p.y}
                r={focus === ent.entity_id ? 10 : 8}
                fill={color}
                stroke="#09090b"
                strokeWidth={2}
              />
              <text
                x={p.x + (right ? 14 : -14)}
                y={p.y + 3}
                fontSize="10"
                fill={lit ? "#fecaca" : "#d4d4d8"}
                textAnchor={right ? "start" : "end"}
              >
                {ent.canonical_name.length > 26 ? ent.canonical_name.slice(0, 25) + "…" : ent.canonical_name}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="flex flex-wrap gap-3 text-[10px] text-zinc-500 mt-1">
        {TYPE_ORDER.map((t) => (
          <span key={t} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: TYPE_COLORS[t] }} />
            {t}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-red-400" /> in selected event
        </span>
      </div>

      {focus && byId[focus] && (
        <div className="mt-3 text-xs border-t border-zinc-900 pt-2">
          <div className="text-zinc-200 font-medium">
            {byId[focus].canonical_name} <span className="text-zinc-500">({byId[focus].entity_type})</span>
          </div>
          {(() => {
            const canonical = byId[focus].canonical_name.trim().toLowerCase();
            const otherAliases = (byId[focus].aliases || "")
              .split(",")
              .map((a) => a.trim())
              .filter((a) => a && a.toLowerCase() !== canonical);
            return otherAliases.length > 0 ? (
              <div className="text-zinc-500 mt-0.5">also referred to as: {otherAliases.join(", ")}</div>
            ) : null;
          })()}
          <div className="mt-1.5 space-y-0.5">
            {selectedEdges.length === 0 && <div className="text-zinc-600">No relationships recorded.</div>}
            {selectedEdges.map((e) => (
              <div key={`${e.from}>${e.to}`} className="text-zinc-400">
                {byId[e.from]?.canonical_name} <span className="text-zinc-600">→ {e.types.join(" / ")} →</span>{" "}
                {byId[e.to]?.canonical_name}
              </div>
            ))}
          </div>
        </div>
      )}
      {!focus && <div className="text-[11px] text-zinc-600 mt-2">Click an entity to see its relationships.</div>}
    </div>
  );
}
