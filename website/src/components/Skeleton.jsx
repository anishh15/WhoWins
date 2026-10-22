/** A pulsing placeholder block (opacity only), sized by its classes so the layout does not jump. */
export function Bone({ className = '' }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-xl bg-tint/50 ${className}`} />
}

/** The shape of an inner page while its code loads: a header band and a few content blocks. */
export function PageSkeleton() {
  return (
    <div className="min-h-screen" role="status" aria-label="Loading the page">
      <div className="border-b border-line bg-gradient-to-b from-wash/70 to-bg">
        <div className="page space-y-4 py-12 sm:py-16">
          <Bone className="h-3 w-24" />
          <Bone className="h-10 w-full max-w-xl" />
          <Bone className="h-5 w-full max-w-2xl" />
        </div>
      </div>
      <div className="page mt-10 grid gap-5 lg:grid-cols-3">
        <Bone className="h-48" />
        <Bone className="h-48" />
        <Bone className="h-48" />
      </div>
    </div>
  )
}
