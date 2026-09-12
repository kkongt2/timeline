"""Numerical features shared by the offline trainer and data publisher."""
import numpy as np
from features_v7 import PAIR_COLUMNS

def pair_features(X):
    X=np.asarray(X,dtype=float);pairs=np.array([(i,j) for i in range(len(X)) for j in range(i+1,len(X))]);out=[]
    for i,j in pairs:
        a,b=X[i],X[j];o=X[[k for k in range(len(X)) if k not in (i,j)]]
        extras=[max(o[:,30]),np.mean(o[:,30]),np.mean(o[:,30]>min(a[30],b[30])),
            max(o[:,4]),max(o[:,32]),np.mean(o[:,42]),a[42]*b[42],abs(a[43]-b[43]),
            min(a[41],b[41]),np.mean((o[:,42]>.5)&(o[:,46]>0))]
        out.append([*((a[PAIR_COLUMNS]+b[PAIR_COLUMNS])/2),*np.minimum(a[PAIR_COLUMNS],b[PAIR_COLUMNS]),
                    *np.abs(a[PAIR_COLUMNS]-b[PAIR_COLUMNS]),*a[20:27],*extras])
    return np.asarray(out),pairs

def export(model,link):
    trees=[]
    for iteration in model._predictors:
        nodes=[]
        for n in iteration[0].nodes:
            if n['is_categorical']:raise ValueError('Categorical node unsupported')
            nodes.append([int(n['is_leaf']),int(n['feature_idx']),float(n['num_threshold']),int(n['left']),int(n['right']),float(n['value'])])
        trees.append(nodes)
    return dict(bias=float(model._baseline_prediction[0,0]),trees=trees,link=link,width=149)
