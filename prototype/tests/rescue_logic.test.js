// Tests for rescue_logic.js. Run with:  node --test prototype/tests/rescue_logic.test.js
// Uses only Node's built-in test runner (Node 18+). No npm packages.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const L = require("../rescue_logic.js");

const HEADER = "lead_id,lead_source,geography,parent_timezone,created_at,demo_scheduled_at,rep_assigned,rep_shift,follow_up_attempts,demo_joined,demo_completed,converted";
const csv = (...lines) => L.parseCsv([HEADER, ...lines].join("\n"));
const AS_OF = L.parseTime("2026-07-15 09:00");

// ------------------------------------------------------------------ CSV

test("parseCsv handles quotes, embedded commas, CRLF and a BOM", () => {
  const rows = L.parseCsv('﻿a,b\r\n"x, y","say ""hi"""\r\n3,4\r\n');
  assert.deepEqual(rows, [{ a: "x, y", b: 'say "hi"' }, { a: "3", b: "4" }]);
});

test("parseCsv rejects empty input and unclosed quotes", () => {
  assert.throws(() => L.parseCsv(""), /empty/);
  assert.throws(() => L.parseCsv('a\n"oops'), /unclosed quote/);
});

test("toCsv round-trips through parseCsv", () => {
  const rows = [{ a: 'he said "x, y"', b: "2" }];
  assert.deepEqual(L.parseCsv(L.toCsv(rows, ["a", "b"])), rows);
});

// ------------------------------------------------------------------ time and arm

test("parseTime reads the export format and rejects impossible dates", () => {
  assert.equal(L.parseTime("2026-07-15 09:00"), Date.UTC(2026, 6, 15, 9, 0));
  assert.equal(L.parseTime("2026-07-15T09:00"), Date.UTC(2026, 6, 15, 9, 0)); // <input type=datetime-local>
  assert.equal(L.parseTime("2026-02-30 09:00"), null);
  assert.equal(L.parseTime("15/07/2026"), null);
  assert.equal(L.parseTime(""), null);
});

