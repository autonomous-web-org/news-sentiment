/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }
type Counts = { neutral: number; positive: number; negative: number };
type YearRow = { year: string; score: 0 | 1 | 2 };
type StackDatum = { year: Date } & Counts;

export function SentimentStackedBar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const parseDay = d3.timeParse('%Y-%m-%d')!;
    const fmtYear = d3.timeFormat('%Y');
    const parseYear = d3.timeParse('%Y')!;

    // Normalize into year rows, guard invalid dates
    const yearRows: YearRow[] = data
      .map(d => {
        const dt = parseDay(d.date);
        if (!dt) return null;
        return { year: fmtYear(dt), score: d.score as 0 | 1 | 2 };
      })
      .filter((d): d is YearRow => !!d);

    // Aggregate counts by year
    const rollup = d3.rollup<YearRow, Counts, [string]>(
      yearRows,
      (values) => ({
        neutral: values.filter(v => v.score === 0).length,
        positive: values.filter(v => v.score === 1).length,
        negative: values.filter(v => v.score === 2).length,
      }),
      v => v.year
    );

    // Build dataset of { year: Date, neutral, positive, negative }
    const dataset: StackDatum[] = Array.from(rollup, ([year, counts]) => ({
      year: parseYear(year)!,
      ...counts,
    }))
      .filter(d => d.year instanceof Date && !isNaN(d.year.getTime()))
      .sort((a, b) => a.year.getTime() - b.year.getTime());

    const margin = { top: 20, right: 30, bottom: 50, left: 50 };
    const width = 600 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr(
      'viewBox',
      `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`
    );

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const keys = ['neutral', 'positive', 'negative'] as const;

    const color = d3.scaleOrdinal<string, string>()
      .domain(keys as unknown as string[])
      .range(isDark ? ['#64748b', '#10b981', '#f43f5e'] : ['#64748b', '#10b981', '#f43f5e']);

    const x = d3.scaleBand<Date>()
      .domain(dataset.map(d => d.year))
      .range([0, width])
      .padding(0.1);

    const yMax = d3.max(dataset, d => d.neutral + d.positive + d.negative) ?? 0;

    const y = d3.scaleLinear()
      .domain([0, yMax])
      .nice()
      .range([height, 0]);

    // Stack generator typed with StackDatum
    const stackGen = d3.stack<StackDatum>()
      .keys(keys as unknown as ReadonlyArray<keyof Counts>);

    const series = stackGen(dataset);

    // Axes
    const xAxis = d3.axisBottom<Date>(x)
      .tickFormat(d3.timeFormat('%Y') as unknown as (d: Date) => string);

    const yAxis = d3.axisLeft(y).ticks(5);

    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(xAxis as any)
      .selectAll('text')
      .style('fill', isDark ? '#e2e8f0' : '#334155');

    g.append('g')
      .call(yAxis)
      .selectAll('text')
      .style('fill', isDark ? '#e2e8f0' : '#334155');

    // Bars (no per-rect <title> here)
    const layers = g.selectAll('g.layer')
      .data(series)
      .join('g')
      .attr('class', 'layer')
      .attr('fill', d => color(d.key as string)!);

    layers.selectAll('rect')
      .data(d => d)
      .join('rect')
      .attr('x', d => x(d.data.year)!)
      .attr('y', d => y(d[1]))
      .attr('height', d => Math.max(0, y(d[0]) - y(d[1])))
      .attr('width', x.bandwidth());

    // One overlay per year with a single combined <title>
    const hover = g.append('g').attr('class', 'hover-overlays');

    hover.selectAll('rect.overlay')
      .data(dataset)
      .join('rect')
      .attr('class', 'overlay')
      .attr('x', d => x(d.year)!)
      .attr('y', 0)
      .attr('width', x.bandwidth())
      .attr('height', height)
      .attr('fill', 'transparent')        // keep painted for pointer-events
      .style('pointer-events', 'all')     // ensure hover works across the full column
      .append('title')
      .text(d => {
        const total = d.neutral + d.positive + d.negative;
        return `${fmtYear(d.year)}
Neutral: ${d.neutral}
Positive: ${d.positive}
Negative: ${d.negative}
Total: ${total}`;
      });
  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
