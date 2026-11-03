export default function AiNotice() {
  return (
    <div role="note" data-testid="ai-notice" className="w-full bg-amber-950/70 border-b border-amber-900/70 text-amber-200 text-[11px] leading-snug px-4 py-1.5 text-center">
      <strong className="font-semibold">AI-assisted analysis.</strong> Everything here, including findings, scenarios, scores and any legal references, is drafted by AI models from the recorded evidence.
      It is a suggestion to help an investigator, not a finding of fact and not legal advice. Have a qualified person review and confirm it against the source evidence and the official texts before relying on it.
    </div>
  );
}
