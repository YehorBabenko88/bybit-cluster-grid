class TradeJournal:
    def __init__(self): self.rows=[]
    def append(self,trade): self.rows.append(trade)
    def extend(self,trades): self.rows.extend(trades)
