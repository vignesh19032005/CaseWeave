"use client";

// A small, safe Markdown renderer for the case report: headings, paragraphs, bullet and numbered lists, block quotes, rules, tables,
// **bold**, *italic* and `code`. It builds React elements only (no raw HTML), so text from evidence or a model can never inject markup.
import React from "react";

function inline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("`")) out.push(<code key={key} className="px-1 py-0.5 rounded bg-zinc-100 text-zinc-800 text-[0.85em] font-mono break-all">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={key} className="font-semibold text-zinc-900">{inline(tok.slice(2, -2), key)}</strong>);
    else out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "ul"; items: string[] }
  | { t: "ol"; items: string[] }
  | { t: "quote"; text: string }
  | { t: "hr" }
  | { t: "table"; head: string[]; rows: string[][] };

function parse(md: string): Block[] {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  const cells = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { blocks.push({ t: "h", level: h[1].length, text: h[2] }); i++; continue; }
    if (/^---+\s*$/.test(line)) { blocks.push({ t: "hr" }); i++; continue; }
    if (/^\s*>/.test(line)) {
      const q: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      blocks.push({ t: "quote", text: q.join(" ") });
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(cells(lines[i])); i++; }
      blocks.push({ t: "table", head, rows });
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length && !/^\s*>/.test(lines[i])))) {
        if (/^\s*[-*]\s+/.test(lines[i])) items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      // an indented block quote right after an item belongs to that item
      while (i < lines.length && /^\s+>/.test(lines[i]) && items.length) { items[items.length - 1] += " " + lines[i].replace(/^\s*>\s?/, "“") + "”"; i++; }
      blocks.push({ t: "ul", items });
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      blocks.push({ t: "ol", items });
      continue;
    }
    const para: string[] = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*[-*]\s+|\s*\d+[.)]\s+|\s*>|---+\s*$)/.test(lines[i])) { para.push(lines[i].trim()); i++; }
    blocks.push({ t: "p", text: para.join(" ") });
  }
  return blocks;
}

export default function Markdown({ text }: { text: string }) {
  const blocks = React.useMemo(() => parse(text), [text]);
  return (
    <div className="text-[14px] leading-relaxed text-zinc-700">
      {blocks.map((b, n) => {
        const k = `b${n}`;
        switch (b.t) {
          case "h":
            if (b.level === 1) return <h1 key={k} className="text-2xl font-bold text-zinc-900 border-b-2 border-indigo-600 pb-2 mb-4">{inline(b.text, k)}</h1>;
            if (b.level === 2) return <h2 key={k} className="text-lg font-bold text-indigo-900 border-b border-zinc-300 pb-1 mt-8 mb-3">{inline(b.text, k)}</h2>;
            return <h3 key={k} className="text-[15px] font-semibold text-zinc-900 mt-5 mb-2">{inline(b.text, k)}</h3>;
          case "p":
            return <p key={k} className="my-2">{inline(b.text, k)}</p>;
          case "ul":
            return <ul key={k} className="my-2 pl-5 list-disc space-y-1.5 marker:text-indigo-500">{b.items.map((it, j) => <li key={j}>{inline(it, `${k}-${j}`)}</li>)}</ul>;
          case "ol":
            return <ol key={k} className="my-2 pl-5 list-decimal space-y-1.5">{b.items.map((it, j) => <li key={j}>{inline(it, `${k}-${j}`)}</li>)}</ol>;
          case "quote":
            return <blockquote key={k} className="my-2 pl-3 border-l-4 border-indigo-300 text-zinc-600 italic">{inline(b.text, k)}</blockquote>;
          case "hr":
            return <hr key={k} className="my-5 border-zinc-300" />;
          case "table":
            return (
              <div key={k} className="my-3 overflow-x-auto">
                <table className="w-full text-[13px] border border-zinc-300">
                  <thead className="bg-zinc-100"><tr>{b.head.map((c, j) => <th key={j} className="text-left px-2 py-1.5 border-b border-zinc-300 font-semibold text-zinc-900">{inline(c, `${k}h${j}`)}</th>)}</tr></thead>
                  <tbody>{b.rows.map((r, j) => <tr key={j} className="odd:bg-white even:bg-zinc-50">{r.map((c, q) => <td key={q} className="px-2 py-1.5 border-b border-zinc-200 align-top">{inline(c, `${k}r${j}-${q}`)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
