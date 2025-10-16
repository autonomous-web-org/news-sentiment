/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props {
  datasets: Record<string, SentimentRow[]>;
  isDark: boolean;
}

export function SentimentSparklines({ datasets, isDark }: Props) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {Object.entries(datasets).map(([key, data]) => (
        <Sparkline key={key} data={data} label={key} isDark={isDark} />
      ))}
    </div>
  );
}

function useResizeObserver<T extends HTMLElement>() {
  const ref = React.useRef<T | null>(null);
  const [size, setSize] = React.useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });

  React.useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      const e = entries[0];
      if (!e) return;
      const { inlineSize: width, blockSize: height } =
        (e as any).borderBoxSize?.[0] ?? e.contentRect;
      setSize({ width, height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  return { ref, size };
}

function Sparkline({
  data,
  label,
  isDark,
}: {
  data: SentimentRow[];
  label: string;
  isDark: boolean;
}) {
  const { ref, size } = useResizeObserver<HTMLDivElement>();
  const svgRef = React.useRef<SVGSVGElement>(null);

  // Parse, clean, dedupe, and sort once per data change
  const processed = React.useMemo(() => {
    const parse = d3.utcParse('%Y-%m-%d'); // robust to TZ
    // Map and filter invalid rows
    const mapped = data
      .map((d) => ({ date: parse(d.date), score: +d.score }))
      .filter((d): d is { date: Date; score: number } => !!d.date && Number.isFinite(d.score));

    // Deduplicate by day (keep last occurrence)
    const byDay = new Map<string, { date: Date; score: number }>();
    for (const d of mapped) {
      byDay.set(d3.utcFormat('%Y-%m-%d')(d.date), d);
    }

    // Sort ascending by date
    const arr = Array.from(byDay.values()).sort((a, b) => +a.date - +b.date);
    return arr;
  }, [data]);

  React.useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 6, right: 2, bottom: 4, left: 42 }; // left space for label
    const width = Math.max(120, (size.width || 200));
    const height = 40;

    svg.attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    if (processed.length < 2 || innerW <= 0 || innerH <= 0) {
      // Still show label even if no line
      svg
        .append('text')
        .attr('x', 2)
        .attr('y', 12)
        .attr('fill', isDark ? '#e2e8f0' : '#334155')
        .attr('font-size', 10)
        .text(label);
      return;
    }

    const x = d3
      .scaleUtc()
      .domain(d3.extent(processed, (d) => d.date) as [Date, Date])
      .range([0, innerW]);

    const [yMin, yMax] = d3.extent(processed, (d) => d.score) as [number, number];
    const pad = yMin === yMax ? Math.max(0.5, Math.abs(yMax) || 1) : 0;
    const y = d3
      .scaleLinear()
      .domain([yMin - pad, yMax + pad])
      .range([innerH, 0]);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const line = d3
      .line<{ date: Date; score: number }>()
      .defined((d) => Number.isFinite(d.score))
      .x((d) => x(d.date))
      .y((d) => y(d.score))
      .curve(d3.curveMonotoneX);

    g.append('path')
      .attr('fill', 'none')
      .attr('stroke', isDark ? '#ffffff' : '#0f172a')
      .attr('stroke-width', 1.25)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')
      .attr('d', line(processed) ?? '');

    // Last value dot
    const last = processed[processed.length - 1];
    g.append('circle')
      .attr('cx', x(last.date))
      .attr('cy', y(last.score))
      .attr('r', 1.8)
      .attr('fill', isDark ? '#94a3b8' : '#1e293b');

    // Label in left margin
    svg
      .append('text')
      .attr('x', 2)
      .attr('y', 12)
      .attr('fill', isDark ? '#e2e8f0' : '#334155')
      .attr('font-size', 10)
      .text(label);
  }, [processed, size.width, isDark, label]);

  return (
    <div ref={ref} className="w-full">
      <svg ref={svgRef} className="block" />
    </div>
  );
}
