import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const sourceRoot = resolve(import.meta.dirname, "..");

test("home route renders the cover page instead of the agent audit entry", () => {
  const routesSource = readFileSync(resolve(sourceRoot, "app/routes.tsx"), "utf8");

  assert.match(routesSource, /import HomeCover from ['"]@\/pages\/HomeCover['"]/);
  assert.match(routesSource, /path: '\/', element: <HomeCover \/>/);
  assert.doesNotMatch(routesSource, /path: '\/', element: <AgentAudit \/>/);
});

test("home cover uses the supplied artwork and opens the one-click CVE startup dialog", () => {
  const homeSource = readFileSync(resolve(sourceRoot, "pages/HomeCover.tsx"), "utf8");
  const oneClickSource = readFileSync(resolve(sourceRoot, "pages/OneClickCVE.tsx"), "utf8");

  assert.match(homeSource, /\/Homepage\.png/);
  assert.match(homeSource, /\/one-click-cve\?start=1/);
  assert.match(homeSource, /aria-label="点击获取CVE编号"/);
  assert.match(oneClickSource, /new URLSearchParams\(location\.search\)/);
  assert.match(oneClickSource, /setDialogOpen\(true\)/);
});

test("home cover keeps the app sidebar visible", () => {
  const appSource = readFileSync(resolve(sourceRoot, "app/App.tsx"), "utf8");

  assert.doesNotMatch(appSource, /isHomeCover/);
  assert.match(appSource, /<Sidebar collapsed=\{collapsed\} setCollapsed=\{setCollapsed\} \/>/);
  assert.match(appSource, /collapsed \? "md:ml-\[104px\]" : "md:ml-\[296px\]"/);
});
