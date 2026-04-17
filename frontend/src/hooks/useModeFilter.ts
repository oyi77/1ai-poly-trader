import { useContext } from 'react'
import { ModeFilterContext, ModeFilterContextType } from '../contexts/ModeFilterContext'

export function useModeFilter(): ModeFilterContextType {
  const context = useContext(ModeFilterContext)

  if (context === undefined) {
    throw new Error('useModeFilter must be used within ModeFilterProvider')
  }

  return context
}
