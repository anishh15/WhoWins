/** A plain, accessible table: columns are [label, render(row), align?]. */
export default function DataTable({ caption, columns, rows, rowKey }) {
  return (
    <div tabIndex={0} role="region" aria-label={caption} className="max-h-[28rem] overflow-auto rounded-xl border border-line">
      <table className="w-full border-collapse text-left text-[0.8rem]">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 bg-raised">
          <tr>
            {columns.map(([label, , align]) => (
              <th key={label} scope="col" className={`border-b border-line px-3 py-2 font-semibold text-soft ${align === 'right' ? 'text-right' : ''}`}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line/70 last:border-0">
              {columns.map(([label, render, align]) => (
                <td key={label} className={`px-3 py-1.5 text-ink ${align === 'right' ? 'num text-right' : ''}`}>{render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
