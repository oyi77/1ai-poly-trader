import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agiAPI, type DecisionEntry } from '../api/agi';

const DecisionAuditLog: React.FC = () => {
  const [page, setPage] = useState(1);
  const [regimeFilter, setRegimeFilter] = useState('');
  const [goalFilter, setGoalFilter] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['agi', 'decisions', page, regimeFilter, goalFilter],
    queryFn: () => agiAPI.getDecisions(page, 20, regimeFilter, goalFilter),
  });

  if (isLoading) {
    return <div>Loading audit log...</div>;
  }

  const logData = data || { decisions: [], page: 1, total: 0, page_size: 20 };

  return (
    <div className="decision-audit-log">
      <h1>Decision Audit Log</h1>
      
      <div className="filters">
        <select value={regimeFilter} onChange={(e) => setRegimeFilter(e.target.value)}>
          <option value="">All Regimes</option>
          <option value="bull">Bull</option>
          <option value="bear">Bear</option>
          <option value="sideways">Sideways</option>
          <option value="crisis">Crisis</option>
        </select>
        
        <select value={goalFilter} onChange={(e) => setGoalFilter(e.target.value)}>
          <option value="">All Goals</option>
          <option value="maximize_pnl">Maximize P&L</option>
          <option value="preserve_capital">Preserve Capital</option>
          <option value="grow_allocation">Grow Allocation</option>
          <option value="reduce_exposure">Reduce Exposure</option>
        </select>
      </div>

      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Decision Type</th>
            <th>Input</th>
            <th>Output</th>
            <th>Reasoning</th>
          </tr>
        </thead>
        <tbody>
          {logData.decisions.map((entry: DecisionEntry, index: number) => (
            <tr key={index}>
              <td>{new Date(entry.timestamp).toLocaleString()}</td>
              <td>{entry.decision_type}</td>
              <td>
                <pre>{JSON.stringify(entry.input_data, null, 2)}</pre>
              </td>
              <td>
                <pre>{JSON.stringify(entry.output_data, null, 2)}</pre>
              </td>
              <td>{entry.reasoning}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="pagination">
        <button 
          disabled={page <= 1} 
          onClick={() => setPage(p => Math.max(1, p - 1))}
        >
          Previous
        </button>
        <span>Page {logData.page} of {Math.ceil(logData.total / logData.page_size)}</span>
        <button 
          disabled={page >= Math.ceil(logData.total / logData.page_size)} 
          onClick={() => setPage(p => p + 1)}
        >
          Next
        </button>
      </div>

      <div className="navigation">
        <Link to="/agi">Back to AGI Control</Link>
      </div>
    </div>
  );
};

export default DecisionAuditLog;
