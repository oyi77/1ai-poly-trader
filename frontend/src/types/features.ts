export interface ActivityLog {
  id: number;
  timestamp: string; // ISO 8601
  strategy_name: string;
  decision_type: 'entry' | 'exit' | 'hold' | 'adjustment';
  data: Record<string, any>;
  confidence_score: number;
  mode: 'paper' | 'live';
}

export interface MiroFishSignal {
  id: number;
  timestamp: string;
  prediction_topic: string;
  confidence: number;
  report: Record<string, any>;
  debate_weight: number;
  processed: boolean;
}

export interface StrategyProposal {
  id: number;
  strategy_name: string;
  change_details: Record<string, any>;
  expected_impact: string;
  admin_decision: 'pending' | 'approved' | 'rejected';
  executed_at?: string;
  impact_measured?: Record<string, any>;
  created_at: string;
  admin_user_id?: string;
}
