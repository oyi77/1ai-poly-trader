import { createContext, useState, ReactNode } from 'react'

export type ModeFilter = 'all' | 'paper' | 'testnet' | 'live'

export interface ModeFilterContextType {
  selectedMode: ModeFilter
  setSelectedMode: (mode: ModeFilter) => void
}

const ModeFilterContext = createContext<ModeFilterContextType | undefined>(undefined)

export function ModeFilterProvider({ children }: { children: ReactNode }) {
  const [selectedMode, setSelectedMode] = useState<ModeFilter>('all')

  return (
    <ModeFilterContext.Provider value={{ selectedMode, setSelectedMode }}>
      {children}
    </ModeFilterContext.Provider>
  )
}

export { ModeFilterContext }
