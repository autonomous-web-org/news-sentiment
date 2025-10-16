/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';

import { YearPicker } from '../year_picker';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }
type Counts = { neutral: number; positive: number; negative: number };

export function SentimentCalendar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  const parse = useMemo(() => d3.timeParse('%Y-%m-%d')!, []);
  const fmtDay = useMemo(() => d3.timeFormat('%Y-%m-%d'), []);
  const pretty = useMemo(() => d3.timeFormat('%b %d, %Y'), []);

  const dates = useMemo(() => (
    data
      .map(d => parse(d.date))
      .filter((d): d is Date => d instanceof Date && !isNaN(d.getTime()))
  ), [data, parse]);

  const years = useMemo(() => {
    const ys = Array.from(new Set(dates.map(d => d.getFullYear()))).sort((a, b) => a - b);
    return ys.length ? ys : [new Date().getFullYear()];
  }, [dates]);

  const minYear = years[0];
  const maxYear = years[years.length - 1];
  const [selectedYear, setSelectedYear] = useState<number>(maxYear);

  useEffect(() => {
    if (selectedYear < minYear || selectedYear > maxYear) setSelectedYear(maxYear);
  }, [minYear, maxYear, selectedYear]);

  const counts = useMemo(() => (
    d3.rollup<SentimentRow, Counts, [string]>(
      data,
      (values) => ({
        neutral: values.filter(d => d.score === 0).length,
        positive: values.filter(d => d.score === 1).length,
        negative: values.filter(d => d.score === 2).length,
      }),
      (d) => d.date
    )
  ), [data]);

  useEffect(() => {
    if (!ref.current) return;

    const cellSize = 15;
    const width = 53 * cellSize;
    const height = 7 * cellSize;

    const yearStart = new Date(selectedYear, 0, 1);
    const yearEnd = new Date(selectedYear, 11, 31);
    const allDays = d3.timeDays(yearStart, d3.timeDay.offset(yearEnd, 1));

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width + 20} ${height + 20}`);

    const g = svg.append('g').attr('transform', 'translate(10,10)');

    const colorScale = d3.scaleOrdinal<string, string>()
      .domain(['neutral', 'positive', 'negative'])
      .range(isDark ? ['#475569', '#059669', '#be123c'] : ['#cbd5e1', '#10b981', '#f43f5e']);

    const dayType = new Map<string, 'neutral' | 'positive' | 'negative'>();
    for (const d of allDays) {
      const key = fmtDay(d);
      const c = counts.get(key);
      if (!c) { dayType.set(key, 'neutral'); continue; }
      const max = Math.max(c.neutral, c.positive, c.negative);
      const type = max === c.positive ? 'positive' : max === c.negative ? 'negative' : 'neutral';
      dayType.set(key, type);
    }

    const rects = g.selectAll('rect')
      .data(allDays)
      .enter()
      .append('rect')
      .attr('width', cellSize - 1)
      .attr('height', cellSize - 1)
      .attr('x', (d: Date) => d3.timeWeek.count(d3.timeYear(d), d) * cellSize)
      .attr('y', (d: Date) => d.getDay() * cellSize)
      .attr('fill', (d: Date) => colorScale(dayType.get(fmtDay(d))!));

    rects.append('title').text((d: Date) => {
      const key = fmtDay(d);
      const c = counts.get(key) ?? { positive: 0, negative: 0, neutral: 0 };
      const sentiment = dayType.get(key) ?? 'neutral';
      return `${pretty(d)} — ${sentiment} (pos:${c.positive}, neg:${c.negative}, neu:${c.neutral})`;
    });
  }, [counts, fmtDay, isDark, pretty, selectedYear]);

  return (
    <div className="w-full">
      <div className="flex items-center gap-2 mb-3">
        <YearPicker
          value={selectedYear}
          min={minYear}
          max={maxYear}
          onChange={setSelectedYear}
          order="desc"
          className="flex-0"
        />
      </div>
      <svg ref={ref} className="w-full h-auto" />
    </div>
  );
}