import Rich from './Rich'

/** A finding in the paper's format: small-caps claim, bold sentence, short evidence, and more behind a toggle. */
export default function Insight({ claim, bold, evidence, details, number }) {
  return (
    <div>
      <p className="flex items-baseline gap-3">
        {number && <span className="font-serif text-sm font-semibold text-accent">{number}</span>}
        <span className="claim text-[1.35rem] leading-snug sm:text-[1.5rem]">{claim}</span>
      </p>
      <Rich as="p" text={`**${bold}**`} className="mt-3 text-[1.02rem] leading-relaxed text-ink" />
      {evidence && <Rich as="p" text={evidence} className="mt-3 leading-relaxed text-soft" />}
      {details && (
        <details className="group mt-4 rounded-xl border border-line bg-raised/60 px-4 py-2.5">
          <summary className="cursor-pointer select-none text-sm font-medium text-accent marker:text-accent">More from the paper</summary>
          {[details].flat().map((text) => <Rich key={text} as="p" text={text} className="mt-2 text-sm leading-relaxed text-soft" />)}
        </details>
      )}
    </div>
  )
}
