import { createContext, useState, useEffect, ReactNode } from 'react'

export type ModeFilter = 'all' | 'paper' | 'testnet' | 'live'

export interface ModeFilterContextType {
  selectedMode: ModeFilter
  setSelectedMode: (mode: ModeFilter) => void
}

const ModeFilterContext = createContext<ModeFilterContextType | undefined>(undefined)

export function ModeFilterProvider({ children }: { children: ReactNode }) {
  const [selectedMode, setSelectedMode] = useState<ModeFilter>(() => {
    // Read from localStorage on mount
    const saved = localStorage.getItem('dashboard_mode_filter')
    if (saved && ['all', 'paper', 'testnet', 'live'].includes(saved)) {
      return saved as ModeFilter
    }
    return 'all'
  })

  // Write to localStorage when mode changes
  useEffect(() => {
    localStorage.setItem('dashboard_mode_filter', selectedMode)
  }, [selectedMode])

  return (
    <ModeFilterContext.Provider value={{ selectedMode, setSelectedMode }}>
      {children}
    </ModeFilterContext.Provider>
  )
}

export { ModeFilterContext }
