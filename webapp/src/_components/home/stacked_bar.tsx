/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }
type Counts = { neutral: number; positive: number; negative: number };
type MonthRow = { month: string; score: 0 | 1 | 2 };
type StackDatum = { month: Date } & Counts;

export function SentimentStackedBar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const parseDay = d3.timeParse('%Y-%m-%d')!;
    const fmtMonth = d3.timeFormat('%Y-%m');
    const parseMonth = d3.timeParse('%Y-%m')!;

    // Normalize into month rows, guard invalid dates
    const monthRows: MonthRow[] = data
      .map(d => {
        const dt = parseDay(d.date);
        if (!dt) return null;
        return { month: fmtMonth(dt), score: d.score as 0 | 1 | 2 };
      })
      .filter((d): d is MonthRow => !!d);

    // Aggregate counts by month (typed reducer receives MonthRow[])
    const rollup = d3.rollup<MonthRow, Counts, [string]>(
      monthRows,
      (values) => ({
        neutral: values.filter(v => v.score === 0).length,
        positive: values.filter(v => v.score === 1).length,
        negative: values.filter(v => v.score === 2).length,
      }),
      v => v.month
    );

    // Build dataset of { month: Date, neutral, positive, negative }
    const dataset: StackDatum[] = Array.from(rollup, ([month, counts]) => ({
      month: parseMonth(month)!,
      ...counts,
    }))
      .filter(d => d.month instanceof Date && !isNaN(d.month.getTime()))
      .sort((a, b) => a.month.getTime() - b.month.getTime());

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
      .domain(dataset.map(d => d.month))
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
      .tickFormat(d3.timeFormat('%b %y') as unknown as (d: Date) => string);

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

    // Bars
    g.selectAll('g.layer')
      .data(series)
      .join('g')
      .attr('class', 'layer')
      .attr('fill', d => color(d.key as string)!)
      .selectAll('rect')
      .data(d => d)
      .join('rect')
      .attr('x', d => x(d.data.month)!)
      .attr('y', d => y(d[1]))
      .attr('height', d => Math.max(0, y(d[0]) - y(d[1])))
      .attr('width', x.bandwidth());

  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
