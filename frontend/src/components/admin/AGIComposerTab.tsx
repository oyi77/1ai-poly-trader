import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agiAPI } from '../../api/agi'

const BLOCK_CATALOG = {
  signal_source: ['whale_tracker_signal', 'btc_momentum_signal', 'weather_signal', 'oracle_signal'],
  filter: ['min_edge_005', 'min_confidence_07', 'volume_filter'],
  position_sizer: ['kelly_sizer', 'fixed_01', 'fixed_005', 'half_kelly'],
  risk_rule: ['max_1pct', 'max_2pct', 'daily_loss_5pct', 'max_drawdown_10pct'],
  exit_rule: ['take_profit_10pct', 'take_profit_20pct', 'stop_loss_5pct', 'trailing_stop_3pct'],
}

interface StrategyBlock {
  signal_source: string
  filter: string
  position_sizer: string
  risk_rule: string
  exit_rule: string
}

export function AGIComposerTab() {
  const qc = useQueryClient()
  const [strategyName, setStrategyName] = useState('')
  const [blocks, setBlocks] = useState<StrategyBlock[]>([])
  const [selectedBlock, setSelectedBlock] = useState<Partial<StrategyBlock>>({})

  const { data: composedData, isLoading: composedLoading } = useQuery({
    queryKey: ['agi', 'strategies', 'composed'],
    queryFn: () => agiAPI.getComposedStrategies(),
  })

  const composeMutation = useMutation({
    mutationFn: (params: { name: string; blocks: StrategyBlock[] }) =>
      agiAPI.composeStrategy(params.name, params.blocks),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agi', 'strategies'] })
      setStrategyName('')
      setBlocks([])
    },
  })

  const addBlock = () => {
    if (selectedBlock.signal_source && selectedBlock.filter && 
        selectedBlock.position_sizer && selectedBlock.risk_rule && selectedBlock.exit_rule) {
      setBlocks([...blocks, selectedBlock as StrategyBlock])
      setSelectedBlock({})
    }
  }

  const removeBlock = (index: number) => {
    setBlocks(blocks.filter((_, i) => i !== index))
  }

  const handleCompose = () => {
    if (strategyName && blocks.length > 0) {
      composeMutation.mutate({ name: strategyName, blocks })
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Block Palette */}
        <div className="border border-neutral-800 bg-neutral-900/20 p-4 space-y-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Block Palette</div>
          
          {(Object.entries(BLOCK_CATALOG) as [keyof typeof BLOCK_CATALOG, string[]][]).map(([category, items]) => (
            <div key={category} className="space-y-1">
              <div className="text-[8px] text-neutral-600 uppercase font-bold">{category.replace('_', ' ')}</div>
              <div className="flex flex-wrap gap-1">
                {items.map(item => (
                  <button
                    key={item}
                    onClick={() => setSelectedBlock({ ...selectedBlock, [category]: item })}
                    className={`px-2 py-0.5 text-[9px] font-mono border transition-colors ${
                      selectedBlock[category] === item
                        ? 'bg-blue-500/20 border-blue-500/50 text-blue-300'
                        : 'bg-neutral-800/50 border-neutral-800 text-neutral-500 hover:border-neutral-600'
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ))}

          <button
            onClick={addBlock}
            disabled={!selectedBlock.signal_source || !selectedBlock.filter || !selectedBlock.position_sizer || !selectedBlock.risk_rule || !selectedBlock.exit_rule}
            className="w-full mt-2 px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-30"
          >
            Add Block to Canvas
          </button>
        </div>

        {/* Composition Canvas */}
        <div className="border border-neutral-800 bg-neutral-900/20 p-4 space-y-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Composition Canvas</div>
          
          <div className="space-y-1">
            <div className="text-[8px] text-neutral-600 uppercase">Strategy Name</div>
            <input
              type="text"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              placeholder="e.g. btc_momentum_v1"
              className="w-full bg-black border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-800"
            />
          </div>

          <div className="space-y-2 min-h-[100px] border border-neutral-800/50 p-2 bg-black/20">
            {blocks.length === 0 ? (
              <div className="text-[10px] text-neutral-700 italic">No blocks added yet...</div>
            ) : (
              blocks.map((block, index) => (
                <div key={index} className="group border border-neutral-800 p-2 text-[9px] font-mono relative bg-neutral-900/40">
                  <div className="grid grid-cols-2 gap-y-1">
                    <div className="text-neutral-600 uppercase">Signal:</div><div className="text-blue-400">{block.signal_source}</div>
                    <div className="text-neutral-600 uppercase">Filter:</div><div className="text-neutral-400">{block.filter}</div>
                    <div className="text-neutral-600 uppercase">Size:</div><div className="text-neutral-400">{block.position_sizer}</div>
                    <div className="text-neutral-600 uppercase">Risk:</div><div className="text-red-400/70">{block.risk_rule}</div>
                    <div className="text-neutral-600 uppercase">Exit:</div><div className="text-green-400/70">{block.exit_rule}</div>
                  </div>
                  <button
                    onClick={() => removeBlock(index)}
                    className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 transition-opacity"
                  >
                    [REMOVE]
                  </button>
                </div>
              ))
            )}
          </div>

          <button
            onClick={handleCompose}
            disabled={!strategyName || blocks.length === 0 || composeMutation.isPending}
            className="w-full px-3 py-2 bg-blue-500/10 border border-blue-500/30 text-blue-400 text-[10px] uppercase tracking-wider hover:bg-blue-500/20 transition-colors disabled:opacity-40"
          >
            {composeMutation.isPending ? 'Composing...' : 'Finalize & Deploy Strategy'}
          </button>
        </div>
      </div>

      {/* Existing Strategies List */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Deployed AGI Strategies</div>
        {composedLoading ? (
          <div className="text-[10px] text-neutral-600">Loading...</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {(composedData || []).map((s: any) => (
              <div key={s.id} className="border border-neutral-800 p-2 font-mono flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-neutral-300">{s.name}</div>
                  <div className="text-[8px] text-neutral-600 uppercase">{s.id.slice(0, 8)}...</div>
                </div>
                <div className="text-[9px] px-1.5 py-0.5 bg-neutral-800 text-neutral-500 uppercase tracking-tighter">
                  {s.status}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
