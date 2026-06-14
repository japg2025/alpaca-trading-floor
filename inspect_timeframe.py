from alpaca.data.timeframe import TimeFrame
print([x for x in dir(TimeFrame) if not x.startswith('_')])
