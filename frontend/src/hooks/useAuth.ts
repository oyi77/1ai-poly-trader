import { useState, useEffect } from 'react'
import { getAdminApiKey, setAdminApiKey } from '../api'
import { retryFetch } from '../utils/retryFetch'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface AuthState {
  isAuthenticated: boolean
  authRequired: boolean
  login: (password: string) => Promise<void>
  logout: () => void
}

export function useAuth(): AuthState {
  const [adminKey, setKey] = useState(() => getAdminApiKey())
  const [authRequired, setAuthRequired] = useState(false)

  useEffect(() => {
    let cancelled = false
    
    retryFetch(`${API_BASE}/api/admin/auth-required`)
      .then(r => r.json())
      .then((d: { auth_required: boolean }) => {
        if (!cancelled) setAuthRequired(d.auth_required)
      })
      .catch(() => {})
    
    return () => {
      cancelled = true
    }
  }, [])

  const login = async (password: string): Promise<void> => {
    const res = await retryFetch(`${API_BASE}/api/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error((err as { detail?: string }).detail ?? 'Invalid password')
    }
    setAdminApiKey(password)
    setKey(password)
  }

  const logout = () => {
    setAdminApiKey('')
    setKey('')
  }

  const isAuthenticated = !authRequired || !!adminKey

  return { isAuthenticated, authRequired, login, logout }
}
