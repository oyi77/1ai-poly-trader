import { NavBar } from '../components/NavBar'
import { ProposalApprovalPanel } from '../components/ProposalApprovalPanel'
import { useProposals } from '../hooks/useProposals'
import { useAuth } from '../hooks/useAuth'

export default function Proposals() {
  const { proposals, loading, approve, reject } = useProposals()
  const { isAuthenticated } = useAuth()

  return (
    <div className="min-h-screen bg-black text-neutral-100">
      <NavBar title="Strategy Proposals" />
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-neutral-100 mb-2">Strategy Proposals</h1>
          <p className="text-sm text-neutral-400">
            Review and approve AI-generated strategy adjustments
          </p>
        </div>
          <ProposalApprovalPanel
            proposals={proposals}
          onApprove={isAuthenticated ? approve : undefined}
          onReject={isAuthenticated ? reject : undefined}
          loading={loading}
          readOnly={!isAuthenticated}
        />
      </div>
    </div>
  )
}
