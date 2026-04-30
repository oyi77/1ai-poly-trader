import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { agiAPI } from '../api/agi';

const REGIME_ICONS: Record<string, string> = {
  bull: '🐂',
  bear: '🐻',
  sideways: '↔️',
  sideways_volatile: '↔️⚡',
  crisis: '🔥',
  unknown: '❓',
};

const REGIME_COLORS: Record<string, string> = {
  bull: 'text-green-400',
  bear: 'text-red-400',
  sideways: 'text-yellow-400',
  sideways_volatile: 'text-orange-400',
  crisis: 'text-red-600',
  unknown: 'text-gray-400',
};

const GOAL_LABELS: Record<string, string> = {
  maximize_pnl: 'Maximize P&L',
  preserve_capital: 'Preserve Capital',
  grow_allocation: 'Grow Allocation',
  reduce_exposure: 'Reduce Exposure',
};

const RegimeDisplay: React.FC = () => {
  const { data: regimeData, isLoading: regimeLoading } = useQuery({
    queryKey: ['agi', 'regime'],
    queryFn: () => agiAPI.getRegime(),
    refetchInterval: 30000,
  });

  const { data: goalData, isLoading: goalLoading } = useQuery({
    queryKey: ['agi', 'goal'],
    queryFn: () => agiAPI.getGoal(),
    refetchInterval: 30000,
  });

  if (regimeLoading || goalLoading) {
    return <div className="regime-display loading">Loading regime data...</div>;
  }

  const regime = (regimeData?.regime || 'unknown').toLowerCase();
  const confidence = regimeData?.confidence ?? 0;
  const history = regimeData?.history || [];
  const goal = (goalData?.goal || 'unknown').toLowerCase();
  const goalReason = goalData?.reason || '';
  const goalSetAt = goalData?.set_at || '';
  const goalPerformance = goalData?.performance;

  return (
    <div className="regime-display space-y-6">
      <h1 className="text-2xl font-bold">Regime & Goal Status</h1>

      {/* Current Regime */}
      <div className="regime-card bg-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Current Market Regime</h2>
        <div className="flex items-center gap-4">
          <span className="text-5xl">{REGIME_ICONS[regime] || REGIME_ICONS.unknown}</span>
          <div>
            <div className={`text-3xl font-bold ${REGIME_COLORS[regime] || REGIME_COLORS.unknown}`}>
              {regime.replace('_', ' ').toUpperCase()}
            </div>
            <div className="text-gray-400">
              Confidence: <span className="text-white font-mono">{(confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* Confidence Gauge */}
        <div className="mt-4">
          <div className="w-full bg-gray-700 rounded-full h-4">
            <div
              className={`h-4 rounded-full transition-all duration-500 ${
                confidence >= 0.7 ? 'bg-green-500' : confidence >= 0.4 ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-sm text-gray-500 mt-1">
            <span>Low</span>
            <span>Medium</span>
            <span>High</span>
          </div>
        </div>
      </div>

      {/* Goal Status */}
      <div className="goal-card bg-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Current Goal</h2>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎯</span>
            <div>
              <div className="text-xl font-bold text-blue-400">
                {GOAL_LABELS[goal] || goal.toUpperCase()}
              </div>
              {goalReason && (
                <div className="text-gray-400 text-sm">Reason: {goalReason}</div>
              )}
            </div>
          </div>
          {goalSetAt && (
            <div className="text-gray-500 text-sm">
              Set at: {new Date(goalSetAt).toLocaleString()}
            </div>
          )}
          {goalPerformance && (
            <div className="bg-gray-900 rounded p-3 mt-2">
              <div className="text-sm text-gray-400">Performance</div>
              <div className="flex gap-6">
                <div>
                  <span className="text-gray-500">Metric:</span>{' '}
                  <span className="text-white">{goalPerformance.metric}</span>
                </div>
                <div>
                  <span className="text-gray-500">Value:</span>{' '}
                  <span className="text-white">{goalPerformance.value.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Target:</span>{' '}
                  <span className="text-white">{goalPerformance.target.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Regime History Timeline */}
      <div className="history-card bg-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Regime History (Last 24h)</h2>
        {history.length === 0 ? (
          <div className="text-gray-500">No regime history available</div>
        ) : (
          <div className="space-y-2">
            {history.slice().reverse().map((entry, index) => (
              <div key={index} className="flex items-center gap-3 text-sm">
                <span className="text-lg">{REGIME_ICONS[entry.regime.toLowerCase()] || '❓'}</span>
                <span className={`font-medium ${REGIME_COLORS[entry.regime.toLowerCase()] || 'text-gray-400'}`}>
                  {entry.regime.replace('_', ' ').toUpperCase()}
                </span>
                <span className="text-gray-500">
                  {(entry.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-gray-600 text-xs">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="navigation">
        <a href="/agi" className="text-blue-400 hover:text-blue-300">Back to AGI Control</a>
      </div>
    </div>
  );
};

export default RegimeDisplay;