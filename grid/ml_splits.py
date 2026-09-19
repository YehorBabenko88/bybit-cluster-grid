from datetime import timedelta

def _get(r,key,default=None):
    try:return r[key]
    except (KeyError,TypeError):return default

def walk_forward(rows,folds=5,embargo_minutes=240):
    """Chronological expanding folds. Training labels must finish before validation embargo."""
    rows=sorted(rows,key=lambda r:r["event_ts"])
    n=len(rows)
    if n<folds+1:return []
    block=max(1,n//(folds+1)); out=[]
    for i in range(1,folds+1):
        val_start=i*block; val_end=min(n,(i+1)*block)
        if val_start>=n:break
        validation=rows[val_start:val_end]
        boundary=validation[0]["event_ts"]-timedelta(minutes=embargo_minutes)
        validation_groups={_get(r,"split_group") for r in validation if _get(r,"split_group")}
        train=[]
        for r in rows[:val_start]:
            label_end=_get(r,"label_end_ts") or r["event_ts"]
            if label_end>=boundary:continue
            if _get(r,"split_group") and _get(r,"split_group") in validation_groups:continue
            train.append(r)
        if train and validation:out.append((train,validation))
    return out
