// UNFPA stage-2 "final-approve all" for the Bandhu records a manager already
// approved. Two clicks (arm, then confirm) because it finalises many records at
// once. The server re-checks every item through the same two-stage rules as a
// single approval and records each one under the reviewer who clicked, so this
// only saves clicks; it never widens who can approve what.
import { useState } from 'react'
import { CheckCheck } from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'

interface BulkItem {
  id: string
  model_type?: string
}

interface Props {
  items: BulkItem[]
  reviewerName: string
  onDone: () => void
}

interface BulkResult {
  requested: number
  approved: number
  skipped: { id: string; model_type?: string; detail: string }[]
}

export function BulkFinalApprove({ items, reviewerName, onDone }: Props) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)

  if (items.length === 0 && !message) return null

  const run = async () => {
    setBusy(true)
    setMessage('')
    try {
      const { data } = await api.post<BulkResult>(
        '/programs/pending-approvals/bulk-approve/',
        { items: items.map(({ id, model_type }) => ({ id, model_type })) },
      )
      const skippedNote = data.skipped.length
        ? ` ${data.skipped.length} left in the queue: ${data.skipped[0].detail}`
        : ''
      setIsError(data.skipped.length > 0)
      setMessage(`${data.approved} of ${data.requested} records approved.${skippedNote}`)
      onDone()
    } catch (err) {
      setIsError(true)
      setMessage(apiErrorMessage(err))
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }

  return (
    <div className="card" style={{
      margin: '-6px 0 18px', padding: '12px 20px', borderRadius: 14,
      display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
    }}>
      {items.length > 0 && !armed && (
        <button className="btn success" disabled={busy} onClick={() => setArmed(true)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <CheckCheck size={16} /> Final-approve all {items.length}
        </button>
      )}
      {armed && (
        <>
          <span style={{ fontSize: 14, color: 'var(--ink)' }}>
            Approve all {items.length} records as <b>{reviewerName}</b>? Each one
            is recorded under your name and released to the dashboard.
          </span>
          <button className="btn success" disabled={busy} onClick={run}>
            {busy ? 'Approving…' : `Yes, approve ${items.length}`}
          </button>
          <button className="btn ghost" disabled={busy} onClick={() => setArmed(false)}>
            Cancel
          </button>
        </>
      )}
      {message && (
        <span role="status" style={{
          fontSize: 13, fontWeight: 600,
          color: isError ? 'var(--rose, #e5484d)' : 'var(--ink-2)',
        }}>{message}</span>
      )}
    </div>
  )
}
