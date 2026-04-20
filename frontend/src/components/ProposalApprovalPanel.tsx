import type { StrategyProposal } from '../types/features'

interface ProposalApprovalPanelProps {
  proposals: StrategyProposal[]
  onApprove: (id: number) => void
  onReject: (id: number) => void
  loading: boolean
}

export function ProposalApprovalPanel({
  proposals,
  onApprove,
  onReject,
  loading,
}: ProposalApprovalPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-400">Loading proposals...</div>
      </div>
    )
  }

  const pendingProposals = proposals.filter((p) => p.admin_decision === 'pending')

  if (pendingProposals.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-500">No pending proposals</div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {pendingProposals.map((proposal) => (
        <div
          key={proposal.id}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-6"
        >
          <div className="flex items-start justify-between gap-6">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-3">
                <h3 className="text-lg font-medium text-neutral-100">
                  {proposal.strategy_name}
                </h3>
                <span className="text-xs px-2 py-1 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                  Pending Review
                </span>
              </div>

              <div className="mb-4">
                <div className="text-sm text-neutral-400 mb-2">Expected Impact:</div>
                <div className="text-sm text-neutral-300">{proposal.expected_impact}</div>
              </div>

              <div className="mb-4">
                <div className="text-sm text-neutral-400 mb-2">Change Details:</div>
                <pre className="text-xs text-neutral-300 bg-neutral-950 border border-neutral-800 rounded p-3 overflow-x-auto">
                  {JSON.stringify(proposal.change_details, null, 2)}
                </pre>
              </div>

              <div className="text-xs text-neutral-500">
                Created: {new Date(proposal.created_at).toLocaleString()}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <button
                onClick={() => onApprove(proposal.id)}
                className="px-4 py-2 bg-green-500/10 text-green-400 border border-green-500/20 rounded hover:bg-green-500/20 transition-colors text-sm font-medium"
              >
                Approve
              </button>
              <button
                onClick={() => onReject(proposal.id)}
                className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded hover:bg-red-500/20 transition-colors text-sm font-medium"
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
