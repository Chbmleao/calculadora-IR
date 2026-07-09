import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

/** Target allocation & rebalancing placeholder (real screen: task 11). */
export function RebalancePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Rebalance"
        description="Define target weights and see what to buy — built in task 11."
      />
      <EmptyState
        icon="⚖️"
        title="No targets defined"
        description="Set a desired percentage per asset or class to get buy suggestions that steer the portfolio toward your target."
      />
    </div>
  );
}
