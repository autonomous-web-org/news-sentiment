import { useMemo } from 'react';
import { twMerge } from 'tailwind-merge';

interface YearPickerProps {
  value: number;
  min: number;
  max: number;
  onChange: (year: number) => void;
  order?: 'asc' | 'desc'; // default asc
  className?: string;
}

export function YearPicker({
  value,
  min,
  max,
  onChange,
  order = 'asc',
  className
}: YearPickerProps) {
  const years = useMemo(() => {
    const start = Math.min(min, max);
    const end = Math.max(min, max);
    const arr = [];
    for (let y = start; y <= end; y++) arr.push(y);
    return order === 'desc' ? arr.reverse() : arr;
  }, [min, max, order]);

//   const canPrev = value > Math.min(min, max);
//   const canNext = value < Math.max(min, max);

  return (
    <div className={twMerge("flex items-center gap-2", className)}>
        {/* <button
          type="button"
          aria-label="Previous year"
          onClick={() => canPrev && onChange(value - 1)}
          disabled={!canPrev}
          className="border rounded px-2 py-1"
        >
          ‹
        </button> */}

        <label htmlFor="yearSelect" className="text-sm">Year</label>
        <select
          id="yearSelect"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="border rounded px-2 py-1"
          aria-label="Select year"
        >
          {years.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
{/* 
        <button
          type="button"
          aria-label="Next year"
          onClick={() => canNext && onChange(value + 1)}
          disabled={!canNext}
          className="border rounded px-2 py-1"
        >
          ›
        </button> */}
    </div>
  );
}
