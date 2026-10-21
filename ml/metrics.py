"""Class-wise operating-point metrics with greedy one-to-one IoU matching."""
from backend.app.vision import iou


def match_counts(predictions, truths, names, confidence=.35, overlap=.5):
    counts={name:{"tp":0,"fp":0,"fn":0} for name in names}
    used=set()
    for prediction in sorted(predictions,key=lambda p:p['confidence'],reverse=True):
        if prediction['confidence']<confidence:
            continue
        candidates=[(iou(prediction['bbox'],truth['bbox']),index) for index,truth in enumerate(truths)
                    if index not in used and prediction['class']==truth['class']]
        best=max(candidates,default=(0,-1))
        if best[0]>=overlap:
            used.add(best[1]);counts[prediction['class']]['tp']+=1
        else:
            counts[prediction['class']]['fp']+=1
    for index,truth in enumerate(truths):
        if index not in used:
            counts[truth['class']]['fn']+=1
    return counts


def summarize(counts):
    return [{"class":name,**values,
             "precision":values['tp']/(values['tp']+values['fp']) if values['tp']+values['fp'] else None,
             "recall":values['tp']/(values['tp']+values['fn']) if values['tp']+values['fn'] else None}
            for name,values in counts.items()]

