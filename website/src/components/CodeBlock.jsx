import CopyButton from './CopyButton'

/** A code sample with its language and a copy button; comments after # are dimmed; wrap breaks long lines. */
export default function CodeBlock({ code, lang = 'bash', title, wrap = false }) {
  const lines = code.split('\n')
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-raised">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
        <span className="font-mono text-[0.7rem] uppercase tracking-wider text-muted">{title || lang}</span>
        <CopyButton text={code} />
      </div>
      <pre tabIndex={0} aria-label={`${title || lang} code`} className={`overflow-x-auto px-4 py-3 font-mono text-[0.8rem] leading-relaxed text-ink ${wrap ? 'whitespace-pre-wrap break-words' : ''}`}>
        <code>
          {lines.map((line, i) => {
            const at = lang === 'bash' || lang === 'python' ? line.search(/(^|\s)#/) : -1
            return (
              <span key={i} className="block">
                {at < 0 ? line || ' ' : (
                  <>
                    {line.slice(0, at)}
                    <span className="text-muted">{line.slice(at)}</span>
                  </>
                )}
              </span>
            )
          })}
        </code>
      </pre>
    </div>
  )
}
