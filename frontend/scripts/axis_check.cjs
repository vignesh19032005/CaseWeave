// Checks the "skip quiet periods" time axis. Run: node scripts/axis_check.cjs
const ts = require("typescript");
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "app", "scene", "sandboxSolver.ts"), "utf8");
const js = ts.transpileModule(src, { compilerOptions: { module: "commonjs", target: "es2020" } }).outputText;
const m = { exports: {} };
new Function("module", "exports", "require", js)(m, m.exports, require);
const { quietGaps, buildAxis, toDisplay, fromDisplay } = m.exports;

let failed = 0;
const ok = (cond, msg) => { if (!cond) { failed++; console.error("FAIL:", msg); } else console.log("ok  :", msg); };
const seg = (t0, t1) => ({ t0, t1, kind: "dwell", step: 0 });
const scn = (spans, total) => ({ plan: { total_duration_s: total, actors: spans.map((s, i) => ({ id: "a" + i, segments: s.map(([a, b]) => seg(a, b)) })) } });

// one person acts at the start, another an hour later
const s1 = scn([[[0, 10]], [[3900, 3990]]], 3990);
const g1 = quietGaps(s1);
ok(g1.length === 1 && g1[0].from === 10 && g1[0].to === 3900, "finds the 64 minute quiet stretch");
const ax = buildAxis(3990, g1);
ok(Math.abs(ax.display - (10 + 30 + 90)) < 1e-9, "playback clock is 10 s + 30 s of the gap + 90 s = 130 s");
ok(Math.abs(ax.skipped - (3890 - 30)) < 1e-9, "reports the skipped time");
ok(Math.abs(fromDisplay(ax, 10 + 15) - (10 + 15)) < 1e-9, "the first 15 s of the gap are played");
ok(Math.abs(fromDisplay(ax, 10 + 15.0001) - (3900 - 15)) < 0.01, "then it jumps to the last 15 s before the next action");
ok(Math.abs(fromDisplay(ax, 10 + 30) - 3900) < 1e-9, "and arrives exactly when the next action starts");
for (const t of [0, 5, 10, 20, 24.9, 3886, 3890, 3900, 3950, 3990]) ok(Math.abs(fromDisplay(ax, toDisplay(ax, t)) - t) < 1e-6, `round trip at t=${t}`);
ok(Math.abs(toDisplay(ax, 2000) - 25) < 1e-9, "a time inside the skipped middle maps to the break point");
let prev = -1, mono = true;
for (let t = 0; t <= 3990; t += 7) { const d = toDisplay(ax, t); if (d < prev - 1e-9) mono = false; prev = d; }
ok(mono, "the shortened clock never runs backwards");
ok(toDisplay(ax, 3990) === ax.display && fromDisplay(ax, ax.display) === 3990, "the end maps to the end");

// nothing to skip
const s2 = scn([[[0, 30]], [[35, 80]]], 80);
ok(quietGaps(s2).length === 0 && buildAxis(80, []).display === 80, "short pauses are left alone");
ok(Math.abs(fromDisplay(buildAxis(80, []), 42) - 42) < 1e-9, "with nothing skipped the clock is the plain one");

// a quiet stretch at the end, and one only just over the limit
const s3 = scn([[[0, 20]]], 200);
const g3 = quietGaps(s3);
ok(g3.length === 1 && g3[0].from === 20 && g3[0].to === 200, "a quiet stretch at the end is found");
const g4 = quietGaps(scn([[[0, 10]], [[45, 60]]], 60));
ok(g4.length === 0 || buildAxis(60, g4).skipped === 5, "a gap only just over the limit skips almost nothing");
ok(quietGaps(undefined).length === 0, "no scenario, no gaps");

process.exit(failed ? 1 : 0);
