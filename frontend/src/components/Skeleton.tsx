interface SkeletonProps {
  className?: string
  rows?: number
}

export function Skeleton({ className = '', rows = 1 }: SkeletonProps) {
  return (
    <div className={`animate-pulse ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-neutral-800 rounded mb-2 last:mb-0"
          style={{ opacity: 0.5 - i * 0.05 }}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-neutral-900/50 border border-neutral-800 rounded-lg p-4 ${className}`}>
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 bg-neutral-800 rounded-lg animate-pulse" />
        <div className="flex-1">
          <div className="h-4 bg-neutral-800 rounded w-1/3 mb-2" />
          <div className="h-3 bg-neutral-800 rounded w-1/4" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 bg-neutral-800 rounded w-full" />
        <div className="h-3 bg-neutral-800 rounded w-2/3" />
      </div>
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="h-4 bg-neutral-800 rounded flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} className="flex gap-2">
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div
              key={colIdx}
              className="h-8 bg-neutral-900 rounded flex-1"
              style={{ opacity: 1 - rowIdx * 0.1 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}