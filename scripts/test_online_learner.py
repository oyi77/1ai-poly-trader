from backend.models.database import SessionLocal, Trade
from backend.core.online_learner import OnlineLearner

db = SessionLocal()
trade = db.query(Trade).filter(Trade.result.in_(["win", "loss"])).first()

if trade:
    learner = OnlineLearner()
    learner.on_trade_settled(trade, db)
    print("OnlineLearner ran successfully on a settled trade!")
else:
    print("No settled trades found.")
