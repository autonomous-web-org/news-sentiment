import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }

export function SentimentStream({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const parse = d3.timeParse('%Y-%m-%d');
    // Aggregate daily counts by score
    const roll = d3.rollup(
      data.map(d=>({ date: parse(d.date)!, score: d.score })),
      v=>({
        neutral:v.filter(d=>d.score===0).length,
        positive:v.filter(d=>d.score===1).length,
        negative:v.filter(d=>d.score===2).length
      }),
      d=>d.date
    );
    const dataset = Array.from(roll, ([date,counts])=>({ date, ...counts }));
    dataset.sort((a,b)=>a.date.getTime()-b.date.getTime());

    const keys=['neutral','positive','negative'];
    const stack = d3.stack<any>().keys(keys).offset(d3.stackOffsetWiggle);
    const series = stack(dataset as any);

    const margin={top:20,right:30,bottom:30,left:50};
    const width=600-margin.left-margin.right;
    const height=300-margin.top-margin.bottom;

    const x = d3.scaleTime()
      .domain(d3.extent(dataset,d=>d.date) as [Date,Date])
      .range([0,width]);
    const y = d3.scaleLinear()
      .domain([
        d3.min(series, s=>d3.min(s,d=>d[0]))!,
        d3.max(series, s=>d3.max(s,d=>d[1]))!
      ])
      .range([height,0]);

    const color = d3.scaleOrdinal<string>()
      .domain(keys)
      .range(isDark?['#475569','#059669','#be123c']:['#cbd5e1','#10b981','#f43f5e']);

    const area = d3.area<any>()
      .x(d=>x(d.data.date))
      .y0(d=>y(d[0]))
      .y1(d=>y(d[1]))
      .curve(d3.curveBasis);

    const svg=d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox',`0 0 ${width+margin.left+margin.right} ${height+margin.top+margin.bottom}`);
    const g=svg.append('g').attr('transform',`translate(${margin.left},${margin.top})`);

    g.selectAll('path')
      .data(series)
      .enter().append('path')
      .attr('d',area)
      .attr('fill',d=>color(d.key)!)
      .attr('stroke','none');
  },[data,isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
