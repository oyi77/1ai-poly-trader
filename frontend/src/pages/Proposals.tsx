import { NavBar } from '../components/NavBar'
import { ProposalApprovalPanel } from '../components/ProposalApprovalPanel'
import { useProposals } from '../hooks/useProposals'

export default function Proposals() {
  const { proposals, loading, approve, reject } = useProposals()

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
          onApprove={approve}
          onReject={reject}
          loading={loading}
        />
      </div>
    </div>
  )
}
