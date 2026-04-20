import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { StrategyProposal } from '../types/features'
import { adminApi, getWsUrl } from '../api'

interface ProposalApprovalUIProps {
  isAdmin: boolean
}

interface ApprovalHistory {
  proposal_id: number
  admin_user_id: string
  decision: 'approved' | 'rejected'
  reason: string
  timestamp: string
}

interface ConfirmDialogState {
  open: boolean
  type: 'approve' | 'reject' | null
  proposalId: number | null
  proposalName: string
}

export function ProposalApprovalUI({ isAdmin }: ProposalApprovalUIProps) {
  const queryClient = useQueryClient()
  const [selectedProposal, setSelectedProposal] = useState<number | null>(null)
  const [approvalReason, setApprovalReason] = useState('')
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState>({
    open: false,
    type: null,
    proposalId: null,
    proposalName: '',
  })
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const {
    data: proposals = [],
    isLoading,
    error: queryError,
  } = useQuery<StrategyProposal[]>({
    queryKey: ['proposals', 'pending'],
    queryFn: async () => {
      const response = await adminApi.get('/proposals', {
        params: { status: 'pending' },
      })
      return response.data
    },
    refetchInterval: 10000,
  })
  useEffect(() => {
    const wsUrl = getWsUrl('/ws/proposals')
    let ws: WebSocket | null = null
    let reconnectTimeout: NodeJS.Timeout | null = null
    let isClosed = false

    const connect = () => {
      if (isClosed) return

      try {
        ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          console.log('[ProposalApprovalUI] WebSocket connected')
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'proposal_update') {
              queryClient.invalidateQueries({ queryKey: ['proposals'] })
            }
          } catch (e) {
            console.error('[ProposalApprovalUI] Failed to parse WebSocket message:', e)
          }
        }

        ws.onerror = (error) => {
          console.error('[ProposalApprovalUI] WebSocket error:', error)
        }

        ws.onclose = () => {
          console.log('[ProposalApprovalUI] WebSocket closed')
          if (!isClosed) {
            reconnectTimeout = setTimeout(connect, 5000)
          }
        }
      } catch (e) {
        console.error('[ProposalApprovalUI] Failed to create WebSocket:', e)
        if (!isClosed) {
          reconnectTimeout = setTimeout(connect, 5000)
        }
      }
    }

    connect()

    return () => {
      isClosed = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) {
        ws.close()
      }
    }
  }, [queryClient])

  const openConfirmDialog = (type: 'approve' | 'reject', proposalId: number, proposalName: string) => {
    setConfirmDialog({
      open: true,
      type,
      proposalId,
      proposalName,
    })
  }

  const closeConfirmDialog = () => {
    setConfirmDialog({
      open: false,
      type: null,
      proposalId: null,
      proposalName: '',
    })
    setApprovalReason('')
  }

  const handleApprove = useCallback(async () => {
    if (!confirmDialog.proposalId || !approvalReason.trim()) {
      setActionError('Approval reason is required')
      return
    }

    setActionLoading(true)
    setActionError(null)

    try {
      await adminApi.post(`/proposals/${confirmDialog.proposalId}/approve`, {
        admin_user_id: 'admin',
        reason: approvalReason.trim(),
      })

      queryClient.invalidateQueries({ queryKey: ['proposals'] })
      closeConfirmDialog()
      setSelectedProposal(null)
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to approve proposal'
      setActionError(message)
    } finally {
      setActionLoading(false)
    }
  }, [confirmDialog.proposalId, approvalReason, queryClient])

  const handleReject = useCallback(async () => {
    if (!confirmDialog.proposalId || !approvalReason.trim()) {
      setActionError('Rejection reason is required')
      return
    }

    setActionLoading(true)
    setActionError(null)

    try {
      await adminApi.post(`/proposals/${confirmDialog.proposalId}/reject`, {
        admin_user_id: 'admin',
        reason: approvalReason.trim(),
      })

      queryClient.invalidateQueries({ queryKey: ['proposals'] })
      closeConfirmDialog()
      setSelectedProposal(null)
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to reject proposal'
      setActionError(message)
    } finally {
      setActionLoading(false)
    }
  }, [confirmDialog.proposalId, approvalReason, queryClient])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-400 text-sm">Loading proposals...</div>
      </div>
    )
  }

  if (queryError) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-red-400 text-sm">
          Error loading proposals: {queryError instanceof Error ? queryError.message : 'Unknown error'}
        </div>
      </div>
    )
  }

  const pendingProposals = proposals.filter((p) => p.admin_decision === 'pending')

  if (pendingProposals.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-500 text-sm">No pending proposals</div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {actionError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <div className="text-red-400 text-sm">{actionError}</div>
          <button
            onClick={() => setActionError(null)}
            className="text-xs text-red-300 hover:text-red-200 mt-2 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {pendingProposals.map((proposal) => (
        <ProposalCard
          key={proposal.id}
          proposal={proposal}
          isAdmin={isAdmin}
          isSelected={selectedProposal === proposal.id}
          onSelect={() => setSelectedProposal(proposal.id)}
          onApprove={() => openConfirmDialog('approve', proposal.id, proposal.strategy_name)}
          onReject={() => openConfirmDialog('reject', proposal.id, proposal.strategy_name)}
        />
      ))}

      {confirmDialog.open && (
        <ConfirmationDialog
          type={confirmDialog.type!}
          proposalName={confirmDialog.proposalName}
          reason={approvalReason}
          onReasonChange={setApprovalReason}
          onConfirm={confirmDialog.type === 'approve' ? handleApprove : handleReject}
          onCancel={closeConfirmDialog}
          loading={actionLoading}
          error={actionError}
        />
      )}
    </div>
  )
}

