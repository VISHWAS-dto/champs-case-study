/*
 * Late-Demo Rescue Sheet — core logic (Phase 8 §5).
 *
 * Pure functions only: no DOM, no storage. The page (rescue_sheet.html) and the
 * tests (tests/rescue_logic.test.js) both load this file.
 *
 * Time convention: every timestamp in the CRM export ("YYYY-MM-DD HH:MM") is read
 * in the export clock, assumed UTC [A]. Internally times are epoch milliseconds.
 */
(function (root) {
  "use strict";

  const HOUR_MS = 3600 * 1000;

  const DEFAULT_SETTINGS = {
    lateThresholdH: 48, // Phase 4: the join-rate step sits at 48h after lead creation
    minMoveH: 3,        // MOVE only if at least this many hours remain before the deadline; else CONFIRM
    expiringSoonH: 4,   // shift-lead "expiring soon" window
    mwe: 0.03,          // minimum worthwhile effect for the decision rule (+3 pp J/S)
    minCompletion: 0.8, // adoption guardrail: share of rescue rows worked before their deadline
  };

  const OUTCOME_CODES = [
    "moved_before_deadline",
    "moved_after_deadline",
    "confirmed_as_is",
    "no_answer",
    "cancelled",
  ];

  // Columns the daily list needs. demo_joined is only needed by measure().
  const REQUIRED_COLUMNS = [
    "lead_id", "created_at", "demo_scheduled_at", "parent_timezone",
    "rep_assigned", "rep_shift", "geography",
  ];

  // ------------------------------------------------------------------ CSV

  /** Parse CSV text into an array of objects keyed by the header row. Handles quoted fields. */
  function parseCsv(text) {
    if (typeof text !== "string" || text.trim() === "") {
      throw new Error("The file is empty.");
    }
    text = text.replace(/^﻿/, ""); // Excel byte-order mark

    const records = [];
    let field = "";
    let record = [];
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') inQuotes = false;
        else field += c;
      } else if (c === '"') {
        inQuotes = true;
      } else if (c === ",") {
        record.push(field); field = "";
      } else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        record.push(field); field = "";
        records.push(record); record = [];
      } else {
        field += c;
      }
    }
    if (inQuotes) throw new Error("The CSV has an unclosed quote.");
    if (field !== "" || record.length) { record.push(field); records.push(record); }

    const nonEmpty = records.filter((r) => !(r.length === 1 && r[0].trim() === ""));
    const header = nonEmpty.shift().map((h) => h.trim());
    return nonEmpty.map((r) => {
      const row = {};
      header.forEach((h, j) => { row[h] = (r[j] || "").trim(); });
      return row;
    });
  }

  /** Turn an array of objects into CSV text (quotes fields that need it). */
  function toCsv(rows, columns) {
    const esc = (v) => {
      let s = v === null || v === undefined ? "" : String(v);
      if (/^[=+@\t\r]/.test(s)) s = "'" + s; // stop spreadsheets running CRM text as a formula
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return [columns.join(",")]
      .concat(rows.map((r) => columns.map((c) => esc(r[c])).join(",")))
      .join("\n") + "\n";
  }

  /** Throw a readable error if any required column is missing. */
  function checkColumns(rows, required, expected) {
    if (!rows.length) throw new Error("The file has a header but no data rows.");
    const missing = required.filter((c) => !(c in rows[0]));
    if (missing.length) {
      const semicolons = Object.keys(rows[0]).some((h) => h.includes(";"));
      throw new Error("Missing column(s): " + missing.join(", ") + ". Expected " +
        (expected || "the CRM export with the 12 case-file columns") + "." +
        (semicolons ? " The file looks semicolon-separated; save it as comma-separated CSV." : ""));
    }
  }

  // ------------------------------------------------------------------ time

  /** "YYYY-MM-DD HH:MM[:SS]" (or with a "T") in the export clock → epoch ms, or null. */
  function parseTime(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/.exec((s || "").trim());
    if (!m || +m[4] > 23 || +m[5] > 59 || +(m[6] || 0) > 59) return null;
    const t = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    const d = new Date(t);
    // Reject impossible dates such as 2026-02-30 (Date.UTC would roll them over).
    if (d.getUTCMonth() !== +m[2] - 1 || d.getUTCDate() !== +m[3]) return null;
    return t;
  }

  /** epoch ms → "YYYY-MM-DD HH:MM" in the export clock. */
  function formatTime(t) {
    return new Date(t).toISOString().slice(0, 16).replace("T", " ");
  }

  const formatterCache = {};
  /** epoch ms → "Wed 15 Jul, 16:13" in the given IANA timezone. Falls back to UTC if the zone is unknown. */
  function formatLocal(t, timeZone) {
    if (!timeZone) return formatLocal(t, "UTC") + " (UTC: timezone missing)";
    let fmt = formatterCache[timeZone];
    if (!fmt) {
      try {
        fmt = new Intl.DateTimeFormat("en-GB", {
          timeZone, weekday: "short", day: "numeric", month: "short",
          hour: "2-digit", minute: "2-digit", hourCycle: "h23",
        });
      } catch (e) {
        return formatLocal(t, "UTC") + " (UTC: unknown timezone " + timeZone + ")";
      }
      formatterCache[timeZone] = fmt;
    }
    const p = {};
    fmt.formatToParts(new Date(t)).forEach((x) => { p[x.type] = x.value; });
    return `${p.weekday} ${p.day} ${p.month}, ${p.hour}:${p.minute}`;
  }

  // ------------------------------------------------------------------ rules

  /** Holdout arm from the last digit of the lead ID: odd → RESCUE, even → CONTROL. */
  function armFor(leadId) {
    const m = /(\d)\D*$/.exec(leadId || "");
    if (!m) return null;
    return +m[1] % 2 === 1 ? "RESCUE" : "CONTROL";
  }

  /**
   * Build the day's rescue list (Phase 8 §5). THIS IS WHERE ALL THE RULES LIVE.
   *
   * @param rows      parsed CRM export rows
   * @param asOf      epoch ms of "now" in the export clock
   * @param outcomes  { lead_id: {outcome, logged_at} } from the outcome log (optional)
   * @returns { flagged: [...], problems: [...], counts: {...} }
   */
  function buildRescueList(rows, asOf, outcomes, settings) {
    const s = Object.assign({}, DEFAULT_SETTINGS, settings || {});
    outcomes = outcomes || {};
    checkColumns(rows, REQUIRED_COLUMNS);
    if (typeof asOf !== "number" || isNaN(asOf)) throw new Error("'Run as of' time is not a valid date.");

    const flagged = [];
    const problems = [];
    const seen = new Set();

    rows.forEach((row, i) => {
      const line = i + 2; // +1 for the header, +1 for 1-based line numbers
      if (!row.demo_scheduled_at) return;                        // never booked
      if (seen.has(row.lead_id)) {
        problems.push({ line, lead_id: row.lead_id, reason: "duplicate lead_id (first row kept)" });
        return;
      }
      seen.add(row.lead_id);
      const created = parseTime(row.created_at);
      const demo = parseTime(row.demo_scheduled_at);
      if (created === null || demo === null) {
        problems.push({ line, lead_id: row.lead_id, reason: "unreadable created_at or demo_scheduled_at" });
        return;
      }
      if (created > asOf) return;                               // lead not yet created at this time
      const gapH = (demo - created) / HOUR_MS;
      if (gapH <= s.lateThresholdH) return;                     // not late
      if (demo <= asOf) return;                                 // already held; nothing to rescue
      const arm = armFor(row.lead_id);
      if (!arm) {
        problems.push({ line, lead_id: row.lead_id, reason: "lead_id has no digit to assign an arm" });
        return;
      }

      const deadline = created + s.lateThresholdH * HOUR_MS;
      const hoursLeft = (deadline - asOf) / HOUR_MS;
      const logged = outcomes[row.lead_id];

      flagged.push({
        lead_id: row.lead_id,
        geography: row.geography,
        parent_timezone: row.parent_timezone,
        rep_assigned: row.rep_assigned,
        rep_shift: row.rep_shift,
        created_at: row.created_at,
        demo_scheduled_at: row.demo_scheduled_at,
        gap_h: round1(gapH),
        deadline_utc: formatTime(deadline),
        deadline_ms: deadline,
        hours_left: hoursLeft > 0 ? Math.max(round1(hoursLeft), 0.1) : round1(hoursLeft),
        // Too little time to book a new slot → confirm the current one instead (decided before rounding).
        action: hoursLeft >= s.minMoveH ? "MOVE" : "CONFIRM",
        arm,
        deadline_local: formatLocal(deadline, row.parent_timezone),
        slot_local: formatLocal(demo, row.parent_timezone),
        status: logged ? logged.outcome : "TO DO",
        logged_at: logged ? logged.logged_at : "",
      });
    });

    // MOVE before CONFIRM, then soonest deadline first.
    flagged.sort((a, b) =>
      (a.action === b.action ? 0 : a.action === "MOVE" ? -1 : 1) || a.deadline_ms - b.deadline_ms);

    const open = flagged.filter((r) => r.action === "MOVE");
    const openRescue = open.filter((r) => r.arm === "RESCUE");
    return {
      flagged,
      problems,
      counts: {
        flagged: flagged.length,
        move: open.length,
        confirm: flagged.length - open.length,
        openRescue: openRescue.length,
        openControl: open.length - openRescue.length,
        openRescueByShift: countBy(openRescue, "rep_shift"),
      },
    };
  }

  /** The rows one rep works: rescue arm only (control is never shown). Rows still TO DO come first. */
  function repView(flagged, rep) {
    return flagged
      .filter((r) => r.arm === "RESCUE" && (!rep || r.rep_assigned === rep))
      .sort((a, b) => (a.status === "TO DO" ? 0 : 1) - (b.status === "TO DO" ? 0 : 1));
  }

  /** Shift-lead summary per shift and per rep, plus rows expiring soon that nobody has worked. */
  function summarise(flagged, asOf, settings) {
    const s = Object.assign({}, DEFAULT_SETTINGS, settings || {});
    const rescue = flagged.filter((r) => r.arm === "RESCUE");

    const group = (key) => {
      const out = {};
      rescue.forEach((r) => {
        const g = out[r[key]] || (out[r[key]] = { due: 0, worked: 0, workedBeforeDeadline: 0, byOutcome: {} });
        g.due++;
        if (r.status !== "TO DO") {
          g.worked++;
          g.byOutcome[r.status] = (g.byOutcome[r.status] || 0) + 1;
          if (workedBeforeDeadline(r)) g.workedBeforeDeadline++;
        }
      });
      Object.values(out).forEach((g) => { g.pctWorkedBeforeDeadline = g.due ? g.workedBeforeDeadline / g.due : 0; });
      return out;
    };

    const expiringSoon = rescue.filter((r) =>
      r.status === "TO DO" && r.action === "MOVE" && (r.deadline_ms - asOf) / HOUR_MS <= s.expiringSoonH);

    return { byShift: group("rep_shift"), byRep: group("rep_assigned"), expiringSoon };
  }

  function workedBeforeDeadline(r) {
    const t = parseTime(r.logged_at);
    return t !== null && t <= r.deadline_ms;
  }

  // ------------------------------------------------------------------ first-seen register

  /**
   * Record, for every flagged row (BOTH arms), when it first appeared on a list and whether it was
   * MOVE-eligible then. Existing entries are never overwritten. The register fixes each lead's arm and
   * stratum at first listing, so a demo that is later moved (and no longer looks late in the CRM) still
   * counts in its arm. Returns a new map.
   */
  function recordFirstSeen(register, flagged, asOf) {
    const out = Object.assign({}, register || {});
    flagged.forEach((r) => {
      if (!Object.prototype.hasOwnProperty.call(out, r.lead_id)) {
        out[r.lead_id] = { first_seen_at: formatTime(asOf), first_action: r.action, arm: r.arm };
      }
    });
    return out;
  }

  // ------------------------------------------------------------------ measurement

  /** Two-proportion difference with a 95% CI (normal approximation, as in Phase 4). */
  function diffCi(j1, n1, j2, n2) {
    if (!n1 || !n2) return null;
    const p1 = j1 / n1, p2 = j2 / n2;
    const se = Math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2);
    const d = p1 - p2;
    return { diff: d, lo: d - 1.96 * se, hi: d + 1.96 * se };
  }

  /**
   * Weekly readout. Intent-to-treat: every listed late demo counts in its arm, whatever its call outcome.
   *
   * With a first-seen register the population is every lead in the register (arm and stratum fixed at
   * first listing), and the PRIMARY analysis is the MOVE-eligible stratum. Without one (e.g. historical
   * data, where nobody was called) the population falls back to late demos in the export, all counted.
   *
   * @param rows       a LATER export with demo_joined filled in (Y/N)
   * @param outcomes   { lead_id: {outcome, logged_at} }
   * @param window     optional { from, to } epoch ms on created_at (the pilot period)
   * @param settings   optional overrides of DEFAULT_SETTINGS
   * @param firstSeen  optional { lead_id: {first_seen_at, first_action, arm} } from recordFirstSeen
   */
  function measure(rows, outcomes, window, settings, firstSeen) {
    const s = Object.assign({}, DEFAULT_SETTINGS, settings || {});
    outcomes = outcomes || {};
    firstSeen = firstSeen || {};
    checkColumns(rows, ["lead_id", "created_at", "demo_scheduled_at", "demo_joined"]);
    window = window || {};
    const useRegister = Object.keys(firstSeen).length > 0;

    const newGroup = () => ({ RESCUE: { n: 0, joined: 0 }, CONTROL: { n: 0, joined: 0 } });
    const all = newGroup();
    const eligible = newGroup();
    const byOutcome = {};
    let workedInTime = 0;
    let rescuePrimary = 0;
    let skippedNoResult = 0;
    const seen = new Set();

    rows.forEach((row) => {
      if (seen.has(row.lead_id)) return; // duplicates: first row counts, as in the daily list
      seen.add(row.lead_id);
      const created = parseTime(row.created_at);
      if (created === null) return;
      if (window.from !== undefined && created < window.from) return;
      if (window.to !== undefined && created > window.to) return;
      const reg = useRegister && Object.prototype.hasOwnProperty.call(firstSeen, row.lead_id)
        ? firstSeen[row.lead_id] : null;
      if (useRegister) {
        if (!reg) return;                                     // never listed: not in the pilot
      } else {
        const demo = parseTime(row.demo_scheduled_at);
        if (demo === null || (demo - created) / HOUR_MS <= s.lateThresholdH) return;
      }
      const joined = (row.demo_joined || "").toUpperCase();
      if (joined !== "Y" && joined !== "N") { skippedNoResult++; return; } // demo not yet held
      const arm = armFor(row.lead_id);
      if (!arm) return;

      const isJoined = joined === "Y" ? 1 : 0;
      all[arm].n++;
      all[arm].joined += isJoined;
      const primary = !useRegister || reg.first_action === "MOVE";
      if (useRegister && primary) { eligible[arm].n++; eligible[arm].joined += isJoined; }

      if (arm === "RESCUE" && primary) {
        rescuePrimary++;
        const o = outcomes[row.lead_id];
        const code = o ? o.outcome : "not_logged";
        const g = byOutcome[code] || (byOutcome[code] = { n: 0, joined: 0 });
        g.n++; g.joined += isJoined;
        const t = o ? parseTime(o.logged_at) : null;
        if (t !== null && t <= created + s.lateThresholdH * HOUR_MS) workedInTime++;
      }
    });

    const rate = (g) => (g.n ? g.joined / g.n : null);
    const finish = (arms) => {
      Object.values(arms).forEach((g) => { g.rate = rate(g); });
      return { arms, ci: diffCi(arms.RESCUE.joined, arms.RESCUE.n, arms.CONTROL.joined, arms.CONTROL.n) };
    };
    Object.values(byOutcome).forEach((g) => { g.rate = rate(g); });
    const secondary = finish(all);
    const primary = useRegister ? finish(eligible) : secondary;
    const completion = rescuePrimary ? workedInTime / rescuePrimary : 0;
    const anyLogged = Object.keys(byOutcome).some((k) => k !== "not_logged");

    return {
      stratum: useRegister ? "MOVE_ELIGIBLE" : "ALL_LATE",
      arms: primary.arms, ci: primary.ci,      // primary analysis
      allLate: secondary,                      // secondary: every listed late demo
      byOutcome, completion, skippedNoResult,
      verdict: verdict(primary.ci, completion, anyLogged, s),
    };
  }

  /** Pre-registered decision rule: minimum worthwhile effect (MWE) +3 pp, adoption guardrail 80%. */
  function verdict(ci, completion, anyLogged, settings) {
    const s = Object.assign({}, DEFAULT_SETTINGS, settings || {});
    const mwe = "+" + Math.round(s.mwe * 100) + " pp";
    if (!ci) return { code: "NO_DATA", text: "Not enough late demos with a result in both arms." };
    if (!anyLogged) {
      return { code: "A_A", text: "No outcomes logged: this is an A/A check. The arms should match (CI spans 0)." };
    }
    if (completion < s.minCompletion) {
      return { code: "INCONCLUSIVE", text: `Inconclusive: fewer than ${Math.round(s.minCompletion * 100)}% of rescue rows were worked before their deadline. Fix adoption first.` };
    }
    if (ci.lo > 0) return { code: "SCALE", text: "Scale: the lower end of the 95% CI is above 0." };
    if (ci.hi < s.mwe) return { code: "STOP", text: `Stop: the upper end of the 95% CI is below the minimum worthwhile effect (${mwe}).` };
    return { code: "EXTEND", text: `Extend the pilot: the 95% CI includes 0 and still reaches above ${mwe}.` };
  }

  // ------------------------------------------------------------------ outcome log

  const OUTCOME_LOG_COLUMNS = ["lead_id", "outcome", "logged_at"];

  /** Outcome-log rows → { lead_id: {outcome, logged_at} }. Rows with unknown codes are reported, not kept. */
  function readOutcomeLog(rows) {
    checkColumns(rows, OUTCOME_LOG_COLUMNS, "an outcome log with columns " + OUTCOME_LOG_COLUMNS.join(", "));
    const map = {};
    const problems = [];
    rows.forEach((r, i) => {
      const arm = armFor(r.lead_id);
      if (!arm) {
        problems.push({ line: i + 2, lead_id: r.lead_id, reason: "lead_id has no digit" });
      } else if (!OUTCOME_CODES.includes(r.outcome)) {
        problems.push({ line: i + 2, lead_id: r.lead_id, reason: "unknown outcome '" + r.outcome + "'" });
      } else if (parseTime(r.logged_at) === null) {
        problems.push({ line: i + 2, lead_id: r.lead_id, reason: "unreadable logged_at" });
      } else {
        map[r.lead_id] = { outcome: r.outcome, logged_at: r.logged_at }; // later rows win
        if (r.source) map[r.lead_id].source = r.source; // e.g. SIMULATED demo data
        if (arm === "CONTROL") {
          // Kept (intent-to-treat), but a control lead was called: the holdout is contaminated.
          problems.push({ line: i + 2, lead_id: r.lead_id, reason: "CONTROL lead was worked (holdout contamination; kept)" });
        }
      }
    });
    return { outcomes: map, problems };
  }

  /** Merge outcome maps: for each lead the entry with the later logged_at wins (ties go to `incoming`). */
  function mergeOutcomes(current, incoming) {
    const out = Object.assign({}, current);
    Object.keys(incoming).forEach((id) => {
      const a = out[id], b = incoming[id];
      if (!a || (parseTime(b.logged_at) || 0) >= (parseTime(a.logged_at) || 0)) out[id] = b;
    });
    return out;
  }

  // ------------------------------------------------------------------ helpers

  function round1(x) { return Math.round(x * 10) / 10; }

  function countBy(rows, key) {
    const out = {};
    rows.forEach((r) => { out[r[key]] = (out[r[key]] || 0) + 1; });
    return out;
  }

  const api = {
    DEFAULT_SETTINGS, OUTCOME_CODES, REQUIRED_COLUMNS, OUTCOME_LOG_COLUMNS,
    parseCsv, toCsv, parseTime, formatTime, formatLocal, armFor,
    buildRescueList, repView, summarise, recordFirstSeen, measure, verdict, diffCi, readOutcomeLog, mergeOutcomes,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RescueLogic = api;
})(this);
