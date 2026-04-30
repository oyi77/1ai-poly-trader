import { api, adminApi } from '../api';

export interface RegimeStatus {
  regime: string;
  confidence: number;
  timestamp: string;
  history?: Array<{
    regime: string;
    confidence: number;
    timestamp: string;
  }>;
}

export interface GoalStatus {
  goal: string;
  reason: string;
  set_at: string;
  performance?: {
    metric: string;
    value: number;
    target: number;
  };
}

export interface DecisionEntry {
  id: string;
  timestamp: string;
  agent_name: string;
  decision_type: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  reasoning: string;
  confidence: number;
}

export interface ComposedStrategy {
  id: string;
  name: string;
  blocks: Array<{
    signal_source: string;
    filter: string;
    position_sizer: string;
    risk_rule: string;
    exit_rule: string;
  }>;
  status: string;
  created_at: string;
}

export interface ExperimentResult {
  id: string;
  strategy_name: string;
  status: string;
  trades: number;
  win_rate: number;
  pnl: number;
  created_at: string;
}

export interface AGIStatus {
  regime: string;
  goal: string;
  health: string;
  emergency_stop: boolean;
  allocations?: Record<string, number>;
  last_cycle?: string;
}

export const agiAPI = {
  getStatus: () => api.get<AGIStatus>('/agi/status').then(r => r.data),

  getRegime: () => api.get<RegimeStatus>('/agi/regime').then(r => r.data),

  getGoal: () => api.get<GoalStatus>('/agi/goal').then(r => r.data),

  getDecisions: (page: number = 1, pageSize: number = 20, regime?: string, goal?: string) => {
    const params: Record<string, unknown> = { page, page_size: pageSize };
    if (regime) params.regime = regime;
    if (goal) params.goal = goal;
    return api.get<{ decisions: DecisionEntry[]; page: number; total: number; page_size: number }>('/agi/decisions', { params }).then(r => r.data);
  },

  getComposedStrategies: () => api.get<ComposedStrategy[]>('/agi/strategies/composed').then(r => r.data),

  composeStrategy: (name: string, blocks: ComposedStrategy['blocks']) =>
    adminApi.post<ComposedStrategy>('/agi/strategies/compose', { name, blocks }).then(r => r.data),

  getExperiments: () => api.get<ExperimentResult[]>('/agi/experiments').then(r => r.data),

  getKnowledgeGraph: (query?: string) => {
    const params = query ? { query } : {};
    return api.get<{ entities: unknown[]; relations: unknown[] }>('/agi/knowledge-graph', { params }).then(r => r.data);
  },

  emergencyStop: () => adminApi.post<{ status: string; message: string }>('/agi/emergency-stop').then(r => r.data),

  overrideGoal: (goal: string, reason: string) =>
    adminApi.post<{ status: string; goal: string }>('/agi/goal/override', { goal, reason }).then(r => r.data),

  runCycle: () => adminApi.post<{ actions_taken: number; errors: string[] }>('/agi/run-cycle').then(r => r.data),
};