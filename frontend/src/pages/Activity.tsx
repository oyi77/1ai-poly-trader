import { NavBar } from '../components/NavBar'
import { ActivityTimeline } from '../components/ActivityTimeline'
import { useActivity } from '../hooks/useActivity'

export default function Activity() {
  const { activities, loading } = useActivity()

  return (
    <div className="min-h-screen bg-black text-neutral-100">
      <NavBar title="Activity Log" />
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-neutral-100 mb-2">Activity Log</h1>
          <p className="text-sm text-neutral-400">
            Real-time strategy decisions and trading activity
          </p>
        </div>
        <ActivityTimeline activities={activities} loading={loading} />
      </div>
    </div>
  )
}
