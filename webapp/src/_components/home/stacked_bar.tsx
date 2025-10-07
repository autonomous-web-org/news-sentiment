import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }

export function SentimentStackedBar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const parse = d3.timeParse('%Y-%m-%d');
    // Aggregate counts by month and score
    const rollup = d3.rollup(
      data.map(d => ({ month: d3.timeFormat('%Y-%m')(parse(d.date)!), score: d.score })),
      v => ({
        neutral: v.filter(d => d.score === 0).length,
        positive: v.filter(d => d.score === 1).length,
        negative: v.filter(d => d.score === 2).length,
      }),
      d => d.month
    );
    const dataset = Array.from(rollup, ([month, counts]) => ({ month: d3.timeParse('%Y-%m')(month)!, ...counts }));
    dataset.sort((a, b) => a.month.getTime() - b.month.getTime());

    const margin = { top: 20, right: 30, bottom: 50, left: 50 };
    const width = 600 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const keys = ['neutral','positive','negative'];
    const color = d3.scaleOrdinal<string>()
      .domain(keys)
      .range(isDark
        ? ['#64748b','#10b981','#f43f5e']
        : ['#64748b','#10b981','#f43f5e']
      );

    const x = d3.scaleBand<Date>()
      .domain(dataset.map(d => d.month))
      .range([0, width])
      .padding(0.1);

    const y = d3.scaleLinear()
      .domain([0, d3.max(dataset, d => d.neutral + d.positive + d.negative)!])
      .nice()
      .range([height, 0]);

    const stackGen = d3.stack<any>().keys(keys);
    const series = stackGen(dataset as any);

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x).tickFormat(d3.timeFormat('%b %y')))
      .selectAll('text')
      .style('fill', isDark ? '#e2e8f0' : '#334155');

    g.append('g')
      .call(d3.axisLeft(y).ticks(5))
      .selectAll('text')
      .style('fill', isDark ? '#e2e8f0' : '#334155');

    // Bars
    g.selectAll('g.layer')
      .data(series)
      .enter()
      .append('g')
      .attr('class','layer')
      .attr('fill', d => color(d.key)!)
      .selectAll('rect')
      .data(d => d)
      .enter()
      .append('rect')
      .attr('x', d => x(d.data.month)!)
      .attr('y', d => y(d[1]))
      .attr('height', d => y(d[0]) - y(d[1]))
      .attr('width', x.bandwidth());

  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
