/**
 * SWR fetcher utilities.
 * SWR = stale-while-revalidate: returns cached data instantly on tab switch,
 * then silently revalidates in the background. No spinner on repeated visits.
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

/**
 * Create an SWR fetcher bound to a Bearer token.
 * Usage in a component:
 *   const { data, error, isLoading, mutate } = useSWR(
 *     token ? ["/api/documents", token] : null,
 *     ([url, tok]) => swrFetch(url, tok)
 *   );
 */
export async function swrFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = new Error(`Fetch failed: ${res.status}`);
    (err as any).status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

/** SWR global config — revalidate on focus, dedupe within 5s */
export const swrConfig = {
  revalidateOnFocus: true,        // silently refresh when user switches back to tab
  revalidateOnReconnect: true,    // refresh on network reconnect
  dedupingInterval: 5000,         // deduplicate identical fetches within 5s
  errorRetryCount: 2,
  keepPreviousData: true,         // show stale data while revalidating (no blank flash)
};
