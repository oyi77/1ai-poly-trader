import type { ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'

interface AdminOnlyProps {
  children: ReactNode
  fallback?: ReactNode
}

export function AdminOnly({ children, fallback = null }: AdminOnlyProps) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <>{fallback}</>
}
