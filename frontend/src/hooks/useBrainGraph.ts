import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'
import { getWsUrl } from '../api'

export interface BrainNode {
  id: string
  type: 'signal' | 'ai' | 'execution' | 'analysis'
  label: string
  status: 'active' | 'idle' | 'processing' | 'error'
  data?: any
}

export interface BrainEdge {
  id: string
  source: string
  target: string
  animated: boolean
  label?: string
}

export interface BrainGraphData {
  nodes: BrainNode[]
  edges: BrainEdge[]
  debate_id?: string
  timestamp: string
}

export interface DebateTranscript {
  id: string
  timestamp: string
  speaker: string
  message: string
  vote?: 'approve' | 'reject' | 'abstain'
}

export interface UseBrainGraphResult {
  graphData: BrainGraphData | null
  transcript: DebateTranscript[]
  status: 'connecting' | 'open' | 'closed' | 'error'
  loading: boolean
}

export function useBrainGraph(): UseBrainGraphResult {
  const [graphData, setGraphData] = useState<BrainGraphData | null>(null)
  const [transcript, setTranscript] = useState<DebateTranscript[]>([])
  const [loading, setLoading] = useState(true)

  const { data, status } = useWebSocket<BrainGraphData>(getWsUrl('/ws/brain'), { topic: 'brain' })

  useEffect(() => {
    if (data) {
      setGraphData(data)
      setLoading(false)
      
      if (data.debate_id) {
        fetchDebateTranscript(data.debate_id)
      }
    }
  }, [data])

  const fetchDebateTranscript = useCallback(async (debateId: string) => {
    try {
      const response = await fetch(`/api/brain/debate/${debateId}`)
      if (response.ok) {
        const data = await response.json()
        setTranscript(data.transcript || [])
      }
    } catch (err) {
      console.error('Failed to fetch debate transcript:', err)
    }
  }, [])

  return {
    graphData,
    transcript,
    status,
    loading,
  }
}
