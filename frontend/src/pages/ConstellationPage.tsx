import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import * as d3 from "d3";
import { api } from "../api/client";

const CAT_CONFIG: Record<string, { color: string; label: string; angle: number }> = {
  crypto: { color: "#f59e0b", label: "CRYPTO", angle: Math.PI * 0.15 },
  ai: { color: "#818cf8", label: "AI", angle: Math.PI * 1.1 },
  macro: { color: "#34d399", label: "MACRO", angle: Math.PI * 1.75 },
  fintech: { color: "#f472b6", label: "FINTECH", angle: Math.PI * 0.65 },
  other: { color: "#64748b", label: "OTHER", angle: Math.PI * 0.4 },
};

function categorize(tag: string): string {
  const s = tag.toLowerCase();
  if (s.includes("btc") || s.includes("crypto") || s.includes("stablecoin") || s.includes("pyusd") || s.includes("coin")) return "crypto";
  if (s.includes("ai") || s.includes("openai") || s.includes("llm") || s.includes("model") || s.includes("memory") || s.includes("semiconductor") || s.includes("china-ai") || s.includes("alibaba")) return "ai";
  if (s.includes("credit") || s.includes("regulatory") || s.includes("rate") || s.includes("fed") || s.includes("macro") || s.includes("gold")) return "macro";
  if (s.includes("fintech") || s.includes("mastercard") || s.includes("acquisition") || s.includes("paypal")) return "fintech";
  return "other";
}

function parseTradingPlay(play: string | null): { bullPct: number; bullText: string; bearPct: number; bearText: string } | null {
  if (!play) return null;

  const bullPctMatch = play.match(/BULL_PCT:\s*(\d+)/);
  const bearPctMatch = play.match(/BEAR_PCT:\s*(\d+)/);
  const bullTextMatch = play.match(/BULL:\s*(.+?)(?=\n\n|BEAR_PCT|$)/s);
  const bearTextMatch = play.match(/BEAR:\s*(.+?)$/s);

  // Fallback for old SCENARIO format
  if (!bullPctMatch) {
    const scenarioA = play.match(/SCENARIO A:\s*(.+?)(?=SCENARIO B|$)/s);
    const scenarioB = play.match(/SCENARIO B:\s*(.+?)$/s);
    if (scenarioA && scenarioB) {
      return { bullPct: 50, bullText: scenarioA[1].trim(), bearPct: 50, bearText: scenarioB[1].trim() };
    }
    return null;
  }

  return {
    bullPct: parseInt(bullPctMatch[1], 10),
    bullText: bullTextMatch ? bullTextMatch[1].trim() : "",
    bearPct: bearPctMatch ? parseInt(bearPctMatch[1], 10) : 100 - parseInt(bullPctMatch[1], 10),
    bearText: bearTextMatch ? bearTextMatch[1].trim() : "",
  };
}

interface ActiveEvent {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  sources: string[];
}

interface EventNode extends d3.SimulationNodeDatum {
  id: string;
  eventId: number;
  type: "event";
  score: number;
  sourceCount: number;
  sources: string[];
  cat: string;
  r: number;
}

interface GraphLink extends d3.SimulationLinkDatum<EventNode> {
  type: string;
}

