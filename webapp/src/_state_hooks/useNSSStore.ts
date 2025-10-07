import { create } from 'zustand';

export type SentimentRow = { date: string; score: number };

interface NSSState {
  exchange: string;
  ticker: string;
  data: SentimentRow[];
  loading: boolean;
  status: string;
  setExchange: (exchange: string) => void;
  setTicker: (ticker: string) => void;
  setData: (data: SentimentRow[]) => void;
  setLoading: (loading: boolean) => void;
  setStatus: (status: string) => void;
}

export const useNSSStore = create<NSSState>((set) => ({
  exchange: 'NASDAQ',
  ticker: '',
  data: [],
  loading: false,
  status: '',
  setExchange: (exchange) => set({ exchange }),
  setTicker: (ticker) => set({ ticker }),
  setData: (data) => set({ data }),
  setLoading: (loading) => set({ loading }),
  setStatus: (status) => set({ status }),
}));
