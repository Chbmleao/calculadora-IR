import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { extractErrorMessage } from "../api/client";
import { emitToast } from "./toastBridge";

/**
 * App-wide React Query client.
 *
 * Central error surfacing: mutation failures (user actions like refresh/import)
 * always toast; query failures toast only on background refetch (when data was
 * already present) so first-load errors are shown inline by pages instead of as
 * a toast on every mount.
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.state.data !== undefined) {
        emitToast(extractErrorMessage(error), "error");
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      emitToast(extractErrorMessage(error), "error");
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
