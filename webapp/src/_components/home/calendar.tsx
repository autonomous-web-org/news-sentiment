/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }
type Counts = { neutral: number; positive: number; negative: number };

export function SentimentCalendar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const parse = d3.timeParse('%Y-%m-%d')!;
    const fmtDay = d3.timeFormat('%Y-%m-%d');

    // Count per date (typed reducer receives an array of rows)
    const counts = d3.rollup<SentimentRow, Counts, [string]>(
      data,
      (values) => ({
        neutral: values.filter(d => d.score === 0).length,
        positive: values.filter(d => d.score === 1).length,
        negative: values.filter(d => d.score === 2).length,
      }),
      (      d: { date: any; }) => d.date
    );

    // Prepare date range (guard nulls)
    const dates = data
      .map(d => parse(d.date))
      .filter((d): d is Date => d instanceof Date && !isNaN(d.getTime()));

    if (!dates.length) {
      const svg = d3.select(ref.current);
      svg.selectAll('*').remove();
      svg.attr('viewBox', `0 0 300 120`);
      svg
        .append('text')
        .attr('x', 150)
        .attr('y', 60)
        .attr('text-anchor', 'middle')
        .attr('fill', isDark ? '#e2e8f0' : '#334155')
        .text('No data');
      return;
    }

    const [minDate, maxDate] = d3.extent(dates) as [Date, Date];

    const allDays = d3.timeDays(minDate, d3.timeDay.offset(maxDate, 1));

    const cellSize = 15;
    const width = 53 * cellSize;
    const height = 7 * cellSize;

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width + 20} ${height + 20}`);

    const g = svg.append('g').attr('transform', 'translate(10,10)');

    const colorScale = d3.scaleOrdinal<string, string>()
      .domain(['neutral', 'positive', 'negative'])
      .range(isDark ? ['#475569', '#059669', '#be123c'] : ['#cbd5e1', '#10b981', '#f43f5e']);

    // Map day to sentiment type by majority
    const dayType = new Map<string, 'neutral' | 'positive' | 'negative'>();
    for (const d of allDays) {
      const key = fmtDay(d);
      const c = counts.get(key);
      if (!c) {
        dayType.set(key, 'neutral');
        continue;
      }
      const max = Math.max(c.neutral, c.positive, c.negative);
      const type = max === c.positive ? 'positive' : max === c.negative ? 'negative' : 'neutral';
      dayType.set(key, type);
    }

    // Cells
    g.selectAll('rect')
      .data(allDays)
      .enter()
      .append('rect')
      .attr('width', cellSize - 1)
      .attr('height', cellSize - 1)
      .attr('x', (d: Date) => d3.timeWeek.count(d3.timeYear(d), d) * cellSize)
      .attr('y', (d: Date) => d.getDay() * cellSize)
      .attr('fill', (d: Date) => colorScale(dayType.get(fmtDay(d))!));

  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
