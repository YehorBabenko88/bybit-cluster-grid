from datetime import timedelta

def walk_forward(rows,folds=5,embargo_minutes=240):
    """Chronological expanding-window folds with an embargo around validation."""
    rows=sorted(rows,key=lambda r:r["event_ts"])
    n=len(rows)
    if n<folds+1:return []
    block=max(1,n//(folds+1)); out=[]
    for i in range(1,folds+1):
        val_start=i*block; val_end=min(n,(i+1)*block)
        if val_start>=n:break
        cutoff=rows[val_start]["event_ts"]-timedelta(minutes=embargo_minutes)
        train=[r for r in rows[:val_start] if r["event_ts"]<cutoff]
        valid=rows[val_start:val_end]
        if train and valid:out.append((train,valid))
    return out
