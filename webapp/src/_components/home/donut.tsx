/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props {
  data: SentimentRow[];
  isDark: boolean;
  fillContainer?: boolean; // optional: fill non-square parents
}

export function SentimentDonut({ data, isDark, fillContainer = false }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    // Tally
    const counts = { neutral: 0, positive: 0, negative: 0 };
    data.forEach(d => {
      counts[d.score === 1 ? 'positive' : d.score === 2 ? 'negative' : 'neutral']++;
    });
    const total = data.length;

    const dataset = [
      { key: 'Neutral',  value: counts.neutral,  color: '#64748b' },
      { key: 'Positive', value: counts.positive, color: '#10b981' },
      { key: 'Negative', value: counts.negative, color: '#f43f5e' },
    ];

    // Geometry
    const OUTER = 60;
    const INNER = 25;
    const STROKE = 2;
    const PAD = 6;
    const size = 1 * OUTER + 2 * PAD + STROKE;

    const pie = d3.pie<any>()
      .value((d: { value: number }) => d.value)
      .sort(null);

    const arc = d3.arc<any>() // d3 arc generator for donut segments
      .innerRadius(INNER)
      .outerRadius(OUTER);

    // Render
    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();

    svg
      .attr('viewBox', `0 0 ${size} ${size}`)
      .attr('preserveAspectRatio', fillContainer ? 'xMidYMid slice' : 'xMidYMid meet');

    const g = svg.append('g').attr('transform', `translate(${size / 2}, ${size / 2})`);

    const paths = g.selectAll('path')
      .data(pie(dataset))
      .enter()
      .append('path')
      .attr('d', arc as any)
      .attr('fill', (d: any) => d.data.color)
      .attr('stroke', isDark ? '#1e293b' : '#ffffff')
      .attr('stroke-width', STROKE);

    // Native tooltip fallback
    paths.append('title').text((d: any) => {
      const pct = total ? Math.round((d.data.value / total) * 100) : 0;
      return `${d.data.key}: ${d.data.value} (${pct}%)`;
    });

    // Center label
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .style('fill', isDark ? '#10b981' : '#10b981')
      .style('font-size', '6px')
      .text(total > 0 ? `${Math.round((counts.positive / total) * 100)}% Positive` : '0% Positive');

  }, [data, isDark, fillContainer]);

  return <svg ref={ref} className="w-full" style={{ aspectRatio: '1 / 1', display: 'block' }} />;
}
