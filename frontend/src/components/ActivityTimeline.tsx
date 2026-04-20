import type { ActivityLog } from '../types/features'

interface ActivityTimelineProps {
  activities: ActivityLog[]
  loading: boolean
}

export function ActivityTimeline({ activities, loading }: ActivityTimelineProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-400">Loading activities...</div>
      </div>
    )
  }

  if (activities.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-neutral-500">No activity logs yet</div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {activities.map((activity) => (
        <div
          key={activity.id}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 hover:border-neutral-700 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs text-neutral-400">
                  {new Date(activity.timestamp).toLocaleString()}
                </span>
                <span className="text-xs font-medium text-neutral-300">
                  {activity.strategy_name}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    activity.decision_type === 'entry'
                      ? 'bg-green-500/10 text-green-400'
                      : activity.decision_type === 'exit'
                      ? 'bg-red-500/10 text-red-400'
                      : activity.decision_type === 'adjustment'
                      ? 'bg-yellow-500/10 text-yellow-400'
                      : 'bg-neutral-500/10 text-neutral-400'
                  }`}
                >
                  {activity.decision_type}
                </span>
              </div>
              <div className="text-sm text-neutral-400 truncate">
                {JSON.stringify(activity.data)}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div
                className={`text-xs font-medium px-2 py-1 rounded ${
                  activity.confidence_score >= 0.7
                    ? 'bg-green-500/10 text-green-400'
                    : activity.confidence_score >= 0.5
                    ? 'bg-yellow-500/10 text-yellow-400'
                    : 'bg-red-500/10 text-red-400'
                }`}
              >
                {(activity.confidence_score * 100).toFixed(0)}%
              </div>
              <div
                className={`text-xs px-2 py-1 rounded ${
                  activity.mode === 'live'
                    ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                    : 'bg-neutral-500/10 text-neutral-400'
                }`}
              >
                {activity.mode}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
