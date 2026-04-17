import { useModeFilter } from '../../hooks/useModeFilter'
import type { ModeFilter } from '../../contexts/ModeFilterContext'

const MODES: ModeFilter[] = ['all', 'paper', 'testnet', 'live']

export function ModeSelector() {
  const { selectedMode, setSelectedMode } = useModeFilter()
  
  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800 bg-neutral-950">
      <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Mode</span>
      {MODES.map(mode => (
        <button
          key={mode}
          onClick={() => setSelectedMode(mode)}
          className={`
            px-3 py-1 text-[10px] font-mono rounded-full border transition-colors
            ${mode === selectedMode 
              ? 'bg-blue-500/20 border-blue-500 text-blue-400' 
              : 'bg-neutral-900 border-neutral-700 text-neutral-400 hover:bg-neutral-800 hover:border-neutral-600'
            }
          `}
        >
          {mode.charAt(0).toUpperCase() + mode.slice(1)}
        </button>
      ))}
    </div>
  )
}
