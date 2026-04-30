import { Routes, Route, NavLink } from 'react-router-dom';
import AGIControlPanel from '../components/AGIControlPanel';
import DecisionAuditLog from '../components/DecisionAuditLog';
import StrategyComposerUI from '../components/StrategyComposerUI';
import RegimeDisplay from '../components/RegimeDisplay';

const AGI_TABS = [
  { path: '/agi', label: 'Control Panel', end: true },
  { path: '/agi/decisions', label: 'Decision Log' },
  { path: '/agi/composer', label: 'Strategy Composer' },
  { path: '/agi/regime', label: 'Regime & Goal' },
];

export default function AGIControl() {
  return (
    <div className="agi-control-page min-h-screen bg-gray-900 text-white p-6">
      <nav className="flex gap-4 mb-6 border-b border-gray-700 pb-3">
        {AGI_TABS.map(tab => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end={tab.end}
            className={({ isActive }) =>
              `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Routes>
        <Route index element={<AGIControlPanel />} />
        <Route path="decisions" element={<DecisionAuditLog />} />
        <Route path="composer" element={<StrategyComposerUI />} />
        <Route path="regime" element={<RegimeDisplay />} />
      </Routes>
    </div>
  );
}