/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }

export function SentimentDonut({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const counts = { neutral:0,positive:0,negative:0 };
    data.forEach(d=>counts[d.score===1?'positive':d.score===2?'negative':'neutral']++);
    const total = data.length;
    const dataset = [
      { label:'Neutral',value:counts.neutral,color:isDark?'#64748b':'#64748b' },
      { label:'Positive',value:counts.positive,color:'#10b981' },
      { label:'Negative',value:counts.negative,color:'#f43f5e' }
    ];

    const pie = d3.pie<any>().value((d: { value: any; })=>d.value).sort(null);
    const arc = d3.arc<any>().innerRadius(70).outerRadius(100);

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox','0 0 200 200');
    const g = svg.append('g').attr('transform','translate(100,100)');

    g.selectAll('path')
      .data(pie(dataset))
      .enter().append('path')
      .attr('d',arc as any)
      .attr('fill',(d: { data: { color: any; }; })=>d.data.color)
      .attr('stroke',isDark?'#1e293b':'#ffffff')
      .attr('stroke-width',2);

    g.append('text')
      .attr('text-anchor','middle')
      .attr('dy','0.3em')
      .style('fill',isDark?'#e2e8f0':'#334155')
      .style('font-size','14px')
      .text(`${Math.round((counts.positive/total)*100)}% Positive`);
  },[data,isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
