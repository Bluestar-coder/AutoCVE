import { BadgeCheck, SearchCheck } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuditSessionDetail } from "@/pages/AuditSession/types";

export function FindingsSidebar({ session }: { session: AuditSessionDetail | null }) {
  const reconKeys = Object.keys(session?.recon_payload || {});

  return (
    <Card className="overflow-hidden rounded-[26px] border border-[rgba(191,208,198,.72)] bg-[linear-gradient(180deg,rgba(255,255,255,.98),rgba(247,250,248,.96))] shadow-[0_18px_48px_rgba(84,110,93,.08)]">
      <CardHeader className="border-b border-[rgba(186,203,193,.4)] pb-4">
        <CardTitle className="flex items-center gap-3 text-base font-semibold text-slate-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[rgba(255,243,223,.95)] text-orange-700 shadow-sm">
            <SearchCheck className="h-5 w-5" />
          </span>
          Session Context
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4 text-sm text-muted-foreground">
        <div className="rounded-[20px] border border-[rgba(219,226,221,.9)] bg-white/92 p-4 shadow-[0_10px_25px_rgba(97,118,103,.06)]">
          <div className="flex items-center gap-2 text-slate-800">
            <BadgeCheck className="h-4 w-4 text-orange-600" />
            <span className="font-semibold">会话状态</span>
          </div>
          <p className="mt-2 leading-6">当前 runtime stack：{session?.runtime_stack || "unknown"}</p>
          <p className="leading-6">当前会话状态：{session?.state || "unknown"}</p>
        </div>
        <div className="rounded-[20px] border border-[rgba(219,226,221,.9)] bg-white/92 p-4 shadow-[0_10px_25px_rgba(97,118,103,.06)]">
          <p className="font-semibold text-slate-800">Recon payload keys</p>
          <p className="mt-2 leading-6">{reconKeys.length > 0 ? reconKeys.join(", ") : "none"}</p>
        </div>
        <div className="rounded-[20px] border border-dashed border-[rgba(186,203,193,.75)] bg-[rgba(247,250,248,.96)] p-4 text-xs leading-6">
          这里展示的是当前会话上下文概览。右侧其它卡片会继续展开工具、技能、记忆和 verification 交接痕迹。
        </div>
      </CardContent>
    </Card>
  );
}
