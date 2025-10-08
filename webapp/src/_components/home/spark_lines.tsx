/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { datasets: Record<string,SentimentRow[]>; isDark: boolean; }

export function SentimentSparklines({ datasets, isDark }: Props) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {Object.entries(datasets).map(([key, data]) => (
        <Sparkline key={key} data={data} label={key} isDark={isDark} />
      ))}
    </div>
  );
}

function Sparkline({ data, label, isDark }: { data: SentimentRow[]; label: string; isDark: boolean; }) {
  const ref = React.useRef<SVGSVGElement>(null);

  React.useEffect(() => {
    if (!ref.current) return;
    const parse = d3.timeParse('%Y-%m-%d');
    const pd = data.map(d=>({ date: parse(d.date)!, score: d.score }));

    const width=200, height=40;//margin={left:0,top:0,right:0,bottom:0};
    const x = d3.scaleTime()
      .domain(d3.extent(pd,(d: { date: any; })=>d.date) as [Date,Date])
      .range([0,width]);
    const y = d3.scaleLinear()
      .domain([0,2]).range([height,0]);

    const line = d3.line<any>().x((d: { date: any; })=>x(d.date)).y((d: { score: any; })=>y(d.score));

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox',`0 0 ${width} ${height}`);

    svg.append('path')
      .datum(pd)
      .attr('fill','none')
      .attr('stroke', isDark?'#fff':'#000')
      .attr('stroke-width',1)
      .attr('d',line);

    svg.append('text')
      .attr('x',2).attr('y',10)
      .attr('fill', isDark?'#e2e8f0':'#334155')
      .attr('font-size', '10px')
      .text(label);
  },[data,isDark]);

  return <svg ref={ref} className="w-full h-10" />;
}
