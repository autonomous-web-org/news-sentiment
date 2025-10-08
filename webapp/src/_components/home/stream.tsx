/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }

type Counts = { neutral: number; positive: number; negative: number };
type DailyRow = { date: Date; score: 0 | 1 | 2 };
type StreamDatum = { date: Date } & Counts;

export function SentimentStream({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    const parseDay = d3.timeParse('%Y-%m-%d')!;

    // Normalize rows (filter out invalid dates)
    const rows: DailyRow[] = data
      .map(d => {
        const dt = parseDay(d.date);
        if (!dt) return null;
        return { date: dt, score: d.score as 0 | 1 | 2 };
      })
      .filter((d): d is DailyRow => !!d);

    // Aggregate daily counts with a typed reducer
    const roll = d3.rollup<DailyRow, Counts, [Date]>(
      rows,
      (values) => {
        let neutral = 0, positive = 0, negative = 0;
        for (const v of values) {
          if (v.score === 0) neutral++;
          else if (v.score === 1) positive++;
          else if (v.score === 2) negative++;
        }
        return { neutral, positive, negative };
      },
      v => v.date
    );

    const dataset: StreamDatum[] = Array.from(roll, ([date, counts]) => ({ date, ...counts }))
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    const keys = ['neutral', 'positive', 'negative'] as const;

    const margin = { top: 20, right: 30, bottom: 30, left: 50 };
    const width = 600 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const x = d3.scaleTime()
      .domain(d3.extent(dataset, d => d.date) as [Date, Date])
      .range([0, width]);

    // Stack generator typed to StreamDatum
    const stack = d3.stack<StreamDatum>()
      .keys(keys as unknown as ReadonlyArray<keyof Counts>)
      .offset(d3.stackOffsetWiggle);

    const series = stack(dataset);

    // Compute y domain from stacked series
    const y = d3.scaleLinear()
      .domain([
        d3.min(series, s => d3.min(s, d => d[0])) ?? 0,
        d3.max(series, s => d3.max(s, d => d[1])) ?? 0
      ])
      .range([height, 0]);

    const color = d3.scaleOrdinal<string, string>()
      .domain(keys as unknown as string[])
      .range(isDark ? ['#475569', '#059669', '#be123c'] : ['#cbd5e1', '#10b981', '#f43f5e']);

    // Area generator typed to series point
    const area = d3.area<d3.SeriesPoint<StreamDatum>>()
      .x(d => x(d.data.date))
      .y0(d => y(d[0]))
      .y1(d => y(d[1]))
      .curve(d3.curveBasis);

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`);
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    g.selectAll('path')
      .data(series)
      .enter()
      .append('path')
      .attr('d', d => area(d)!)
      .attr('fill', d => color(d.key as string)!)
      .attr('stroke', 'none');
  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
