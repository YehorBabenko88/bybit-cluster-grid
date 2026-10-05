import json
import math
import pickle


def _numeric_features(row):
    out={}
    for prefix,key in (("f","features"),("i","instrument_features")):
        values=row.get(key) or {}
        if not isinstance(values,dict):
            raise ValueError(key+" must be an object")
        for name,value in values.items():
            if isinstance(value,bool):value=float(value)
            if isinstance(value,(int,float)) and math.isfinite(float(value)):
                out[prefix+"."+str(name)]=float(value)
    return out


class TabularBoostBackend:
    def __init__(self,kind="xgboost",threads=1,seed=1729):
        kind=str(kind).lower()
        if kind not in ("xgboost","lightgbm"):raise ValueError("unsupported backend")
        self.kind=kind;self.threads=max(1,int(threads));self.seed=int(seed)

    def _xy(self,rows,params,feature_names=None):
        target_key=params.get("target_key")
        if not target_key:raise ValueError("target_key is required")
        features=[_numeric_features(r) for r in rows]
        names=feature_names or sorted({k for f in features for k in f})
        if not names:raise ValueError("dataset has no numeric features")
        X=[[f.get(k,float("nan")) for k in names] for f in features]
        y=[]
        for r in rows:
            target=r.get("target") or {}
            value=target.get(target_key) if isinstance(target,dict) else None
            if isinstance(value,bool):value=float(value)
            if not isinstance(value,(int,float)) or not math.isfinite(float(value)):
                raise ValueError("target is missing or non-numeric: "+str(target_key))
            y.append(float(value))
        return X,y,names

    def fit(self,rows,params):
        params=dict(params or {})
        X,y,names=self._xy(rows,params)
        objective=str(params.get("objective","regression"))
        common={"n_estimators":int(params.get("n_estimators",200)),
                "max_depth":int(params.get("max_depth",6)),
                "learning_rate":float(params.get("learning_rate",.05))}
        if self.kind=="xgboost":
            import xgboost as xgb
            cls=xgb.XGBClassifier if objective=="binary" else xgb.XGBRegressor
            model=cls(**common,n_jobs=self.threads,random_state=self.seed,
                      tree_method=params.get("tree_method","hist"),
                      verbosity=0)
        else:
            import lightgbm as lgb
            cls=lgb.LGBMClassifier if objective=="binary" else lgb.LGBMRegressor
            model=cls(**common,n_jobs=self.threads,random_state=self.seed,
                      deterministic=True,verbosity=-1)
        model.fit(X,y)
        return {"model":model,"feature_names":names,"params":params,"backend":self.kind}

    def predict(self,bundle,rows):
        X,_,_=self._xy(rows,bundle["params"],bundle["feature_names"])
        model=bundle["model"]
        if bundle["params"].get("objective")=="binary" and hasattr(model,"predict_proba"):
            return model.predict_proba(X)[:,1].tolist()
        return model.predict(X).tolist()

    def evaluate(self,rows,pred,target_key=None):
        if not target_key:raise ValueError("target_key is required for evaluation")
        _,y,_=self._xy(rows,{"target_key":target_key})
        mse=sum((a-b)**2 for a,b in zip(y,pred))/max(1,len(y))
        return {"mse":mse,"rmse":mse**.5,"samples":len(y)}

    async def serialize(self,bundle):
        return pickle.dumps(bundle,protocol=pickle.HIGHEST_PROTOCOL)