interface ProposalCardProps {
  proposal: StrategyProposal
  isAdmin: boolean
  isSelected: boolean
  onSelect: () => void
  onApprove: () => void
  onReject: () => void
}

function ProposalCard({ proposal, isAdmin, isSelected, onSelect, onApprove, onReject }: ProposalCardProps) {
  const [showDetails, setShowDetails] = useState(false)

  return (
    <div
      className={`bg-neutral-900 border rounded-lg p-6 transition-all ${
        isSelected ? 'border-blue-500/50 shadow-lg shadow-blue-500/10' : 'border-neutral-800'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <h3 className="text-lg font-medium text-neutral-100">{proposal.strategy_name}</h3>
            <span className="text-xs px-2 py-1 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
              Pending Review
            </span>
          </div>

          <div className="mb-4">
            <div className="text-sm text-neutral-400 mb-2">Expected Impact:</div>
            <div className="text-sm text-neutral-300">{proposal.expected_impact}</div>
          </div>

          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-neutral-400">Change Details:</div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setShowDetails(!showDetails)
                }}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                {showDetails ? 'Hide' : 'Show'} Details
              </button>
            </div>
            {showDetails && (
              <pre className="text-xs text-neutral-300 bg-neutral-950 border border-neutral-800 rounded p-3 overflow-x-auto">
                {JSON.stringify(proposal.change_details, null, 2)}
              </pre>
            )}
          </div>

          {proposal.impact_measured && (
            <ImpactMetrics impact={proposal.impact_measured} />
          )}

          <div className="flex items-center gap-4 text-xs text-neutral-500">
            <span>Created: {new Date(proposal.created_at).toLocaleString()}</span>
            {proposal.admin_user_id && (
              <span>Reviewed by: {proposal.admin_user_id}</span>
            )}
          </div>

          {proposal.admin_user_id && (
            <ApprovalHistory proposalId={proposal.id} />
          )}
        </div>

        {isAdmin && (
          <div className="flex flex-col gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation()
                onApprove()
              }}
              className="px-4 py-2 bg-green-500/10 text-green-400 border border-green-500/20 rounded hover:bg-green-500/20 transition-colors text-sm font-medium whitespace-nowrap"
            >
              Approve
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onReject()
              }}
              className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded hover:bg-red-500/20 transition-colors text-sm font-medium whitespace-nowrap"
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

interface ImpactMetricsProps {
  impact: Record<string, any>
}

function ImpactMetrics({ impact }: ImpactMetricsProps) {
  return (
    <div className="mb-4 p-4 bg-neutral-950 border border-neutral-800 rounded">
      <div className="text-sm text-neutral-400 mb-3">Impact Metrics:</div>
      <div className="grid grid-cols-2 gap-4">
        {Object.entries(impact).map(([key, value]) => (
          <div key={key}>
            <div className="text-xs text-neutral-500 mb-1">
              {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
            </div>
            <div className="text-sm text-neutral-200 font-mono">
              {typeof value === 'number' ? value.toFixed(2) : String(value)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface ApprovalHistoryProps {
  proposalId: number
}

function ApprovalHistory({ proposalId }: ApprovalHistoryProps) {
  const { data: history = [] } = useQuery<ApprovalHistory[]>({
    queryKey: ['proposal-history', proposalId],
    queryFn: async () => {
      const response = await adminApi.get(`/proposals/${proposalId}/history`)
      return response.data
    },
    enabled: !!proposalId,
  })

  if (history.length === 0) {
    return null
  }

  return (
    <div className="mt-4 pt-4 border-t border-neutral-800">
      <div className="text-sm text-neutral-400 mb-3">Approval History:</div>
      <div className="space-y-2">
        {history.map((entry, index) => (
          <div key={index} className="flex items-start gap-3 text-xs">
            <div
              className={`px-2 py-1 rounded ${
                entry.decision === 'approved'
                  ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                  : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}
            >
              {entry.decision}
            </div>
            <div className="flex-1">
              <div className="text-neutral-300">
                {entry.admin_user_id} • {new Date(entry.timestamp).toLocaleString()}
              </div>
              {entry.reason && <div className="text-neutral-500 mt-1">{entry.reason}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface ConfirmationDialogProps {
  type: 'approve' | 'reject'
  proposalName: string
  reason: string
  onReasonChange: (reason: string) => void
  onConfirm: () => void
  onCancel: () => void
  loading: boolean
  error: string | null
}

function ConfirmationDialog({
  type,
  proposalName,
  reason,
  onReasonChange,
  onConfirm,
  onCancel,
  loading,
  error,
}: ConfirmationDialogProps) {
  const isApprove = type === 'approve'

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-lg max-w-lg w-full p-6">
        <h3 className="text-lg font-medium text-neutral-100 mb-4">
          {isApprove ? 'Approve' : 'Reject'} Proposal
        </h3>

        <div className="mb-4">
          <div className="text-sm text-neutral-400 mb-2">Strategy:</div>
          <div className="text-sm text-neutral-200 font-medium">{proposalName}</div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-neutral-400 mb-2">
            {isApprove ? 'Approval' : 'Rejection'} Reason: <span className="text-red-400">*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => onReasonChange(e.target.value)}
            placeholder={`Enter reason for ${isApprove ? 'approval' : 'rejection'}...`}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-700 rounded text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-blue-500 resize-none"
            rows={4}
            disabled={loading}
          />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || !reason.trim()}
            className={`px-4 py-2 text-sm font-medium rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              isApprove
                ? 'bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30'
                : 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
            }`}
          >
            {loading ? 'Processing...' : isApprove ? 'Approve' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  )
}
