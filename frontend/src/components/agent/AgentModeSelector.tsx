import { Bot, CheckCircle2, Shield, Sparkles, Zap } from "lucide-react";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/shared/utils/utils";

import {
  AUDIT_MODE_OPTIONS,
  type AuditMode,
  getAuditModeLabel,
} from "./auditModeConfig";

const COPY = {
  sectionLabel: "\u5ba1\u8ba1\u6a21\u5f0f",
  title: "\u6a21\u5f0f\u9009\u62e9",
  subtitle:
    "\u9009\u62e9\u672c\u6b21\u4efb\u52a1\u7684\u6267\u884c\u8def\u5f84\uff0c\u5de5\u5177\u626b\u63cf\u3001Agent \u81ea\u4e3b\u5ba1\u8ba1\u548c\u7efc\u5408\u5e76\u884c\u4e09\u79cd\u6a21\u5f0f\u90fd\u80fd\u5728\u8fd9\u91cc\u5feb\u901f\u5207\u6362\u3002",
  recommended: "\u63a8\u8350",
  settingsSuffix: " \u914d\u7f6e",
  verificationSummary: "\u662f\u5426\u5f00\u542f\u52a8\u6001\u6f0f\u6d1e\u9a8c\u8bc1\uff08\u9ed8\u8ba4\u5173\u95ed\uff09",
  verificationTitle: "\u662f\u5426\u5f00\u542f\u52a8\u6001\u6f0f\u6d1e\u9a8c\u8bc1",
  verificationDescription:
    "\u5f00\u542f\u540e\u4f1a\u6267\u884c\u52a8\u6001\u9a8c\u8bc1\uff0c\u8017\u65f6\u548c token \u6d88\u8017\u90fd\u4f1a\u589e\u52a0\u3002\u52a8\u6001\u9a8c\u8bc1\u6d89\u53ca\u7f51\u7edc\u3001\u73af\u5883\u90e8\u7f72\u3001\u6743\u9650\u7b49\u591a\u65b9\u9762\u56e0\u7d20\uff0c\u53ef\u80fd\u4e0d\u591f\u7a33\u5b9a\uff0c\u5efa\u8bae\u4ec5\u5728\u9700\u8981\u65f6\u5f00\u542f\u3002",
  recommendedOff: "\u63a8\u8350\u5173\u95ed",
} as const;

const MODE_STYLES: Record<
  AuditMode,
  {
    card: string;
    iconBox: string;
    icon: string;
    glow: string;
    check: string;
    panel: string;
    switchHint: string;
    workflow: string;
  }