export function ConstellationPage() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventNode | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["events-active-constellation"],
    queryFn: async () => {
      const res = await fetch("/api/events/active");
      if (!res.ok) {
        throw new Error(`Failed to fetch active events: ${res.status}`);
      }
      const json = await res.json();
      return json.events as ActiveEvent[];
    },
    staleTime: 120_000,
  });

  const { data: eventDetail } = useQuery({
    queryKey: ["event-detail", selectedEvent?.eventId],
    queryFn: () => api.eventDetail(selectedEvent!.eventId),
    enabled: selectedEvent !== null,
  });

  const tradingPlay = eventDetail ? parseTradingPlay(eventDetail.event.trading_play) : null;

  useEffect(() => {
    if (!data || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const W = svgRef.current.clientWidth;
    const H = svgRef.current.clientHeight;
    const cx = W / 2;
    const cy = H / 2;

    // Filter to multi-source events only, limit to top 30
    const events = data
      .filter((e) => e.source_count >= 2)
      .slice(0, 30);

    if (events.length === 0) return;

    // Build nodes
    const nodes: EventNode[] = events.map((e) => {
      const cat = categorize(e.narrative_tag);
      const catConfig = CAT_CONFIG[cat];
      const angle = catConfig.angle + (Math.random() - 0.5) * 0.7;
      const dist = 100 + e.signal_score * 20 + Math.random() * 50;
      return {
        id: e.narrative_tag,
        eventId: e.id,
        type: "event",
        score: e.signal_score,
        sourceCount: e.source_count,
        sources: e.sources || [],
        cat,
        r: Math.max(6, e.signal_score * 3.2),
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
      };
    });

    // Build links (same category + both score >= 3)
    const links: GraphLink[] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        if (nodes[i].cat === nodes[j].cat && nodes[i].score >= 3 && nodes[j].score >= 3) {
          links.push({ source: nodes[i].id, target: nodes[j].id, type: "source" });
        }
      }
    }

    // Cluster centers
    const clusterCenters: Record<string, { x: number; y: number }> = {};
    Object.entries(CAT_CONFIG).forEach(([k, v]) => {
      clusterCenters[k] = { x: cx + Math.cos(v.angle) * 200, y: cy + Math.sin(v.angle) * 200 };
    });

    // Zoom
    const gAll = svg.append("g");
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 5])
      .on("zoom", (e) => gAll.attr("transform", e.transform.toString()));
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity.scale(0.9).translate(W * 0.05, H * 0.05));

    // Background rect for zoom/pan
    gAll
      .append("rect")
      .attr("width", W * 3)
      .attr("height", H * 3)
      .attr("x", -W)
      .attr("y", -H)
      .attr("fill", "transparent");

    // Defs
    const defs = gAll.append("defs");
    const glow = defs
      .append("filter")
      .attr("id", "gl")
      .attr("x", "-100%")
      .attr("y", "-100%")
      .attr("width", "300%")
      .attr("height", "300%");
    glow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "8").attr("result", "b");
    const merge = glow.append("feMerge");
    merge.append("feMergeNode").attr("in", "b");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    // Radial gradients
    nodes.forEach((n, i) => {
      const col = CAT_CONFIG[n.cat].color;
      const a = Math.min(n.score / 10, 1);
      const gr = defs.append("radialGradient").attr("id", `rg${i}`);
      gr.append("stop").attr("offset", "0%").attr("stop-color", col).attr("stop-opacity", 0.6 + a * 0.35);
      gr.append("stop").attr("offset", "55%").attr("stop-color", col).attr("stop-opacity", 0.12 + a * 0.1);
      gr.append("stop").attr("offset", "100%").attr("stop-color", col).attr("stop-opacity", 0.02);
    });

    // Stars
    for (let i = 0; i < 100; i++) {
      gAll
        .append("circle")
        .attr("cx", cx + (Math.random() - 0.5) * W * 2)
        .attr("cy", cy + (Math.random() - 0.5) * H * 2)
        .attr("r", Math.random() * 0.7 + 0.2)
        .attr("fill", `rgba(160,175,200,${Math.random() * 0.12 + 0.03})`);
    }

    // Simulation
    const sim = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<EventNode, GraphLink>(links)
          .id((d) => d.id)
          .distance(70)
          .strength(0.02),
      )
      .force(
        "charge",
        d3.forceManyBody().strength((d) => -150 - (d as EventNode).score * 15),
      )
      .force(
        "x",
        d3.forceX((d) => clusterCenters[(d as EventNode).cat]?.x ?? cx).strength(0.045),
      )
      .force(
        "y",
        d3.forceY((d) => clusterCenters[(d as EventNode).cat]?.y ?? cy).strength(0.045),
      )
      .force(
        "collision",
        d3
          .forceCollide()
          .radius((d) => (d as EventNode).r + 8)
          .strength(0.5),
      )
      .alphaDecay(0.008)
      .velocityDecay(0.35);

    // Links
    const linkSel = gAll
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(100,116,139,0.05)")
      .attr("stroke-width", 0.4);

    // Halos
    const haloSel = gAll
      .append("g")
      .selectAll("circle")
      .data(nodes.filter((n) => n.score >= 4))
      .join("circle")
      .attr("r", (d) => d.r * 3)
      .attr("fill", "none")
      .attr("stroke", (d) => CAT_CONFIG[d.cat].color)
      .attr("stroke-opacity", 0.03)
      .attr("stroke-width", (d) => d.score * 0.5)
      .attr("filter", "url(#gl)");

    // Cluster labels
    Object.entries(CAT_CONFIG).forEach(([k, v]) => {
      if (!nodes.some((n) => n.cat === k)) return;
      gAll
        .append("text")
        .attr("class", `cl-${k}`)
        .attr("text-anchor", "middle")
        .attr("fill", v.color)
        .attr("opacity", 0.1)
        .attr("font-size", "10px")
        .attr("font-weight", "600")
        .attr("letter-spacing", "0.2em")
        .text(v.label);
    });

    // Event nodes with drag
    const drag = d3
      .drag<SVGGElement, EventNode>()
      .on("start", (e, d) => {
        if (!e.active) sim.alphaTarget(0.06).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (e, d) => {
        d.fx = e.x;
        d.fy = e.y;
      })
      .on("end", (e, d) => {
        if (!e.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    const evSel = gAll
      .append("g")
      .selectAll<SVGGElement, EventNode>("g")
      .data(nodes)
      .join("g")
      .style("cursor", "pointer")
      .call(drag);

    evSel
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", (_d, i) => `url(#rg${i})`)
      .attr("filter", (d) => (d.score >= 3 ? "url(#gl)" : null));

    evSel
      .append("text")
      .attr("dy", (d) => -d.r - 6)
      .attr("text-anchor", "middle")
      .attr("fill", "#5a6a7e")
      .attr("font-size", "9px")
      .attr("font-weight", "500")
      .text((d) => d.id.replace(/-/g, " "));

    evSel
      .append("text")
      .attr("dy", 3.5)
      .attr("text-anchor", "middle")
      .attr("fill", (d) => CAT_CONFIG[d.cat].color)
      .attr("font-family", "'JetBrains Mono', monospace")
      .attr("font-size", "8.5px")
      .attr("font-weight", "600")
      .text((d) => d.score.toFixed(1));

    // Interactions
    evSel
      .on("mouseenter", (_e, d) => {
        const conn = new Set([d.id]);
        links.forEach((l) => {
          const s = typeof l.source === "object" ? (l.source as EventNode).id : l.source;
          const t = typeof l.target === "object" ? (l.target as EventNode).id : l.target;
          if (s === d.id) conn.add(t as string);
          if (t === d.id) conn.add(s as string);
        });
        evSel
          .transition()
          .duration(200)
          .style("opacity", (n: EventNode) => (conn.has(n.id) ? 1 : 0.07));
        linkSel.transition().duration(200).style("opacity", (l: GraphLink) => {
          const s = typeof l.source === "object" ? (l.source as EventNode).id : l.source;
          const t = typeof l.target === "object" ? (l.target as EventNode).id : l.target;
          return s === d.id || t === d.id ? 1 : 0.05;
        });
        haloSel
          .transition()
          .duration(200)
          .style("opacity", (n: EventNode) => (conn.has(n.id) ? 1 : 0.03));
      })
      .on("mouseleave", () => {
        evSel.transition().duration(350).style("opacity", 1);
        linkSel.transition().duration(350).style("opacity", 1);
        haloSel.transition().duration(350).style("opacity", 1);
      });

    evSel.on("click", (_e, d) => setSelectedEvent(d));

    evSel.on("dblclick", (_e, d) => {
      svg
        .transition()
        .duration(750)
        .call(
          zoom.transform,
          d3.zoomIdentity
            .translate(W / 2, H / 2)
            .scale(2.5)
            .translate(-(d.x ?? 0), -(d.y ?? 0)),
        );
    });

    svg.on("dblclick.zoom", null);
    svg.on("dblclick", () => {
      svg
        .transition()
        .duration(750)
        .call(zoom.transform, d3.zoomIdentity.scale(0.9).translate(W * 0.05, H * 0.05));
    });

    // Tick
    sim.on("tick", () => {
      linkSel
        .attr("x1", (d: GraphLink) => (d.source as EventNode).x ?? 0)
        .attr("y1", (d: GraphLink) => (d.source as EventNode).y ?? 0)
        .attr("x2", (d: GraphLink) => (d.target as EventNode).x ?? 0)
        .attr("y2", (d: GraphLink) => (d.target as EventNode).y ?? 0);
      evSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
      haloSel.attr("cx", (d: EventNode) => d.x ?? 0).attr("cy", (d: EventNode) => d.y ?? 0);

      // Update cluster labels
      Object.keys(CAT_CONFIG).forEach((k) => {
        const catNodes = nodes.filter((n) => n.cat === k);
        if (!catNodes.length) return;
        const ax = catNodes.reduce((s, n) => s + (n.x ?? 0), 0) / catNodes.length;
        const ay = catNodes.reduce((s, n) => s + (n.y ?? 0), 0) / catNodes.length - 60;
        gAll.select(`.cl-${k}`).attr("x", ax).attr("y", ay);
      });
    });

    return () => {
      sim.stop();
    };
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] gap-3">
        <div className="relative w-12 h-12">
          <div className="absolute inset-0 rounded-full border-2 border-brand-500/20 animate-ping" />
          <div className="absolute inset-2 rounded-full border border-brand-500/40 animate-pulse" />
        </div>
        <p className="text-xs text-slate-500 font-mono">Loading signals...</p>
      </div>
    );
  }

  if (!data || data.filter((e) => e.source_count >= 2).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] gap-4">
        <div className="w-16 h-16 rounded-full bg-slate-800/50 flex items-center justify-center">
          <span className="text-2xl">🔭</span>
        </div>
        <h2 className="text-lg font-semibold text-slate-300">No cross-source signals yet</h2>
        <p className="text-sm text-slate-500 text-center max-w-md">
          Signals appear when the same event is reported by 2+ independent sources.
          Check back in a few hours as collectors gather more data.
        </p>
        <Link to="/" className="text-sm text-brand-400 hover:text-brand-300 mt-2">
          Browse all articles →
        </Link>
      </div>
    );
  }

  return (
    <div className="relative" style={{ height: "calc(100vh - 80px)" }}>
      {/* Headline — #1 signal */}
      {data && data.filter((e) => e.source_count >= 2).length > 0 && (() => {
        const top = data.filter((e) => e.source_count >= 2).sort((a, b) => b.signal_score - a.signal_score)[0];
        const cat = categorize(top.narrative_tag);
        return (
          <div className="absolute top-0 left-0 right-0 z-10 bg-slate-950/60 backdrop-blur-sm border-b border-surface-border px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: CAT_CONFIG[cat].color }} />
              <span className="text-sm text-slate-300">
                <span className="font-semibold text-slate-100">{top.narrative_tag.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
                <span className="text-slate-500 mx-2">&middot;</span>
                <span className="font-mono text-xs" style={{ color: CAT_CONFIG[cat].color }}>Signal {top.signal_score.toFixed(1)}</span>
                <span className="text-slate-500 mx-2">&middot;</span>
                <span className="text-slate-500 text-xs">{top.source_count} sources</span>
              </span>
            </div>
            <span className="text-[10px] text-slate-600 font-mono">{new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
          </div>
        );
      })()}

      {/* HUD */}
      <div className="absolute left-4 top-14 z-10">
        <h1 className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
          Signal Constellation
        </h1>
        <p className="text-[10px] text-slate-600 font-mono mt-1">
          {data?.filter((e) => e.source_count >= 2).length ?? 0} events · scroll zoom · drag pan ·
          click detail
        </p>
      </div>

      {/* Legend */}
      <div className="absolute left-4 bottom-4 z-10 flex gap-4 text-[9px] text-slate-600">
        {Object.entries(CAT_CONFIG).map(([k, v]) => (
          <div key={k} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: v.color, opacity: 0.6 }}
            />
            <span>{v.label}</span>
          </div>
        ))}
      </div>

      {/* SVG */}
      <svg ref={svgRef} className="w-full h-full" />

      {/* Detail panel — slide-in transition */}
      <div className={`absolute right-0 top-0 w-[380px] h-full bg-slate-900/95 backdrop-blur-xl border-l border-surface-border z-20 overflow-y-auto transition-transform duration-300 ease-out ${selectedEvent ? "translate-x-0" : "translate-x-full"}`}>
        <div className="p-6">
          {selectedEvent && (
            <>
              <button
                onClick={() => setSelectedEvent(null)}
                className="absolute top-4 right-4 w-8 h-8 bg-slate-800/50 border border-surface-border rounded-lg text-slate-500 hover:text-slate-200 flex items-center justify-center"
              >
                &times;
              </button>
              <h2 className="text-lg font-semibold text-slate-100 capitalize pr-10">
                {selectedEvent.id.replace(/-/g, " ")}
              </h2>
              <div
                className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg"
                style={{
                  background: `${CAT_CONFIG[selectedEvent.cat].color}10`,
                  border: `1px solid ${CAT_CONFIG[selectedEvent.cat].color}22`,
                }}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: CAT_CONFIG[selectedEvent.cat].color }}
                />
                <span
                  className="font-mono text-xs"
                  style={{ color: CAT_CONFIG[selectedEvent.cat].color }}
                >
                  Signal {selectedEvent.score.toFixed(1)} · {selectedEvent.sourceCount} sources
                </span>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {selectedEvent.sources.map((s) => (
                  <span
                    key={s}
                    className="bg-blue-500/10 text-blue-400 border border-blue-500/15 text-[10px] px-2 py-0.5 rounded"
                  >
                    {s}
                  </span>
                ))}
              </div>

              {/* Narrative summary */}
              {eventDetail?.event.narrative_summary && (
                <p className="mt-4 text-sm text-slate-300 leading-relaxed">
                  {eventDetail.event.narrative_summary}
                </p>
              )}

              {/* Trading play — bull/bear probability */}
              {tradingPlay && (
                <div className="mt-4">
                  <p className="text-[9px] text-slate-500 uppercase tracking-wider mb-2">Scenario Analysis</p>

                  {/* Probability bar */}
                  <div className="flex h-2 rounded-full overflow-hidden mb-3">
                    <div className="bg-green-500/60" style={{ width: `${tradingPlay.bullPct}%` }} />
                    <div className="bg-red-500/60" style={{ width: `${tradingPlay.bearPct}%` }} />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    {/* Bull */}
                    <div className="bg-green-500/5 border border-green-500/10 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-green-400 text-xs font-semibold">BULL</span>
                        <span className="text-green-400/70 text-xs font-mono">{tradingPlay.bullPct}%</span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">{tradingPlay.bullText}</p>
                    </div>
                    {/* Bear */}
                    <div className="bg-red-500/5 border border-red-500/10 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-red-400 text-xs font-semibold">BEAR</span>
                        <span className="text-red-400/70 text-xs font-mono">{tradingPlay.bearPct}%</span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">{tradingPlay.bearText}</p>
                    </div>
                  </div>

                  <p className="text-[9px] text-slate-600 mt-2">AI-generated analysis. Not financial advice.</p>
                </div>
              )}

              {/* Price impacts */}
              {eventDetail?.price_impacts && eventDetail.price_impacts.length > 0 && (
                <div className="mt-4">
                  <p className="text-[9px] text-slate-500 uppercase tracking-wider mb-2">Price Impact</p>
                  <div className="flex gap-4">
                    {eventDetail.price_impacts.map((pi) => (
                      <div key={pi.ticker} className="font-mono text-xs">
                        <span className="text-slate-500">${pi.ticker} </span>
                        <span className={pi.change_1d >= 0 ? "text-green-400" : "text-red-400"}>
                          {pi.change_1d >= 0 ? "+" : ""}{pi.change_1d.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <Link
                to={`/events/${selectedEvent.eventId}`}
                className="mt-6 block text-center text-sm bg-brand-500/10 text-brand-400 border border-brand-500/20 rounded-lg py-2 hover:bg-brand-500/20 transition-colors"
              >
                View Full Detail →
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
