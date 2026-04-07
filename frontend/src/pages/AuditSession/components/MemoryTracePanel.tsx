import { BookMarked, MemoryStick } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuditSessionMemory } from "@/pages/AuditSession/types";

interface MemoryTracePanelProps {
  memories: AuditSessionMemory[];
}

export function MemoryTracePanel({ memories }: MemoryTracePanelProps) {
  return (
    <Card className="overflow-hidden rounded-[26px] border border-[rgba(191,208,198,.72)] bg-[linear-gradient(180deg,rgba(255,255,255,.98),rgba(247,250,248,.96))] shadow-[0_18px_48px_rgba(84,110,93,.08)]">
      <CardHeader className="border-b border-[rgba(186,203,193,.4)] pb-4">
        <CardTitle className="flex items-center gap-3 text-base font-semibold text-slate-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[rgba(226,243,255,.95)] text-sky-700 shadow-sm">
            <MemoryStick className="h-5 w-5" />
          </span>
          Memory Trace
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        {memories.length === 0 ? (
          <p className="text-sm leading-6 text-muted-foreground">这次会话还没有附加任何 instruction 或 recall memory。</p>
        ) : (
          memories.map((memory) => (
            <div key={memory.id} className="rounded-[20px] border border-[rgba(219,226,221,.9)] bg-white/92 p-4 shadow-[0_10px_25px_rgba(97,118,103,.06)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <BookMarked className="h-4 w-4 text-sky-600" />
                    <p className="text-sm font-semibold text-slate-900">{memory.title}</p>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{memory.memory_kind} · {memory.source_type}</p>
                </div>
                <div className="rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700">
                  #{memory.sequence} · {memory.relevance_score ?? "-"}
                </div>
              </div>
              <p className="mt-3 break-all text-xs leading-6 text-muted-foreground">{memory.source_ref}</p>
              <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-2xl bg-[rgba(246,248,247,.95)] p-3 text-xs leading-6 text-slate-700">{memory.content}</pre>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
