import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agiAPI, type AGIStatus, type RegimeStatus, type GoalStatus } from '../api/agi';

const AGIControlPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const [emergencyStopConfirm, setEmergencyStopConfirm] = useState(false);

  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ['agi', 'status'],
    queryFn: () => agiAPI.getStatus(),
  });

  const { data: regimeData, isLoading: regimeLoading } = useQuery({
    queryKey: ['agi', 'regime'],
    queryFn: () => agiAPI.getRegime(),
  });

  const { data: goalData, isLoading: goalLoading } = useQuery({
    queryKey: ['agi', 'goal'],
    queryFn: () => agiAPI.getGoal(),
  });

  const emergencyStopMutation = useMutation({
    mutationFn: () => agiAPI.emergencyStop(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agi'] });
      setEmergencyStopConfirm(false);
    },
  });

  const goalOverrideMutation = useMutation({
    mutationFn: (params: { goal: string; reason: string }) =>
      agiAPI.overrideGoal(params.goal, params.reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agi'] });
    },
  });

  if (statusLoading || regimeLoading || goalLoading) {
    return <div>Loading AGI status...</div>;
  }

  const status: AGIStatus = statusData ?? { regime: 'unknown', goal: 'unknown', health: 'unknown', emergency_stop: false };
  const regime: RegimeStatus = regimeData ?? { regime: 'unknown', confidence: 0, timestamp: '' };
  const goal: GoalStatus = goalData ?? { goal: 'unknown', reason: '', set_at: '' };

  return (
    <div className="agi-control-panel">
      <h1>AGI Control Panel</h1>

      <div className="status-section">
        <h2>Current Status</h2>
        <div>Regime: {regime.regime || status.regime || 'Unknown'}</div>
        <div>Goal: {goal.goal || status.goal || 'Unknown'}</div>
        <div>Health: {status.health || 'Unknown'}</div>
        <div>Emergency Stop: {status.emergency_stop ? 'ACTIVE' : 'Inactive'}</div>
      </div>

      <div className="emergency-stop-section">
        <h2>Emergency Stop</h2>
        {!emergencyStopConfirm ? (
          <button
            className="btn btn-danger"
            onClick={() => setEmergencyStopConfirm(true)}
          >
            Emergency Stop
          </button>
        ) : (
          <div>
            <p>Are you sure you want to activate emergency stop?</p>
            <button
              className="btn btn-danger"
              onClick={() => emergencyStopMutation.mutate()}
              disabled={emergencyStopMutation.isPending}
            >
              Confirm Emergency Stop
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setEmergencyStopConfirm(false)}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      <div className="goal-override-section">
        <h2>Goal Override</h2>
        <select
          onChange={(e) => {
            const reason = prompt('Enter reason for goal override:');
            if (reason) {
              goalOverrideMutation.mutate({
                goal: e.target.value,
                reason,
              });
            }
          }}
        >
          <option value="">Select Goal...</option>
          <option value="maximize_pnl">Maximize P&L</option>
          <option value="preserve_capital">Preserve Capital</option>
          <option value="grow_allocation">Grow Allocation</option>
          <option value="reduce_exposure">Reduce Exposure</option>
        </select>
      </div>

      <div className="navigation">
        <Link to="/">Back to Dashboard</Link>
      </div>
    </div>
  );
};

export default AGIControlPanel;
