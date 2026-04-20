import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { TradeNotifications } from './components/TradeNotifications'
import { PageLoader } from './components/PageLoader'

const Landing = React.lazy(() => import('./pages/Landing'))
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const Admin = React.lazy(() => import('./pages/Admin'))
const Activity = React.lazy(() => import('./pages/Activity'))
const Proposals = React.lazy(() => import('./pages/Proposals'))

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen bg-black flex items-center justify-center">
          <div className="text-center border border-red-900 p-8 max-w-md">
            <div className="text-red-500 text-xs uppercase mb-2 tracking-wider font-mono">
              Runtime Error
            </div>
            <div className="text-neutral-400 text-xs font-mono mb-4 break-words">
              {this.state.error?.message}
            </div>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/**
 * Redirect component for /docs* paths.
 * Docusaurus is a separate static site at /docs/ — we need a full page
 * navigation (not client-side) so the browser fetches the Docusaurus HTML.
 */
function DocsRedirect() {
  React.useEffect(() => {
    const { pathname, search, hash } = window.location
    // Ensure trailing slash for the base /docs path
    const target = pathname === '/docs' ? '/docs/' + search + hash : pathname + search + hash
    window.location.replace(target)
  }, [])
  return <PageLoader />
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <TradeNotifications />
        <React.Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/activity" element={<Activity />} />
            <Route path="/proposals" element={<Proposals />} />
            {/* Legacy standalone routes → redirect to Dashboard tabs */}
            <Route path="/whale-tracker" element={<Navigate to="/dashboard" replace />} />
            <Route path="/settlements" element={<Navigate to="/dashboard" replace />} />
            <Route path="/market-intel" element={<Navigate to="/dashboard" replace />} />
            <Route path="/decisions" element={<Navigate to="/dashboard" replace />} />
            <Route path="/trading-terminal" element={<Navigate to="/dashboard" replace />} />
            <Route path="/pending-approvals" element={<Navigate to="/admin" replace />} />
            <Route path="/edge-tracker" element={<Navigate to="/dashboard" replace />} />
            <Route path="/docs/*" element={<DocsRedirect />} />
            <Route path="/docs" element={<DocsRedirect />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </React.Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
