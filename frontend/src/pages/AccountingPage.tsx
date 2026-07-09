import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

/** Bens e Direitos (DIRPF) placeholder (real screen: task 12). */
export function AccountingPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounting"
        description="Generate the DIRPF “Bens e Direitos” sheet — built in task 12."
      />
      <EmptyState
        icon="🧾"
        title="Nothing to declare yet"
        description="Import your proventos and negotiation summary to preview and download the Bens e Direitos report."
      />
    </div>
  );
}
