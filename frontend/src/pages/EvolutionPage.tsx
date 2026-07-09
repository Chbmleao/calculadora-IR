import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

/** Patrimony evolution & rentability placeholder (real screen: task 10). */
export function EvolutionPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Evolution"
        description="Patrimony over time and true return — built in task 10."
      />
      <EmptyState
        icon="📈"
        title="No history yet"
        description="Import your negotiation history to reconstruct the patrimony curve and separate contributions from market gains."
      />
    </div>
  );
}
