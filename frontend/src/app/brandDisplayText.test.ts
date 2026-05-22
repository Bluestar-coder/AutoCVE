import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const sourceRoot = resolve(import.meta.dirname, "..");

test("login screen shows AI Audit brand text without renaming assets", () => {
  const loginSource = readFileSync(resolve(sourceRoot, "pages/Login.tsx"), "utf8");

  assert.match(loginSource, />AI Audit</);
  assert.match(loginSource, /\\u767b\\u5f55 AI Audit/);
  assert.doesNotMatch(loginSource, />AuditAI</);
  assert.match(loginSource, /alt="AuditAI"/);
  assert.match(loginSource, /\/auditai_icon\.svg/);
});

test("home shell shows AI Audit in the sidebar brand", () => {
  const sidebarSource = readFileSync(resolve(sourceRoot, "components/layout/Sidebar.tsx"), "utf8");

  assert.match(sidebarSource, />AI Audit</);
  assert.doesNotMatch(sidebarSource, />AuditAI</);
  assert.match(sidebarSource, /alt="AuditAI"/);
  assert.match(sidebarSource, /\/auditai_icon\.svg/);
});

test("home splash screen uses the requested visible runtime labels", () => {
  const splashSource = readFileSync(resolve(sourceRoot, "pages/AgentAudit/components/SplashScreen.tsx"), "utf8");

  assert.match(splashSource, /Loading AIAudit Core/);
  assert.match(splashSource, /root@aiaudit:~#/);
  assert.match(splashSource, />AI\s*<\/span>\s*<span[^>]*>Audit</);
  assert.doesNotMatch(splashSource, /Loading AuditAI Core/);
  assert.doesNotMatch(splashSource, /root@auditai:~#/);
  assert.doesNotMatch(splashSource, />Audit\s*<\/span>\s*<span[^>]*>AI</);
});
