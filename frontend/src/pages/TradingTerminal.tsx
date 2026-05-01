import LiveMarketView from '../components/LiveMarketView';
import OpportunityScanner from '../components/OpportunityScanner';
import WhaleActivityFeed from '../components/WhaleActivityFeed';

export default function TradingTerminal() {
  return (
    <div className="min-h-screen bg-neutral-900 text-white p-6">
      <h1 className="text-xl font-semibold text-neutral-100 mb-6">Trading Terminal</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <LiveMarketView />
        <OpportunityScanner />
        <div className="lg:col-span-2">
          <WhaleActivityFeed />
        </div>
      </div>
    </div>
  );
}
