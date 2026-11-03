// Checks seenAt(): who is seen at time t. Run: node scripts/vis_check.cjs
const ts = require("typescript"); const fs = require("fs"); const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "app", "scene", "sandboxSolver.ts"), "utf8");
const js = ts.transpileModule(src, { compilerOptions: { module: "commonjs", target: "es2020" } }).outputText;
const m = { exports: {} }; new Function("module", "exports", "require", js)(m, m.exports, require);
const { seenAt } = m.exports;
let failed = 0; const ok = (c, msg) => { if (!c) { failed++; console.error("FAIL:", msg); } else console.log("ok  :", msg); };
const vis = [
  { observer: "cam", person: "a", person_label: "Thief", kind: "camera", ranges: [[10, 20], [40, 50]], seen_for_s: 20 },
  { observer: "cam", person: "b", person_label: "Other", kind: "camera", ranges: [[15, 30]], seen_for_s: 15 },
  { observer: "wit", person: "a", person_label: "Thief", kind: "witness", ranges: [[0, 5]], seen_for_s: 5 },
];
ok(JSON.stringify(seenAt(vis, 5)) === JSON.stringify({ wit: ["Thief"] }), "only the witness sees at t=5");
ok(Object.keys(seenAt(vis, 7)).length === 0, "nobody is seen at t=7");
ok(JSON.stringify(seenAt(vis, 17).cam) === JSON.stringify(["Thief", "Other"]), "two people seen by the camera at t=17");
ok(JSON.stringify(seenAt(vis, 45)) === JSON.stringify({ cam: ["Thief"] }), "second range works");
ok(seenAt(vis, 10).cam.length === 1 && seenAt(vis, 20).cam.length === 2, "range ends are inclusive");
ok(Object.keys(seenAt(undefined, 5)).length === 0 && Object.keys(seenAt([], 5)).length === 0, "no data, nobody seen");
process.exit(failed ? 1 : 0);
