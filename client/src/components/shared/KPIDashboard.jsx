import React from "react";

import AttentionValuePanel from "../app/AttentionValuePanel";
import EngagementRatePanel from "../app/EngagementRatePanel";
import ExecutionSpeedPanel from "../app/ExecutionSpeedPanel";
import ImpactPanel from "../app/ImpactPanel";
import IncomeEfficiencyPanel from "../app/IncomeEfficiencyPanel";
import MonetizationEfficiencyPanel from "../app/MonetizationEfficiencyPanel";

export default function KPIDashboard() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[#00ffaa]">
          KPI Snapshot
        </p>
        <h2 className="mt-3 text-3xl font-black tracking-tight text-white">
          Performance signals across the workspace
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-zinc-500">
          This aggregate view pulls together the existing KPI-oriented panels without
          changing their internal logic.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <AttentionValuePanel />
        </div>
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <EngagementRatePanel />
        </div>
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <ExecutionSpeedPanel />
        </div>
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <ImpactPanel />
        </div>
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <IncomeEfficiencyPanel />
        </div>
        <div className="rounded-3xl border border-zinc-800/60 bg-zinc-950/60 p-4">
          <MonetizationEfficiencyPanel />
        </div>
      </div>
    </div>
  );
}
