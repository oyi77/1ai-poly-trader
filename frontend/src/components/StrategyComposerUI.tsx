import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agiAPI } from '../api/agi';

const BLOCK_CATALOG = {
  signal_source: ['whale_tracker_signal', 'btc_momentum_signal', 'weather_signal', 'oracle_signal'],
  filter: ['min_edge_005', 'min_confidence_07', 'volume_filter'],
  position_sizer: ['kelly_sizer', 'fixed_01', 'fixed_005', 'half_kelly'],
  risk_rule: ['max_1pct', 'max_2pct', 'daily_loss_5pct', 'max_drawdown_10pct'],
  exit_rule: ['take_profit_10pct', 'take_profit_20pct', 'stop_loss_5pct', 'trailing_stop_3pct'],
};

interface StrategyBlock {
  signal_source: string;
  filter: string;
  position_sizer: string;
  risk_rule: string;
  exit_rule: string;
}

const StrategyComposerUI: React.FC = () => {
  const queryClient = useQueryClient();
  const [strategyName, setStrategyName] = useState('');
  const [blocks, setBlocks] = useState<StrategyBlock[]>([]);
  const [selectedBlock, setSelectedBlock] = useState<Partial<StrategyBlock>>({});

  const { data: composedData, isLoading: composedLoading } = useQuery({
    queryKey: ['agi', 'strategies', 'composed'],
    queryFn: () => agiAPI.getComposedStrategies(),
  });

  const composeMutation = useMutation({
    mutationFn: (params: { name: string; blocks: StrategyBlock[] }) =>
      agiAPI.composeStrategy(params.name, params.blocks),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agi', 'strategies'] });
      setStrategyName('');
      setBlocks([]);
    },
  });

  const addBlock = () => {
    if (selectedBlock.signal_source && selectedBlock.filter && 
        selectedBlock.position_sizer && selectedBlock.risk_rule && selectedBlock.exit_rule) {
      setBlocks([...blocks, selectedBlock as StrategyBlock]);
      setSelectedBlock({});
    }
  };

  const removeBlock = (index: number) => {
    setBlocks(blocks.filter((_, i) => i !== index));
  };

  const handleCompose = () => {
    if (strategyName && blocks.length > 0) {
      composeMutation.mutate({ name: strategyName, blocks });
    }
  };

  return (
    <div className="strategy-composer-ui">
      <h1>Strategy Composer</h1>
      
      <div className="composer-layout">
        <div className="block-palette">
          <h2>Block Palette</h2>
          <div className="block-section">
            <h3>Signal Sources</h3>
            {BLOCK_CATALOG.signal_source.map(s => (
              <button
                key={s}
                className={selectedBlock.signal_source === s ? 'selected' : ''}
                onClick={() => setSelectedBlock({ ...selectedBlock, signal_source: s })}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="block-section">
            <h3>Filters</h3>
            {BLOCK_CATALOG.filter.map(f => (
              <button
                key={f}
                className={selectedBlock.filter === f ? 'selected' : ''}
                onClick={() => setSelectedBlock({ ...selectedBlock, filter: f })}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="block-section">
            <h3>Position Sizers</h3>
            {BLOCK_CATALOG.position_sizer.map(p => (
              <button
                key={p}
                className={selectedBlock.position_sizer === p ? 'selected' : ''}
                onClick={() => setSelectedBlock({ ...selectedBlock, position_sizer: p })}
              >
                {p}
              </button>
            ))}
          </div>
          <div className="block-section">
            <h3>Risk Rules</h3>
            {BLOCK_CATALOG.risk_rule.map(r => (
              <button
                key={r}
                className={selectedBlock.risk_rule === r ? 'selected' : ''}
                onClick={() => setSelectedBlock({ ...selectedBlock, risk_rule: r })}
              >
                {r}
              </button>
            ))}
          </div>
          <div className="block-section">
            <h3>Exit Rules</h3>
            {BLOCK_CATALOG.exit_rule.map(e => (
              <button
                key={e}
                className={selectedBlock.exit_rule === e ? 'selected' : ''}
                onClick={() => setSelectedBlock({ ...selectedBlock, exit_rule: e })}
              >
                {e}
              </button>
            ))}
          </div>
          <button onClick={addBlock} disabled={!selectedBlock.signal_source}>
            Add Block
          </button>
        </div>

        <div className="composition-canvas">
          <h2>Composition Canvas</h2>
          <div>
            <label>Strategy Name:</label>
            <input
              type="text"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
            />
          </div>
          <div className="blocks-list">
            {blocks.map((block, index) => (
              <div key={index} className="block-item">
                <span>Signal: {block.signal_source}</span>
                <span>Filter: {block.filter}</span>
                <span>Position: {block.position_sizer}</span>
                <span>Risk: {block.risk_rule}</span>
                <span>Exit: {block.exit_rule}</span>
                <button onClick={() => removeBlock(index)}>Remove</button>
              </div>
            ))}
          </div>
          <button 
            onClick={handleCompose}
            disabled={!strategyName || blocks.length === 0 || composeMutation.isPending}
          >
            {composeMutation.isPending ? 'Composing...' : 'Compose Strategy'}
          </button>
        </div>
      </div>

      <div className="existing-strategies">
        <h2>Existing Strategies</h2>
        {composedLoading ? (
          <p>Loading...</p>
        ) : (
          <ul>
            {(composedData || []).map((s: any) => (
              <li key={s.id}>
                {s.name} - {s.status}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="navigation">
        <Link to="/agi">Back to AGI Control</Link>
      </div>
    </div>
  );
};

export default StrategyComposerUI;
