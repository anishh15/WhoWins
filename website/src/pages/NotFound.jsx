import { Link } from 'react-router-dom'
import SeatChip from '../components/SeatChip'
import { useTitle } from '../lib/hooks'

export default function NotFound() {
  useTitle('Page not found')
  return (
    <section className="page flex min-h-[60vh] flex-col items-center justify-center py-20 text-center">
      <p className="flex gap-1.5" aria-hidden="true">
        {['S1', 'S2', 'S3', 'S4', 'S5'].map((s) => <SeatChip key={s} seat={s} size="lg" title={false} />)}
      </p>
      <h1 className="mt-6 text-4xl font-semibold tracking-tight">No seat sent this page</h1>
      <p className="mt-3 max-w-md text-soft">The address does not match any page on this site.</p>
      <Link to="/" className="btn-primary mt-8">Back to the home page</Link>
    </section>
  )
}
