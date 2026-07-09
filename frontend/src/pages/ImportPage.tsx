import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

/** Excel import placeholder (real screen: task 12 / ingestion task 02). */
export function ImportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Import"
        description="Upload B3 Excel exports (summary, proventos, history)."
      />
      <EmptyState
        icon="📥"
        title="Nothing imported yet"
        description="Drag in a B3 “Negociação - Resumo”, “Proventos Recebidos”, or negotiation-history export to populate the dashboard."
      />
    </div>
  );
}
