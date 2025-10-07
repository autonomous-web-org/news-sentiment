import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { type SentimentRow } from '../../_state_hooks/useNSSStore';

interface Props { data: SentimentRow[]; isDark: boolean; }

export function SentimentCalendar({ data, isDark }: Props) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const parse = d3.timeParse('%Y-%m-%d');
    // Count per date
    const counts = d3.rollup(
      data,
      v => ({
        neutral: v.filter(d=>d.score===0).length,
        positive: v.filter(d=>d.score===1).length,
        negative: v.filter(d=>d.score===2).length
      }),
      d=>d.date
    );
    // Prepare date range
    const dates = data.map(d=>parse(d.date)!);
    const [minDate, maxDate] = d3.extent(dates)!;
    const dayCount = d3.timeDay.count(minDate, maxDate) + 1;
    const allDays = d3.timeDays(minDate, d3.timeDay.offset(maxDate,1));

    const cellSize = 15;
    const width = 53 * cellSize;
    const height = 7 * cellSize;

    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width+20} ${height+20}`);

    const g = svg.append('g').attr('transform','translate(10,10)');

    const colorScale = d3.scaleOrdinal<string>()
      .domain(['neutral','positive','negative'])
      .range(isDark
        ? ['#475569','#059669','#be123c']
        : ['#cbd5e1','#10b981','#f43f5e']
      );

    // Map day to sentiment type by majority
    const dayType = new Map<string,string>();
    allDays.forEach(d => {
      const key = d3.timeFormat('%Y-%m-%d')(d);
      const c = counts.get(key);
      if (!c) return dayType.set(key,'neutral');
      const max = Math.max(c.neutral,c.positive,c.negative);
      const type = max===c.positive?'positive':max===c.negative?'negative':'neutral';
      dayType.set(key,type);
    });

    // Cells
    g.selectAll('rect')
      .data(allDays)
      .enter()
      .append('rect')
      .attr('width', cellSize-1)
      .attr('height', cellSize-1)
      .attr('x', d => d3.timeWeek.count(d3.timeYear(d), d) * cellSize)
      .attr('y', d => d.getDay() * cellSize)
      .attr('fill', d => colorScale(dayType.get(d3.timeFormat('%Y-%m-%d')(d))!));

  }, [data, isDark]);

  return <svg ref={ref} className="w-full h-auto" />;
}
