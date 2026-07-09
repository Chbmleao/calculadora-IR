import { API_BASE_URL, extractErrorMessage } from "../api/client";
import { useHealth } from "../api/hooks";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatTile } from "../components/StatTile";
import { formatBRL, formatPct } from "../lib/format";

/**
 * Dashboard placeholder (real screen: task 09). Also exercises the data layer
 * end-to-end by calling `GET /api/health` and rendering the JSON response —
 * proof that the typed API client + React Query hooks reach the backend.
 */
export function DashboardPage() {
  const health = useHealth();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Positions & allocation — built in task 09."
      />

      {/* Placeholder headline metrics (formatting helpers in action). */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Total value" value={formatBRL(0)} hint="Awaiting import" />
        <StatTile label="Invested" value={formatBRL(0)} />
        <StatTile
          label="Total return"
          value={formatPct(0, { signed: true })}
          trend="neutral"
        />
        <StatTile label="Positions" value="0" />
      </div>

      <Card
        title="Backend connectivity"
        action={
          <code className="text-xs text-neutral-500 dark:text-neutral-400">
            {API_BASE_URL}
          </code>
        }
      >
        {health.isLoading && <LoadingSpinner label="Calling /api/health…" />}
        {health.isError && (
          <ErrorBanner
            message={extractErrorMessage(health.error)}
            onRetry={() => void health.refetch()}
          />
        )}
        {health.data && (
          <pre className="overflow-x-auto rounded-lg bg-neutral-100 p-3 text-xs text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
            {JSON.stringify(health.data, null, 2)}
          </pre>
        )}
      </Card>

      <EmptyState
        icon="📊"
        title="No positions yet"
        description="Import a B3 negotiation summary to see your holdings and allocation here."
      />
    </div>
  );
}