> = {
  enhanced_scan: {
    card: "border-amber-300/70 bg-[linear-gradient(135deg,rgba(255,251,235,0.96),rgba(255,247,237,0.9))] shadow-[0_16px_40px_-28px_rgba(245,158,11,0.55)] dark:border-amber-500/40 dark:bg-[linear-gradient(135deg,rgba(69,26,3,0.75),rgba(120,53,15,0.34))]",
    iconBox: "border-amber-300/80 bg-amber-100/80 dark:border-amber-400/30 dark:bg-amber-500/10",
    icon: "text-amber-600 dark:text-amber-200",
    glow: "from-amber-400/0 via-amber-300/90 to-amber-500/0",
    check: "text-amber-600 dark:text-amber-200",
    panel: "border-amber-200/80 bg-amber-50/85 dark:border-amber-400/20 dark:bg-amber-950/35",
    switchHint: "text-amber-700 dark:text-amber-200",
    workflow: "border-amber-200/80 bg-amber-50/80 text-amber-700 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-200",
  },
  intelligent_audit: {
    card: "border-violet-300/80 bg-[linear-gradient(135deg,rgba(245,243,255,0.98),rgba(237,233,254,0.88))] shadow-[0_20px_44px_-28px_rgba(124,58,237,0.55)] dark:border-violet-500/40 dark:bg-[linear-gradient(135deg,rgba(49,28,90,0.78),rgba(91,33,182,0.28))]",
    iconBox: "border-violet-300/80 bg-violet-100/80 dark:border-violet-400/30 dark:bg-violet-500/10",
    icon: "text-violet-600 dark:text-violet-200",
    glow: "from-violet-400/0 via-violet-300/95 to-fuchsia-400/0",
    check: "text-violet-600 dark:text-violet-200",
    panel: "border-violet-200/80 bg-violet-50/85 dark:border-violet-400/20 dark:bg-violet-950/35",
    switchHint: "text-violet-700 dark:text-violet-200",
    workflow: "border-violet-200/80 bg-violet-50/80 text-violet-700 dark:border-violet-400/20 dark:bg-violet-500/10 dark:text-violet-200",
  },
  comprehensive_audit: {
    card: "border-emerald-300/80 bg-[linear-gradient(135deg,rgba(236,253,245,0.98),rgba(220,252,231,0.9))] shadow-[0_18px_40px_-28px_rgba(16,185,129,0.5)] dark:border-emerald-500/40 dark:bg-[linear-gradient(135deg,rgba(6,78,59,0.78),rgba(6,95,70,0.28))]",
    iconBox: "border-emerald-300/80 bg-emerald-100/80 dark:border-emerald-400/30 dark:bg-emerald-500/10",
    icon: "text-emerald-600 dark:text-emerald-200",
    glow: "from-emerald-400/0 via-emerald-300/90 to-cyan-400/0",
    check: "text-emerald-600 dark:text-emerald-200",
    panel: "border-emerald-200/80 bg-emerald-50/85 dark:border-emerald-400/20 dark:bg-emerald-950/35",
    switchHint: "text-emerald-700 dark:text-emerald-200",
    workflow: "border-emerald-200/80 bg-emerald-50/80 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-500/10 dark:text-emerald-200",
  },
};

interface AgentModeSelectorProps {
  value: AuditMode;
  onChange: (mode: AuditMode) => void;
  verificationEnabled: boolean;
  onVerificationChange: (enabled: boolean) => void;
  disabled?: boolean;
}

export type { AuditMode } from "./auditModeConfig";