test("formatLocal shows the parent's local time and falls back to UTC for an unknown zone", () => {
  const t = L.parseTime("2026-07-15 09:13");
  assert.equal(L.formatLocal(t, "Asia/Ho_Chi_Minh"), "Wed 15 Jul, 16:13");
  assert.equal(L.formatLocal(t, "Asia/Kolkata"), "Wed 15 Jul, 14:43");
  assert.match(L.formatLocal(t, "Mars/Olympus"), /^Wed 15 Jul, 09:13 \(UTC: unknown timezone/);
});

test("armFor uses the last digit: odd = RESCUE, even = CONTROL", () => {
  assert.equal(L.armFor("L102531"), "RESCUE");
  assert.equal(L.armFor("L102120"), "CONTROL");
  assert.equal(L.armFor("LXYZ"), null);
});

// ------------------------------------------------------------------ buildRescueList

test("buildRescueList applies each flag rule", () => {
  const rows = csv(
    "L1,x,USA,America/New_York,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,", // late, open: MOVE, rescue
    "L2,x,USA,America/New_York,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,", // same, even: CONTROL
    "L3,x,USA,America/New_York,2026-07-12 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,", // deadline passed: CONFIRM
    "L5,x,USA,America/New_York,2026-07-14 09:00,2026-07-16 09:00,AD-01,US_SHIFT,0,,,", // exactly 48h: not late
    "L7,x,USA,America/New_York,2026-07-10 09:00,2026-07-14 09:00,AD-01,US_SHIFT,0,,,", // demo already held
    "L9,x,USA,America/New_York,2026-07-15 10:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // created after as-of
    "L11,x,USA,America/New_York,2026-07-14 09:00,,AD-01,US_SHIFT,0,,,",               // never booked
  );
  const r = L.buildRescueList(rows, AS_OF);
  assert.deepEqual(r.flagged.map((x) => [x.lead_id, x.arm, x.action]),
    [["L1", "RESCUE", "MOVE"], ["L2", "CONTROL", "MOVE"], ["L3", "RESCUE", "CONFIRM"]]);
  const l1 = r.flagged[0];
  assert.equal(l1.deadline_utc, "2026-07-16 09:00");
  assert.equal(l1.hours_left, 24);
  assert.equal(l1.gap_h, 72);
  assert.equal(r.counts.openRescue, 1);
  assert.equal(r.problems.length, 0);
});

test("buildRescueList sorts MOVE before CONFIRM, then by deadline", () => {
  const rows = csv(
    "L1,x,USA,UTC,2026-07-12 09:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // CONFIRM
    "L3,x,USA,UTC,2026-07-14 09:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // MOVE, 24h left
    "L5,x,USA,UTC,2026-07-13 12:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // MOVE, 3h left
  );
  assert.deepEqual(L.buildRescueList(rows, AS_OF).flagged.map((x) => x.lead_id), ["L5", "L3", "L1"]);
});

test("buildRescueList respects a custom threshold", () => {
  const rows = csv("L1,x,USA,UTC,2026-07-14 09:00,2026-07-16 09:00,AD-01,US_SHIFT,0,,,"); // 48h gap
  assert.equal(L.buildRescueList(rows, AS_OF, {}, { lateThresholdH: 24 }).counts.flagged, 1);
});

test("buildRescueList reports bad rows instead of crashing, and rejects missing columns", () => {
  const rows = csv("L1,x,USA,UTC,not-a-date,2026-07-20 09:00,AD-01,US_SHIFT,0,,,");
  const r = L.buildRescueList(rows, AS_OF);
  assert.equal(r.flagged.length, 0);
  assert.equal(r.problems[0].line, 2);
  assert.throws(() => L.buildRescueList(L.parseCsv("lead_id,created_at\nL1,x"), AS_OF), /Missing column\(s\): demo_scheduled_at/);
  assert.throws(() => L.buildRescueList(rows, NaN), /not a valid date/);
});

test("buildRescueList carries outcomes from the log", () => {
  const rows = csv("L1,x,USA,UTC,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,");
  const r = L.buildRescueList(rows, AS_OF, { L1: { outcome: "no_answer", logged_at: "2026-07-15 09:30" } });
  assert.equal(r.flagged[0].status, "no_answer");
});

test("repView never shows control rows and puts TO DO first", () => {
  const flagged = [
    { lead_id: "L1", arm: "RESCUE", rep_assigned: "A", status: "no_answer" },
    { lead_id: "L2", arm: "CONTROL", rep_assigned: "A", status: "TO DO" },
    { lead_id: "L3", arm: "RESCUE", rep_assigned: "A", status: "TO DO" },
    { lead_id: "L5", arm: "RESCUE", rep_assigned: "B", status: "TO DO" },
  ];
  assert.deepEqual(L.repView(flagged, "A").map((r) => r.lead_id), ["L3", "L1"]);
});

// ------------------------------------------------------------------ summarise / outcome log

test("summarise counts worked-before-deadline and expiring rows", () => {
  const rows = csv(
    "L1,x,USA,UTC,2026-07-13 11:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // 2h left, not worked -> expiring
    "L3,x,USA,UTC,2026-07-14 09:00,2026-07-20 09:00,AD-01,US_SHIFT,0,,,", // worked in time
    "L5,x,USA,UTC,2026-07-13 10:00,2026-07-20 09:00,AD-02,US_SHIFT,0,,,", // worked after deadline
  );
  const outcomes = {
    L3: { outcome: "moved_before_deadline", logged_at: "2026-07-15 09:30" },
    L5: { outcome: "moved_after_deadline", logged_at: "2026-07-15 11:00" },
  };
  const s = L.summarise(L.buildRescueList(rows, AS_OF, outcomes).flagged, AS_OF);
  assert.deepEqual(s.expiringSoon.map((r) => r.lead_id), ["L1"]);
  assert.equal(s.byShift.US_SHIFT.due, 3);
  assert.equal(s.byShift.US_SHIFT.worked, 2);
  assert.equal(s.byShift.US_SHIFT.workedBeforeDeadline, 1);
  assert.equal(s.byRep["AD-02"].pctWorkedBeforeDeadline, 0);
});

test("readOutcomeLog keeps valid rows and reports unknown codes", () => {
  const { outcomes, problems } = L.readOutcomeLog(L.parseCsv(
    "lead_id,outcome,logged_at\nL1,no_answer,2026-07-15 09:10\nL3,called_twice,2026-07-15 09:20\nL5,cancelled,bad"));
  assert.deepEqual(Object.keys(outcomes), ["L1"]);
  assert.equal(problems.length, 2);
});

test("readOutcomeLog keeps the SIMULATED marker so the page can warn after a reload", () => {
  const { outcomes } = L.readOutcomeLog(L.parseCsv(
    "lead_id,outcome,logged_at,source\nL1,no_answer,2026-07-15 09:10,SIMULATED\nL3,cancelled,2026-07-15 09:20,"));
  assert.equal(outcomes.L1.source, "SIMULATED");
  assert.equal(outcomes.L3.source, undefined);
});

// ------------------------------------------------------------------ measure

test("diffCi matches a hand calculation", () => {
  const ci = L.diffCi(60, 100, 50, 100);
  assert.ok(Math.abs(ci.diff - 0.1) < 1e-12);
  assert.ok(Math.abs(ci.hi - ci.lo - 2 * 1.96 * Math.sqrt(0.24 / 100 + 0.25 / 100)) < 1e-12);
  assert.equal(L.diffCi(1, 0, 1, 1), null);
});

test("measure applies the pre-registered decision rule", () => {
  // 100 late demos per arm. Rescue joins 80, control joins 50.
  const lines = [];
  for (let i = 0; i < 200; i++) {
    const id = "L" + (1000 + i);            // even i -> even ID -> CONTROL
    const joined = i % 2 ? (i < 160 ? "Y" : "N") : (i < 100 ? "Y" : "N");
    lines.push(`${id},x,USA,UTC,2026-07-01 09:00,2026-07-05 09:00,AD-01,US_SHIFT,0,${joined},N,N`);
  }
  const rows = csv(...lines);
  const worked = {};
  rows.filter((r) => L.armFor(r.lead_id) === "RESCUE")
    .forEach((r) => { worked[r.lead_id] = { outcome: "moved_before_deadline", logged_at: "2026-07-02 09:00" }; });

  const m = L.measure(rows, worked);
  assert.equal(m.arms.RESCUE.n, 100);
  assert.equal(m.arms.RESCUE.rate, 0.8);
  assert.equal(m.arms.CONTROL.rate, 0.5);
  assert.equal(m.completion, 1);
  assert.equal(m.verdict.code, "SCALE");

  assert.equal(L.measure(rows, {}).verdict.code, "A_A");
  const late = {};
  Object.keys(worked).forEach((k) => { late[k] = { outcome: "no_answer", logged_at: "2026-07-04 09:00" }; });
  assert.equal(L.measure(rows, late).verdict.code, "INCONCLUSIVE");
});

test("measure leaves out demos without a result and honours the pilot window", () => {
  const rows = csv(
    "L1,x,USA,UTC,2026-07-01 09:00,2026-07-05 09:00,AD-01,US_SHIFT,0,,N,N",   // no result yet
    "L3,x,USA,UTC,2026-07-01 09:00,2026-07-05 09:00,AD-01,US_SHIFT,0,Y,N,N",
    "L5,x,USA,UTC,2026-06-01 09:00,2026-06-05 09:00,AD-01,US_SHIFT,0,Y,N,N",  // before the window
  );
  const m = L.measure(rows, {}, { from: L.parseTime("2026-07-01 00:00") });
  assert.equal(m.skippedNoResult, 1);
  assert.equal(m.arms.RESCUE.n, 1);
});

// ------------------------------------------------------------------ Phase 10 QA regressions

test("parseTime rejects out-of-range minutes, seconds and hours instead of rolling over", () => {
  assert.equal(L.parseTime("2026-07-15 10:75"), null);
  assert.equal(L.parseTime("2026-07-15 10:00:99"), null);
  assert.equal(L.parseTime("2026-07-15 24:00"), null);
  assert.equal(L.parseTime("2026-07-15 23:59:59"), Date.UTC(2026, 6, 15, 23, 59, 59));
});

test("a MOVE row with minutes left never shows 0.0 h", () => {
  const r = L.buildRescueList(csv("L1,x,USA,UTC,2026-07-13 09:02,2026-07-17 09:00,AD-01,US_SHIFT,0,,,"), AS_OF).flagged[0];
  assert.equal(r.action, "MOVE");
  assert.equal(r.hours_left, 0.1);
});

test("duplicate lead IDs are listed once and reported", () => {
  const line = "L1,x,USA,UTC,2026-07-14 09:00,2026-07-17 09:00,AD-01,US_SHIFT,0,,,";
  const r = L.buildRescueList(csv(line, line), AS_OF);
  assert.equal(r.counts.flagged, 1);
  assert.match(r.problems[0].reason, /duplicate/);
});

test("a missing timezone is labelled, not shown in the machine's zone", () => {
  assert.match(L.formatLocal(AS_OF, ""), /timezone missing/);
});

test("outcome log: bad lead IDs rejected, control leads flagged, right error message", () => {
  const { outcomes, problems } = L.readOutcomeLog(L.parseCsv(
    "lead_id,outcome,logged_at\n__proto__,no_answer,2026-07-15 09:00\nL2,no_answer,2026-07-15 09:00"));
  assert.equal(Object.getPrototypeOf(outcomes), Object.prototype);
  assert.deepEqual(Object.keys(outcomes), ["L2"]);
  assert.deepEqual(problems.map((p) => p.lead_id), ["__proto__", "L2"]);
  assert.match(problems[1].reason, /CONTROL/);
  assert.throws(() => L.readOutcomeLog(L.parseCsv("lead,outcome\nL1,x")), /outcome log with columns/);
});

test("semicolon-separated exports get a hint", () => {
  assert.throws(() => L.buildRescueList(L.parseCsv(HEADER.replace(/,/g, ";") + "\nx"), AS_OF), /semicolon/);
});

test("mergeOutcomes keeps the later logged_at, whatever the load order", () => {
  const older = { L1: { outcome: "no_answer", logged_at: "2026-07-15 09:00" } };
  const newer = { L1: { outcome: "moved_before_deadline", logged_at: "2026-07-15 11:00" } };
  assert.equal(L.mergeOutcomes(newer, older).L1.outcome, "moved_before_deadline");
  assert.equal(L.mergeOutcomes(older, newer).L1.outcome, "moved_before_deadline");
});

test("toCsv neutralises spreadsheet formulas but leaves negative numbers alone", () => {
  assert.equal(L.toCsv([{ a: "=HYPERLINK(1)", b: -12.5 }], ["a", "b"]), "a,b\n'=HYPERLINK(1),-12.5\n");
});

// ------------------------------------------------------------------ acceptance on the case data (Phase 8 §10A)

test("case CSV reproduces the Phase 8 acceptance counts", () => {
  const rows = L.parseCsv(fs.readFileSync(path.join(__dirname, "..", "sample", "case_export.csv"), "utf8"));
  const r = L.buildRescueList(rows, AS_OF);
  assert.deepEqual(
    [r.counts.flagged, r.counts.move, r.counts.confirm, r.counts.openRescue, r.counts.openControl],
    [92, 45, 47, 27, 18]);
  assert.deepEqual(r.counts.openRescueByShift, { IST_SHIFT: 15, US_SHIFT: 10, SEA_SHIFT: 2 });

  const top = L.repView(r.flagged, "AD-07").slice(0, 2);
  assert.deepEqual(top.map((x) => [x.lead_id, x.deadline_local, x.hours_left, x.slot_local]), [
    ["L104265", "Wed 15 Jul, 16:13", 0.2, "Sat 18 Jul, 23:33"],
    ["L102531", "Wed 15 Jul, 22:54", 3.9, "Fri 17 Jul, 10:38"],
  ]);

  const m = L.measure(rows, {});
  assert.equal(m.arms.RESCUE.n, 629);
  assert.equal(m.arms.CONTROL.n, 656);
  assert.equal(m.arms.RESCUE.rate.toFixed(3), "0.464");
  assert.equal(m.arms.CONTROL.rate.toFixed(3), "0.474");
  assert.ok(m.ci.lo < 0 && m.ci.hi > 0, "A/A CI should span zero");
});
