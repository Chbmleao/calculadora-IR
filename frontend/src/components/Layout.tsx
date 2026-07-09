import { NavLink, Outlet } from "react-router-dom";
import clsx from "clsx";

import { usePositions, useRefreshQuotes } from "../api/hooks";
import { formatDate } from "../lib/format";
import { useToast } from "../lib/toast";
import { LoadingSpinner } from "./LoadingSpinner";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "📊", end: true },
  { to: "/evolution", label: "Evolution", icon: "📈" },
  { to: "/rebalance", label: "Rebalance", icon: "⚖️" },
  { to: "/accounting", label: "Accounting", icon: "🧾" },
  { to: "/import", label: "Import", icon: "📥" },
];

/** App shell: sidebar nav + header (as-of date + global "Refresh quotes"). */
export function Layout() {
  const positions = usePositions();
  const refresh = useRefreshQuotes();
  const { notify } = useToast();

  const asOf = positions.data?.as_of ?? null;

  const handleRefresh = () => {
    refresh.mutate(undefined, {
      onSuccess: (result) =>
        notify(`Refreshed ${result.updated} quotes`, "success"),
    });
  };

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <div className="mx-auto flex min-h-screen max-w-7xl">
        {/* Sidebar (desktop) */}
        <aside className="hidden w-56 shrink-0 border-r border-neutral-200 p-4 dark:border-neutral-800 sm:block">
          <div className="mb-6 flex items-center gap-2 px-2">
            <span className="text-xl" aria-hidden>
              💹
            </span>
            <span className="text-sm font-semibold">Invest Dashboard</span>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-600 text-white"
                      : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800",
                  )
                }
              >
                <span aria-hidden>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-neutral-200 bg-neutral-50/80 px-4 py-3 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/80">
            <div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">As of</p>
              <p className="text-sm font-medium tabular-nums">
                {asOf ? formatDate(asOf) : "—"}
              </p>
            </div>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refresh.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {refresh.isPending ? (
                <LoadingSpinner className="h-4 w-4 border-white" />
              ) : (
                <span aria-hidden>↻</span>
              )}
              Refresh quotes
            </button>
          </header>

          {/* Nav (mobile) */}
          <nav className="flex gap-1 overflow-x-auto border-b border-neutral-200 px-2 py-2 dark:border-neutral-800 sm:hidden">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    "whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-600 text-white"
                      : "text-neutral-600 dark:text-neutral-300",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <main className="flex-1 p-4 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
