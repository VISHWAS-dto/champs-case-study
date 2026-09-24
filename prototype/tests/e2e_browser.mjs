// End-to-end test of rescue_sheet.html in headless Chrome via the DevTools protocol (Phase 10 QA).
// No npm packages: Node 22+ (built-in WebSocket) and a local Chrome.
//   node prototype/tests/e2e_browser.mjs            (set CHROME=/path/to/chrome if it isn't in the default place)
// Serves prototype/ on 127.0.0.1:8765, drives the page, prints PASS/FAIL, saves screenshots to a temp dir.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCR = mkdtempSync(path.join(tmpdir(), "rescue-e2e-"));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".csv": "text/csv" };
const server = createServer((req, res) => {
  const file = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  let body;
  try { body = readFileSync(file); } catch { res.writeHead(404).end(); return; }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" }).end(body);
}).listen(8765, "127.0.0.1");
const PAGE = "http://127.0.0.1:8765/rescue_sheet.html";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME,
  ["--headless=new", "--remote-debugging-port=9333", `--user-data-dir=${SCR}/chrome-prof`, "--window-size=1300,1000", "about:blank"],
  { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 50; i++) { try { targets = await (await fetch("http://127.0.0.1:9333/json")).json(); break; } catch { await sleep(200); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = {}; const errors = []; const requests = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending[d.id]) { pending[d.id](d); delete pending[d.id]; }
  if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") errors.push(JSON.stringify(d.params.args));
  if (d.method === "Network.requestWillBeSent") requests.push(d.params.request.url);
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: `(async()=>{${expr}})()`, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description);
  return r.result.result.value;
};
const shot = async (name) => {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${SCR}/${name}.png`, Buffer.from(r.result.data, "base64"));
};
await send("Runtime.enable"); await send("Network.enable"); await send("Page.enable");
await send("Page.navigate", { url: PAGE }); await sleep(1200);

// Helpers installed in the page: put a file into an <input type=file>, click, read text.
const H = `
window.T = {
  async setFile(id, name, text) {
    const dt = new DataTransfer(); dt.items.add(new File([text], name, { type: "text/csv" }));
    document.getElementById(id).files = dt.files;
  },
  async fileFrom(id, url) { await T.setFile(id, url.split("/").pop(), await (await fetch(url)).text()); },
  clearFile(id) { document.getElementById(id).value = ""; },
  async click(id) { document.getElementById(id).click(); await new Promise(r => setTimeout(r, 300)); },
  err() { return document.getElementById("errors").innerText.trim(); },
  text(id) { return document.getElementById(id).innerText; },
};`;
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };
await ev(H + "return 1");
const HDR = "lead_id,lead_source,geography,parent_timezone,created_at,demo_scheduled_at,rep_assigned,rep_shift,follow_up_attempts,demo_joined,demo_completed,converted";

// 1. starts
let v = await ev(`return { title: document.title, asOf: document.getElementById("asOf").value, logic: !!window.RescueLogic }`);
check("page loads, logic script loads, 'as of' defaults to now", v.logic && /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(v.asOf), JSON.stringify(v));

// 2. missing input
v = await ev(`await T.click("runBtn"); return T.err()`);
check("no file picked → clear error", v === "Pick a CRM export CSV first.", v);

// 3. main workflow on the case CSV
v = await ev(`await T.fileFrom("exportFile", "sample/case_export.csv");
  document.getElementById("asOf").value = "";
  await T.click("runBtn"); return T.err()`);
check("empty 'Run as of' → clear error", /valid 'Run as of'/.test(v), v);
v = await ev(`document.getElementById("asOf").value = "2026-07-15T09:00"; await T.click("runBtn");
  return { err: T.err(), stats: [...document.querySelectorAll("#daily .stat")].map(e => e.innerText) }`);
check("build list: 92 flagged, 45/47, 27/18, IST 15 · US 10 · SEA 2",
  !v.err && v.stats.join("|") === "92|45 / 47|27 / 18|IST_SHIFT 15 · US_SHIFT 10 · SEA_SHIFT 2", JSON.stringify(v));
v = await ev(`const s = document.getElementById("repSel"); s.value = "AD-07"; s.onchange({ target: s });
  return [...document.querySelectorAll("#daily tbody tr")].slice(0, 2).map(tr => [...tr.cells].slice(0, 5).map(c => c.innerText.replace(/\\n/g, " ")))`);
check("rep AD-07 top rows match README", v[0][0].startsWith("L104265") && v[0][2].startsWith("Wed 15 Jul, 16:13") && v[0][3] === "0.2 h"
  && v[1][0].startsWith("L102531") && v[1][4] === "Fri 17 Jul, 10:38", JSON.stringify(v));
v = await ev(`const rows = [...document.querySelectorAll("#daily tbody tr")]; return rows.length`);
check("rep view shows only this rep's rescue rows", v > 0, v + " rows");
await shot("01_daily_list");

// 4. log an outcome
v = await ev(`const sel = document.querySelector("select[data-lead='L104265']"); sel.value = "moved_before_deadline"; sel.onchange();
  return { info: document.getElementById("logInfo").innerText, stored: JSON.parse(localStorage.getItem("rescueOutcomes.v1")).L104265 }`);
check("picking an outcome saves it with a timestamp", v.stored?.outcome === "moved_before_deadline" && /^2026-07-15 09:0\d$/.test(v.stored.logged_at), JSON.stringify(v));

// 5. threshold edited after the build must not break logging (bug B9)
v = await ev(`document.getElementById("threshold").value = ""; const sel = document.querySelector("select[data-lead='L102531']");
  sel.value = "no_answer"; sel.onchange(); return { err: T.err(), stat: document.querySelector("#daily .stat + .muted").innerText }`);
check("blank threshold after build: logging still works, header keeps 48h", !v.err && /48h/.test(v.stat), JSON.stringify(v));
await ev(`document.getElementById("threshold").value = "48"; return 1`);

// 6. outcome log merge: an older log must not overwrite a newer in-browser outcome (bug B8)
v = await ev(`await T.setFile("logFile", "old.csv", "lead_id,outcome,logged_at\\nL104265,no_answer,2026-07-14 09:00\\n");
  await T.click("runBtn"); return JSON.parse(localStorage.getItem("rescueOutcomes.v1")).L104265.outcome`);
check("loading an older outcome log keeps the newer outcome", v === "moved_before_deadline", v);

// 7. simulated demo log + summary tab
v = await ev(`await T.fileFrom("logFile", "sample/rescue_outcomes_demo.csv"); await T.click("runBtn");
  document.querySelector("[data-tab=summary]").click();
  return { daily: T.text("daily").includes("SIMULATED"), summary: T.text("summary") }`);
check("demo log loads, SIMULATED warning shown, summary tab renders", v.daily && /By shift/.test(v.summary) && /By rep/.test(v.summary), v.summary.slice(0, 160).replace(/\n/g, " | "));
await shot("02_summary");

// 8. measurement
v = await ev(`T.clearFile("logFile"); document.querySelector("[data-tab=measure]").click(); await T.click("measureBtn"); return T.text("measureOut")`);
check("measurement tab runs and gives a verdict", /Verdict:/.test(v) && /Rescue \(odd ID\)\s+629/.test(v) && /Control \(even ID\)\s+656/.test(v), v.split("\n").slice(0, 6).join(" | "));
await shot("03_measurement");
v = await ev(`localStorage.removeItem("rescueOutcomes.v1"); document.getElementById("clearLog").click(); document.getElementById("clearLog").click();
  await T.click("measureBtn"); return T.text("measureOut").split("\\n")[0]`);
check("no outcomes → A/A verdict", /A\/A check/.test(v), v);

// 9. clear needs two clicks (bug B13)
v = await ev(`const sel = document.querySelector("#daily select[data-lead]"); sel.value = "no_answer"; sel.onchange();
  document.getElementById("clearLog").click(); const after1 = Object.keys(JSON.parse(localStorage.getItem("rescueOutcomes.v1"))).length;
  document.getElementById("clearLog").click(); const after2 = Object.keys(JSON.parse(localStorage.getItem("rescueOutcomes.v1"))).length;
  return [after1, after2]`);
check("'Clear saved outcomes' needs a second click", v[0] === 1 && v[1] === 0, JSON.stringify(v));

// 10. invalid inputs
T_bad: {
  const cases = [
    ["missing columns", "lead_id,created_at\nL1,2026-07-14 09:00\n", /Missing column\(s\): demo_scheduled_at/],
    ["semicolon CSV", HDR.replace(/,/g, ";") + "\nx\n", /semicolon/],
    ["empty file", "", /empty/],
    ["header only", HDR + "\n", /no data rows/],
    ["unclosed quote", HDR + '\n"L1,x\n', /unclosed quote/],
  ];
  for (const [name, text, re] of cases) {
    v = await ev(`T.clearFile("logFile"); await T.setFile("exportFile", "x.csv", ${JSON.stringify(text)}); await T.click("runBtn"); return T.err()`);
    check(`invalid export (${name}) → readable error`, re.test(v), v);
  }
  v = await ev(`await T.setFile("exportFile", "x.csv", ${JSON.stringify(HDR + "\nL1,x,USA,UTC,not-a-date,2026-07-20 09:00,AD-01,US_SHIFT,0,,,\nL3,x,USA,Mars/Base,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,\n")});
    document.getElementById("asOf").value = "2026-07-15T09:00"; await T.click("runBtn"); return { err: T.err(), daily: T.text("daily") }`);
  check("bad date row skipped and reported, unknown timezone labelled", !v.err && /1 row\(s\) need attention: line 2 L1/.test(v.daily) && /unknown timezone Mars\/Base/.test(v.daily), v.daily.slice(0, 300).replace(/\n/g, " | "));
  v = await ev(`document.getElementById("threshold").value = "-5"; await T.click("runBtn"); const e = T.err(); document.getElementById("threshold").value = "48"; return e`);
  check("negative threshold → readable error", /positive number/.test(v), v);
  v = await ev(`await T.setFile("logFile", "log.csv", "lead,outcome\\nL1,x\\n"); await T.click("runBtn"); const e = T.err(); T.clearFile("logFile"); return e`);
  check("bad outcome log → message names the outcome log (not the CRM export)", /outcome log with columns/.test(v), v);
}

// 11. XSS: CRM text is rendered as text
v = await ev(`await T.setFile("exportFile", "x.csv", ${JSON.stringify(HDR + '\nL1,x,"<img src=x onerror=window.__xss=1>",UTC,2026-07-14 09:00,2026-07-17 09:00,"<b>AD-01</b>",US_SHIFT,0,,,\n')});
  await T.click("runBtn"); await new Promise(r => setTimeout(r, 300));
  return { xss: window.__xss === 1, imgs: document.querySelectorAll("#daily img").length, shown: T.text("daily").includes("<img src=x") }`);
check("HTML in CSV fields is shown as text, never executed", !v.xss && v.imgs === 0 && v.shown, JSON.stringify(v));

// 12. phone width: no horizontal page scroll
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
v = await ev(`await T.fileFrom("exportFile", "sample/case_export.csv"); await T.click("runBtn"); document.querySelector("[data-tab=daily]").click();
  await new Promise(r => setTimeout(r, 200)); return [document.documentElement.scrollWidth, innerWidth]`);
check("phone width (390px): no horizontal page scroll", v[0] <= v[1], JSON.stringify(v));
await shot("04_phone");

// 13. privacy: nothing leaves the machine
const external = requests.filter((u) => !u.startsWith("http://127.0.0.1:8765/") && !u.startsWith("data:") && !u.startsWith("blob:"));
check("no network requests except the page's own files", external.length === 0, external.join(", ") || `${new Set(requests).size} local URLs`);
check("no uncaught JS errors during the run", errors.length === 0, errors.join(" / "));

console.log(`\n${results.filter((r) => r.ok).length}/${results.length} passed. Screenshots: ${SCR}`);
ws.close(); chrome.kill(); server.close();
process.exit(results.every((r) => r.ok) ? 0 : 1);
