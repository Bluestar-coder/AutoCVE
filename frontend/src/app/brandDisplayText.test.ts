import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const sourceRoot = resolve(import.meta.dirname, "..");
const oldBrandPattern = new RegExp(["AI" + " Audit", "Audit" + "AI", "AI" + "Audit"].join("|"));

test("login screen shows AutoCVE brand text and icon metadata", () => {
  const loginSource = readFileSync(resolve(sourceRoot, "pages/Login.tsx"), "utf8");

  assert.match(loginSource, />AutoCVE</);
  assert.match(loginSource, /\\u767b\\u5f55 AutoCVE/);
  assert.match(loginSource, /alt="AutoCVE"/);
  assert.match(loginSource, /\/autocve_icon\.svg/);
  assert.doesNotMatch(loginSource, oldBrandPattern);
});

test("home shell shows AutoCVE in the sidebar brand", () => {
  const sidebarSource = readFileSync(resolve(sourceRoot, "components/layout/Sidebar.tsx"), "utf8");

  assert.match(sidebarSource, />AutoCVE</);
  assert.match(sidebarSource, /alt="AutoCVE"/);
  assert.match(sidebarSource, /\/autocve_icon\.svg/);
  assert.doesNotMatch(sidebarSource, oldBrandPattern);
});

test("home splash screen uses the requested visible runtime labels", () => {
  const splashSource = readFileSync(resolve(sourceRoot, "pages/AgentAudit/components/SplashScreen.tsx"), "utf8");

  assert.match(splashSource, /Loading AutoCVE Core/);
  assert.match(splashSource, /root@autocve:~#/);
  assert.match(splashSource, />Auto\s*<\/span>\s*<span[^>]*>CVE</);
  assert.doesNotMatch(splashSource, oldBrandPattern);
  assert.doesNotMatch(splashSource, new RegExp("root@" + "ai" + "audit:~#"));
});