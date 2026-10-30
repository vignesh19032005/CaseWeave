"use client";

import { useMemo } from "react";
import * as React from "react";
import * as Fiber from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as Babel from "@babel/standalone";

/**
 * Compiles LLM-generated JSX (plain <mesh>/<boxGeometry>/... markup, no
 * imports) into a React element at runtime via Babel standalone, then
 * renders it inside the R3F Canvas. This is the same pattern live-code
 * playgrounds use (CodeSandbox, etc) — safe here because the JSX comes from
 * our own backend's LLM call (Stage 6), not untrusted public input. A real
 * production deployment would still sandbox/validate this before eval;
 * flagged here as a known tradeoff, acceptable for a demo where the source
 * is our own pipeline.
 */
function compileJsxToElement(jsx: string): React.ReactElement | null {
  try {
    // Defensive: the LLM occasionally emits stray import/export lines
    // despite the prompt forbidding them — those break `new Function`,
    // which can only evaluate a plain expression, not ESM syntax.
    const sanitized = jsx
      .split("\n")
      .filter((line) => !/^\s*(import|export)\b/.test(line))
      .join("\n");
    const wrapped = `<>${sanitized}</>`;
    // Babel 8's react preset defaults to the automatic runtime, which
    // injects `import { jsx } from "react/jsx-runtime"` — new Function can't
    // evaluate that. Classic runtime emits React.createElement calls instead.
    const result = Babel.transform(wrapped, {
      presets: [["react", { runtime: "classic" }]],
      sourceType: "script",
    });
    if (!result?.code) throw new Error("Babel produced no output");
    // Babel emits the fragment as an expression *statement* ("...;") — the
    // trailing semicolon is a syntax error inside `return ( ... )`.
    const expression = result.code.trim().replace(/;$/, "");
    const factory = new Function("React", `return (${expression})`);
    return factory(React);
  } catch (e) {
    console.error("Scene JSX compile error:", e);
    return null;
  }
}

export default function DynamicScene({ jsx }: { jsx: string }) {
  const element = useMemo(() => compileJsxToElement(jsx), [jsx]);

  if (!element) {
    return <div className="text-red-400 text-sm p-4">Scene failed to compile — see console.</div>;
  }

  return (
    <Fiber.Canvas camera={{ position: [6, 6, 6], fov: 50 }} style={{ height: 480, background: "#111318" }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 8, 5]} intensity={0.8} />
      <gridHelper args={[20, 20, "#333", "#222"]} />
      {element}
      <OrbitControls />
    </Fiber.Canvas>
  );
}
