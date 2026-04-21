import { useState } from 'react'
import { ExternalLink, AlertCircle, Loader2 } from 'lucide-react'

export default function MiroFish() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const handleLoad = () => {
    setLoading(false)
    setError(false)
  }

  const handleError = () => {
    setLoading(false)
    setError(true)
  }

  return (
    <div className="h-screen flex flex-col bg-neutral-950">
      {/* Header */}
      <div className="p-4 border-b border-neutral-800 flex justify-between items-center bg-neutral-900">
        <div>
          <h1 className="text-2xl font-bold text-white">MiroFish Simulation</h1>
          <p className="text-sm text-neutral-400 mt-1">
            Multi-agent prediction engine with 32+ autonomous agents
          </p>
        </div>
        <button
          onClick={() => window.open('https://polyedge-mirofish.aitradepulse.com', '_blank')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
        >
          <ExternalLink className="w-4 h-4" />
          Open Full UI
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-4" />
            <p className="text-neutral-400">Loading MiroFish simulation...</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-white mb-2">
              MiroFish Not Available
            </h2>
            <p className="text-neutral-400 mb-4">
              The MiroFish service is not currently running. Please ensure it's deployed at{' '}
              <code className="text-blue-400">polyedge-mirofish.aitradepulse.com</code>
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-neutral-800 rounded-lg hover:bg-neutral-700 transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Iframe */}
      <iframe
        src="https://polyedge-mirofish.aitradepulse.com"
        className={`flex-1 w-full border-0 ${loading || error ? 'hidden' : ''}`}
        title="MiroFish Simulation"
        onLoad={handleLoad}
        onError={handleError}
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
      />

      {/* Info Footer */}
      <div className="p-3 border-t border-neutral-800 bg-neutral-900 text-xs text-neutral-500">
        <div className="flex justify-between items-center">
          <span>
            MiroFish: Multi-agent simulation for prediction markets
          </span>
          <span>
            Status: <span className={error ? 'text-red-500' : loading ? 'text-yellow-500' : 'text-green-500'}>
              {error ? 'Offline' : loading ? 'Connecting...' : 'Online'}
            </span>
          </span>
        </div>
      </div>
    </div>
  )
}
