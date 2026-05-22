const assert = require("assert");
const fs = require("fs");
const path = require("path");
const ts = require("../frontend/node_modules/typescript");

const repoRoot = path.resolve(__dirname, "..");
const utilsPath = path.join(repoRoot, "frontend", "src", "pages", "AgentAudit", "utils.ts");
const source = fs.readFileSync(utilsPath, "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX,
  },
  fileName: utilsPath,
}).outputText;

const moduleLike = { exports: {} };
const fn = new Function("exports", "module", "require", transpiled);
fn(moduleLike.exports, moduleLike, require);

const { dedupeActivityLogs, stripAgentLogPrefix } = moduleLike.exports;

assert.strictEqual(typeof dedupeActivityLogs, "function", "dedupeActivityLogs should be exported");
assert.strictEqual(typeof stripAgentLogPrefix, "function", "stripAgentLogPrefix should be exported");

const duplicateContent =
  "[Finding Agent] **Evaluating potential vulnerabilities**\n\nI need to keep auditing for vulnerabilities.";

const logs = [
  {
    id: "hist-1",
    time: "11:04:20",
    type: "thinking",
    title: duplicateContent,
    content: duplicateContent,
    agentName: "Finding",
  },
  {
    id: "runtime-1",
    time: "11:04:20",
    type: "thinking",
    title: "**Evaluating potential vulnerabilities**",
    content: "**Evaluating potential vulnerabilities**\n\nI need to keep auditing for vulnerabilities.",
    agentName: "Finding",
  },
  {
    id: "recon-1",
    time: "11:04:21",
    type: "thinking",
    title: "Recon summary",
    content: "Mapped repository routes.",
    agentName: "Recon",
  },
];

const deduped = dedupeActivityLogs(logs);
assert.strictEqual(deduped.length, 2, "duplicate Finding runtime/event logs should collapse to one row");
assert.deepStrictEqual(
  deduped.map((item) => item.id),
  ["hist-1", "recon-1"],
  "the first visible Activity Log entry should be retained"
);
assert.strictEqual(
  stripAgentLogPrefix(duplicateContent),
  "**Evaluating potential vulnerabilities**\n\nI need to keep auditing for vulnerabilities."
);
