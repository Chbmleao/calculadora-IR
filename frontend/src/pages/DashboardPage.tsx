import { Link } from "react-router-dom";

import { extractErrorMessage } from "../api/client";
import { usePositions, useRefreshQuotes } from "../api/hooks";
import { Card } from "../components/Card";
import { DashboardAllocationDonut } from "../components/DashboardAllocationDonut";
import { DashboardPositionsTable } from "../components/DashboardPositionsTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatTile } from "../components/StatTile";
import { formatBRL, formatDate, formatPct } from "../lib/format";
import { useToast } from "../lib/toast";

/** A pulsing placeholder tile shown while positions load. */
function TileSkeleton() {
  return (
    <Card>
      <div className="h-3 w-20 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
      <div className="mt-3 h-7 w-28 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
    </Card>
  );
}

/**
 * Dashboard (task 09): portfolio at a glance — KPI tiles, an allocation donut by
 * asset class, and a sortable positions table. Consumes
 * `GET /api/portfolio/positions` and re-reads after a global quote refresh.
 */
export function DashboardPage() {
  const positions = usePositions();
  const refresh = useRefreshQuotes();
  const { notify } = useToast();

  const handleRefresh = () => {
    refresh.mutate(undefined, {
      onSuccess: (result) =>
        notify(`Refreshed ${result.updated} quotes`, "success"),
      // Errors are surfaced globally by the queryClient MutationCache.
    });
  };

  const refreshButton = (
    <button
      type="button"
      onClick={handleRefresh}
      disabled={refresh.isPending}
      className="inline-flex items-center gap-2 rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
    >
      {refresh.isPending ? (
        <LoadingSpinner className="h-4 w-4" />
      ) : (
        <span aria-hidden>↻</span>
      )}
      Refresh quotes
    </button>
  );

  const data = positions.data;
  const asOfLabel =
    data?.as_of != null ? `As of ${formatDate(data.as_of)}` : "No quotes yet";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Your holdings, allocation and unrealized result at a glance."
        actions={refreshButton}
      />

      {/* Loading */}
      {positions.isLoading && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <TileSkeleton />
            <TileSkeleton />
            <TileSkeleton />
            <TileSkeleton />
          </div>
          <Card title="Portfolio">
            <LoadingSpinner label="Loading positions…" />
          </Card>
        </div>
      )}

      {/* Error */}
      {positions.isError && (
        <ErrorBanner
          message={extractErrorMessage(positions.error)}
          onRetry={() => void positions.refetch()}
        />
      )}

      {/* Empty */}
      {data != null && data.positions.length === 0 && (
        <EmptyState
          icon="📊"
          title="No positions yet"
          description="Import your B3 negotiation summary to see your holdings and allocation here."
          action={
            <Link
              to="/import"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              Go to import
            </Link>
          }
        />
      )}

      {/* Data */}
      {data != null && data.positions.length > 0 && (
        <div className="space-y-6">
          {/* KPI row */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Total value"
              value={formatBRL(data.totals.market_value)}
              hint={asOfLabel}
            />
            <StatTile
              label="Invested"
              value={formatBRL(data.totals.invested)}
              hint={`${data.positions.length} ${
                data.positions.length === 1 ? "position" : "positions"
              }`}
            />
            <StatTile
              label="Unrealized P/L"
              value={
                <span
                  className={
                    data.totals.pnl >= 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-rose-600 dark:text-rose-400"
                  }
                >
                  {formatBRL(data.totals.pnl)}
                </span>
              }
              hint={formatPct(data.totals.pnl_pct, { signed: true })}
              trend={data.totals.pnl >= 0 ? "up" : "down"}
            />
            <StatTile
              label="Proventos"
              value={formatBRL(data.totals.proventos)}
              hint="Dividends & JCP received"
            />
          </div>

          {/* Allocation donut */}
          <Card title="Allocation by asset class">
            {data.allocation_by_class.length > 0 ? (
              <DashboardAllocationDonut
                allocation={data.allocation_by_class}
                totalValue={data.totals.market_value}
              />
            ) : (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                No allocation data available.
              </p>
            )}
          </Card>

          {/* Positions table */}
          <Card
            title="Positions"
            action={
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {data.positions.length}{" "}
                {data.positions.length === 1 ? "holding" : "holdings"}
              </span>
            }
            flush
          >
            <DashboardPositionsTable positions={data.positions} />
          </Card>
        </div>
      )}
    </div>
  );
}
