import { useEffect, useState, useCallback } from 'react';
import { twMerge } from 'tailwind-merge';

import { SentimentStackedBar } from './stacked_bar';
import { SentimentCalendar } from './calendar';
import { SentimentDonut } from './donut';
// import { SentimentSparklines } from './spark_lines';
// import { SentimentStream } from './stream';
import { useNSSStore, type SentimentRow } from '../../_state_hooks/useNSSStore';

const EXCHANGES: string[] = import.meta.env.VITE_EXCHANGES.split(",").map((z: string) => z.toUpperCase());

export function NSSHeader() {
  const {
    exchange, ticker, data,
    setExchange, setTicker, setData, setStatus, setLoading
  } = useNSSStore();

  // Initialize theme
  useEffect(() => {
    const theme = localStorage.getItem('theme');
    if (theme) {
      document.documentElement.classList.toggle('dark', theme === 'dark');
    }
  }, []);

  const handleThemeToggle = () => {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  };

  const loadTicker = useCallback(async () => {
    if (!ticker || !exchange) {
      setStatus('Select an exchange and enter a ticker symbol to load data.');
      setData([]);
      return;
    }
    setLoading(true);
    setStatus(`Loading ${ticker.toUpperCase()}...`);

    try {
      const res = await fetch(
        `${import.meta.env.VITE_SERVER_ENDPOINT}/sentiment?exchange=${exchange.toLowerCase()}&ticker=${ticker.toLowerCase()}`,
        { headers: { Accept: 'text/plain' }, cache: 'no-cache' }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      const parsed: SentimentRow[] = text
        .split(/\r?\n/)
        .filter(Boolean)
        .map((ln) => {
          const [date, scoreStr] = ln.split('|');
          return { date: date.trim(), score: parseInt(scoreStr?.trim() || '', 10) };
        });
      setData(parsed);
      setStatus(`${ticker.toUpperCase()} loaded: ${parsed.length} rows.`);
    } catch {
      setStatus(`No data found for ${ticker.toUpperCase()}.`);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [exchange, ticker, setData, setLoading, setStatus]);

  // Debounce input
  useEffect(() => {
    const timer = setTimeout(() => loadTicker(), 500);
    return () => clearTimeout(timer);
  }, [ticker, exchange, loadTicker]);

  function downloadBlob(content: string, filename: string, type: string) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const handleExcelDownload = () => {
    if (!data.length) return;
    const csv = ['Date,Sentiment score', ...data.map((r) => `${r.date},${r.score}`)].join('\n');
    downloadBlob(csv, `${ticker || 'data'}.csv`, 'text/csv;charset=utf-8');
  };

  const handleJSONDownload = () => {
    if (!data.length) return;
    downloadBlob(JSON.stringify(data, null, 2), `${ticker || 'data'}.json`, 'application/json');
  };

  return (
    <header
      className={twMerge(
        'sticky top-0 z-10 bg-background-light/80 dark:bg-background-dark/80 backdrop-blur-sm border-b border-black/10 dark:border-white/10'
      )}
    >
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">NSS</h1>
        <div className="flex flex-col sm:flex-row gap-3 items-center w-1/2">
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="w-36 p-3 rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-black/20 focus:ring-2 focus:ring-primary text-black dark:text-white"
          >
            <option value="" disabled>
              Select exchange
            </option>
            {EXCHANGES.map((ex) => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>

          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder={`Enter stock ticker (e.g., ${import.meta.env.VITE_DEFAULT_TICKER})`}
            className="w-full p-3 rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-black/20 outline-0 text-black dark:text-white placeholder:text-black/40 dark:placeholder:text-white/40"
            autoComplete="off"
          />

          <button
            type="button"
            onClick={handleExcelDownload}
            className="flex items-center px-4 py-2 rounded-lg bg-primary text-white font-semibold hover:bg-primary/90"
          >
            Excel
          </button>

          <button
            type="button"
            onClick={handleJSONDownload}
            className="flex items-center px-4 py-2 rounded-lg bg-black/10 dark:bg-white/10 text-black dark:text-white font-semibold hover:bg-black/20 dark:hover:bg-white/20"
          >
            JSON
          </button>
        </div>
        <button
            type="button"
            aria-label="Toggle dark mode"
            onClick={handleThemeToggle}
            className="p-2 rounded-full text-black/60 dark:text-white/60 hover:bg-black/10 dark:hover:bg-white/10"
          >
            <svg viewBox="0 0 24 24" width={24} className="fill-current">
              <path d="M12 16C14.2091 16 16 14.2091 16 12C16 9.79086 14.2091 8 12 8V16Z" />
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2ZM12 4V8C9.79086 8 8 9.79086 8 12C8 14.2091 9.79086 16 12 16V20C16.4183 20 20 16.4183 20 12C20 7.58172 16.4183 4 12 4Z"
              />
            </svg>
          </button>
      </div>
    </header>
  );
}

type ChartType = 'stacked-y' | 'calendar' | 'donut'; //| 'sparklines' | 'stream'

export function NSSMain() {
  const { data, status } = useNSSStore();
  const [view, setView] = useState<'table' | 'chart'>('table');
  const [chartType, setChartType] = useState<ChartType>('stacked-y');
  const [isDark, setIsDark] = useState(false);

  // Monitor theme changes
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    setIsDark(document.documentElement.classList.contains('dark'));
    return () => observer.disconnect();
  }, []);

  return (
    <main className="flex-grow container mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12">
      <section className="max-w-4xl mx-auto">
        <div className="flex flex-col sm:flex-row items-start gap-6">
          <aside
            className={twMerge(
              'w-full sm:w-56 bg-white dark:bg-black/20 border border-black/10 dark:border-white/10 rounded-xl shadow-sm p-4'
            )}
          >
            <h3 className="text-sm font-semibold text-black/70 dark:text-white/70 mb-3">
              Sentiment legend
            </h3>
            <ul className="space-y-2 mb-3">
              <li className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <span className="text-sm">1 - Positive</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-rose-500" />
                <span className="text-sm">2 - Negative</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                <span className="text-sm">0 - Neutral</span>
              </li>
            </ul>

            <ol className=''>
              <li><strong>- Do NOT treat neutral days as completely neutral - they could be unknown too.</strong></li>
              <li><strong>- This is not a financial advice.</strong></li>
            </ol>
          </aside>

          <div className="flex-1">
            <p className="sr-only" aria-live="polite">
              {status}
            </p>

            <div className="mb-3 flex flex-col sm:flex-row items-start sm:items-center gap-3 bg-white dark:bg-black/20 p-3 w-full rounded-xl shadow-sm">
              <div
                role="radiogroup"
                aria-label="View mode"
                className="inline-flex rounded-lg border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/10 overflow-hidden"
              >
                {(['table', 'chart'] as const).map((mode) => (
                  <label
                    key={mode}
                    className={twMerge(
                      'block px-3 py-1.5 text-sm cursor-pointer transition select-none',
                      view === mode
                        ? 'bg-white dark:bg-black text-black dark:text-white'
                        : 'text-black/70 dark:text-white/70'
                    )}
                  >
                    <input
                      type="radio"
                      name="view-toggle"
                      className="sr-only"
                      checked={view === mode}
                      onChange={() => setView(mode)}
                    />
                    {mode === 'table' ? 'Table View' : 'Chart View'}
                  </label>
                ))}
              </div>

              {view === 'chart' && (
                <div className="flex items-center gap-2 ml-0 sm:ml-3">
                  <label htmlFor="chart-type" className="text-sm text-black/70 dark:text-white/70">
                    Chart type
                  </label>
                  <select
                    id="chart-type"
                    value={chartType}
                    onChange={(e) => setChartType(e.target.value as ChartType)}
                    className="p-2 rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-black/20 text-sm text-black dark:text-white"
                  >
                    <option value="stacked-y">Stacked bar (yearly)</option>
                    <option value="calendar">Calendar heatmap</option>
                    {/* <option value="sparklines">Sparklines</option> */}
                    {/* <option value="stream">Streamgraph</option> */}
                    <option value="donut">KPI Ring Card (KPI Donut with a twist)</option>
                  </select>
                </div>
              )}
            </div>

            {view === 'table' ? (
              <div className="overflow-auto max-h-[60vh] bg-white dark:bg-black/20 p-3 w-full rounded-xl shadow-sm">
                <table className="w-full text-left">
                  <thead className="top-0 sticky bg-white dark:bg-black">
                    <tr className="border-b border-black/10 dark:border-white/10">
                      <th className="p-4 text-sm font-semibold text-black/60 dark:text-white/60">Date</th>
                      <th className="p-4 text-sm font-semibold text-black/60 dark:text-white/60 text-center">
                        Sentiment score
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/10 dark:divide-white/10">
                    {data.map((row) => (
                      <tr key={row.date}>
                        <th scope="row" className="p-4 whitespace-nowrap text-sm font-medium">
                          {row.date}
                        </th>
                        <td className="p-4 whitespace-nowrap text-sm text-center">{row.score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!data.length && <div className="text-gray-400 text-center py-7">No data to display</div>}
              </div>
            ) : (
              <div className={
                twMerge("bg-white dark:bg-black/20 p-3 w-full rounded-xl shadow-sm mx-auto",
                  chartType === 'donut' && "max-w-[60%]"
                )
                }>
                {!data.length ? (
                  <div className="h-80 flex items-center justify-center">
                    <span className="text-gray-400">No data to display</span>
                  </div>
                ) : (
                  <>
                    {chartType === 'stacked-y' && <SentimentStackedBar data={data} isDark={isDark} />}
                    {chartType === 'calendar' && <SentimentCalendar data={data} isDark={isDark} />}
                    {/* {chartType === 'sparklines' && (
                      <SentimentSparklines
                        datasets={{ [(ticker || 'Current').toUpperCase()]: data }}
                        isDark={isDark}
                      />
                    )} */}
                    {/* {chartType === 'stream' && <SentimentStream data={data} isDark={isDark} />} */}
                    {chartType === 'donut' && <SentimentDonut data={data} isDark={isDark} />}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}