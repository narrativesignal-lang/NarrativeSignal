import { QueryClient } from "@tanstack/react-query";

export const STALE_MARKET_MS = 10 * 60 * 1000;
export const STALE_MACRO_NEWS_MS = 15 * 60 * 1000;
export const STALE_TRENDS_MS = 12 * 60 * 60 * 1000;

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        gcTime: 45 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: 1
      }
    }
  });
}