export default function AgentModeSelector({
  value,
  onChange,
  verificationEnabled,
  onVerificationChange,
  disabled = false,
}: AgentModeSelectorProps) {
  const activeStyle = MODE_STYLES[value];

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-2xl border border-violet-200/70 bg-[linear-gradient(135deg,rgba(250,245,255,0.95),rgba(255,255,255,0.92))] px-4 py-3 shadow-[0_14px_30px_-24px_rgba(124,58,237,0.45)] dark:border-violet-500/25 dark:bg-[linear-gradient(135deg,rgba(46,16,101,0.58),rgba(15,23,42,0.72))]">
        <div className="mt-0.5 rounded-xl border border-violet-200/80 bg-violet-100/80 p-2 dark:border-violet-400/30 dark:bg-violet-500/10">
          <Shield className="h-4 w-4 text-violet-600 dark:text-violet-200" />
        </div>
        <div className="space-y-1">
          <p className="font-mono text-xs font-bold uppercase tracking-[0.22em] text-violet-700 dark:text-violet-200">
            {COPY.sectionLabel}
          </p>
          <p className="text-sm font-semibold text-foreground">{COPY.title}</p>
          <p className="text-xs leading-5 text-muted-foreground">{COPY.subtitle}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {AUDIT_MODE_OPTIONS.map((option) => {
          const isSelected = value === option.mode;
          const style = MODE_STYLES[option.mode];
          const Icon =
            option.mode === "enhanced_scan"
              ? Zap
              : option.mode === "intelligent_audit"
                ? Bot
                : Sparkles;

          return (
            <label
              key={option.mode}
              className={cn(
                "group relative block cursor-pointer overflow-hidden rounded-2xl border p-0 transition-all duration-200",
                "hover:-translate-y-0.5 hover:shadow-[0_18px_34px_-28px_rgba(15,23,42,0.35)]",
                isSelected
                  ? style.card
                  : "border-border/70 bg-background/85 hover:border-border dark:bg-muted/20",
                disabled && "pointer-events-none opacity-55"
              )}
            >
              <input
                type="radio"
                name="auditMode"
                value={option.mode}
                checked={isSelected}
                onChange={() => onChange(option.mode)}
                disabled={disabled}
                className="sr-only"
              />

              <div
                className={cn(
                  "absolute inset-x-6 top-0 h-px bg-gradient-to-r opacity-0 transition-opacity duration-200",
                  style.glow,
                  isSelected && "opacity-100"
                )}
              />

              {option.recommended && (
                <div className="absolute right-3 top-3 rounded-full border border-violet-300/80 bg-violet-600 px-2.5 py-1 text-[11px] font-bold text-white shadow-[0_10px_24px_-18px_rgba(124,58,237,0.85)]">
                  {COPY.recommended}
                </div>
              )}

              <div className="space-y-4 p-4">
                <div className="flex items-start gap-3">
                  <div className={cn("rounded-2xl border p-2.5 shadow-sm", style.iconBox)}>
                    <Icon className={cn("h-4 w-4", style.icon)} />
                  </div>

                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-base font-semibold tracking-tight text-foreground">{option.label}</p>
                          {option.recommended && !isSelected && (
                            <span className="rounded-full border border-violet-200/80 bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-600 dark:border-violet-400/30 dark:bg-violet-500/10 dark:text-violet-200">
                              {COPY.recommended}
                            </span>
                          )}
                        </div>
                        <p
                          className={cn(
                            "mt-2 inline-flex rounded-full border px-2.5 py-1 font-mono text-[11px] shadow-sm",
                            style.workflow
                          )}
                        >
                          {option.workflow}
                        </p>
                      </div>

                      <div
                        className={cn(
                          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-all",
                          isSelected
                            ? `border-current bg-white/70 dark:bg-slate-950/40 ${style.check}`
                            : "border-border/70 bg-background/70 text-transparent"
                        )}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  {option.description.map((item) => (
                    <div
                      key={item}
                      className={cn(
                        "rounded-xl border border-white/60 bg-white/70 px-3 py-2 text-sm leading-6 text-slate-700 shadow-sm dark:border-white/5 dark:bg-slate-950/20 dark:text-slate-100/90",
                        isSelected && "border-white/80"
                      )}
                    >
                      <span className={cn("mr-2 inline-block h-2 w-2 rounded-full align-middle", style.iconBox)} />
                      <span className="align-middle">{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </label>
          );
        })}
      </div>

      <div className={cn("rounded-2xl border p-4 shadow-[0_18px_32px_-28px_rgba(15,23,42,0.4)]", activeStyle.panel)}>
        <div className="space-y-1.5">
          <p className="text-sm font-semibold text-foreground">{getAuditModeLabel(value) + COPY.settingsSuffix}</p>
          <p className="text-xs leading-5 text-muted-foreground">{COPY.verificationSummary}</p>
        </div>

        <div className="mt-4 flex items-center justify-between gap-4 rounded-2xl border border-white/70 bg-background/80 px-4 py-3 shadow-sm dark:border-white/10 dark:bg-slate-950/25">
          <div className="space-y-1">
            <p className="text-sm font-medium text-foreground">{COPY.verificationTitle}</p>
            <p className="text-xs leading-5 text-muted-foreground">{COPY.verificationDescription}</p>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {!verificationEnabled && (
              <span className={cn("text-xs font-semibold", activeStyle.switchHint)}>{COPY.recommendedOff}</span>
            )}
            <Switch
              checked={verificationEnabled}
              onCheckedChange={onVerificationChange}
              disabled={disabled}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
