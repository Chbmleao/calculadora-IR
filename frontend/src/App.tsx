import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { EvolutionPage } from "./pages/EvolutionPage";
import { RebalancePage } from "./pages/RebalancePage";
import { AccountingPage } from "./pages/AccountingPage";
import { ImportPage } from "./pages/ImportPage";

/**
 * Route table. All screens share the {@link Layout} shell (sidebar nav + header).
 * Placeholder pages are filled in by tasks 09-12.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="evolution" element={<EvolutionPage />} />
        <Route path="rebalance" element={<RebalancePage />} />
        <Route path="accounting" element={<AccountingPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Route>
    </Routes>
  );
}
