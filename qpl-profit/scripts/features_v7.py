"""Past-date-only outcome, identity and pace features; shared by training and serving."""
from collections import defaultdict
from datetime import datetime
import re
from features_v6 import History as BaseHistory, FEATURES as BASE_FEATURES, avg, clip, ordinal, person, norm

VERSION = '7.0-race-pace'
FEATURES = BASE_FEATURES + ['actual_place_1y','actual_distance_place','actual_jockey_place','actual_trainer_place',
    'near_distance_form','rating_change','grade_change','opponent_adjusted_margin','early_strength','finish_gain',
    'leader_rate','relative_early_speed','relative_last_speed','sectional_coverage','position_coverage',
    'field_leader_fraction','stronger_rivals','near_distance_experience','age','identity_history_available']
PAIR_COLUMNS = list(range(20)) + list(range(27,32)) + list(range(32,47)) + list(range(48,52))
PAIR_EXTRA = ['rival_rating_max','rival_rating_mean','stronger_rival_fraction','rival_form_max','rival_place_max',
              'rival_leader_mean','both_leaders','early_speed_gap','pair_finish_gain_min','rival_leader_fraction']


def identity(r, h):
    # Reports lack permanent IDs. Cohort+sex prevents merging reused horse names;
    # a current official ID is retained and checked, never inferred for another name.
    age = int(h.get('age') or 0)
    return '|'.join([r['venue'], str(h['name']).strip(), str(int(r['date'][:4])-age) if age else '?', str(h.get('sex') or '?')])


def grade(value):
    m = re.search(r'(\d)등급', str(value or ''))
    return int(m[1]) if m else None


class History:
    def __init__(self, context=None):
        if context and context.get('version') != VERSION: raise ValueError('v7 history version mismatch')
        self.base = BaseHistory(context['base'] if context else None)
        self.records = defaultdict(list, context.get('records', {}) if context else {})
        self.people = defaultdict(list, context.get('people', {}) if context else {})
        self.ids = dict(context.get('ids', {}) if context else {})
        self.through = context.get('through','') if context else ''

    def key(self,r,h):
        key = identity(r,h); known = self.ids.get(key); current = h.get('horse_id')
        if known and current and str(known) != str(current): return key+'|id:'+str(current)
        return key

    def proxy(self,r):
        return dict(r, horses=[dict(h, name=self.key(r,h)) for h in r['horses']])

    def field(self,r):
        proxy = self.proxy(r); _, X, quality = self.base.field(proxy)
        field = sorted(r['horses'],key=lambda h:int(h['number'])); day = ordinal(r['date']); ext = []
        for h,q in zip(field,quality):
            hist = [x for x in self.records[self.key(r,h)] if x['day'] < day]
            yr = [x for x in hist if x['day'] >= day-365]; recent = hist[-5:]
            same = [x for x in hist if x['distance'] == r['distance']]
            near = [x for x in hist if abs(x['distance']-r['distance']) <= 200]
            jt = []
            for kind in ('jockey','trainer'):
                a = [x for x in self.people[r['venue']+'|'+kind+'|'+person(h.get(kind))] if day-365 <= x[0] < day]
                jt.append((sum(x[1] for x in a)+3)/(len(a)+10))
            positions = [x for x in recent if x.get('early_strength') is not None]
            sectionals = [x for x in recent if x.get('early_seconds') and x.get('last_seconds')]
            g,last = grade(r.get('grade')), hist[-1] if hist else None
            last_grade = last.get('grade') if last else None
            values = [(sum(x['placed'] for x in yr)+1.2)/(len(yr)+4),
                (sum(x['placed'] for x in same)+.8)/(len(same)+3),*jt,
                avg([x['form'] for x in near],.4),
                clip((float(h.get('rating') or 0)-last['rating'])/30,-1,1) if last else 0,
                (last_grade-g)/5 if last_grade and g else 0,
                clip(avg([x['adjusted_margin'] for x in recent if x.get('adjusted_margin') is not None])/10,-1,1),
                avg([x['early_strength'] for x in positions],.5), avg([x['finish_gain'] for x in positions]),
                avg([x['leader'] for x in positions],.2),
                -avg([x['early_seconds'] for x in sectionals]), -avg([x['last_seconds'] for x in sectionals]),
                len(sectionals)/5,len(positions)/5,0,0,min(len(near),10)/10,min(int(h.get('age') or 0),15)/15,
                int(bool(hist))]
            q.update(pace_starts=len(positions),sectional_starts=len(sectionals),identity='official_id_checked' if h.get('horse_id') and self.ids.get(self.key(r,h)) else 'name_cohort_sex')
            ext.append(values)
        early=[a[11] for a in ext if a[13]>0]; late=[a[12] for a in ext if a[13]>0]
        for i, e in enumerate(ext):
            e[11]=norm(e[11],early) if e[13]>0 else .5
            e[12]=norm(e[12],late) if e[13]>0 else .5
            e[15]=sum(a[10]>.5 and a[14]>0 for a in ext)/len(ext)
            e[16]=sum(float(h.get('rating') or 0)>float(field[i].get('rating') or 0) for h in field)/len(field)
        return field, [[round(float(v),10) for v in a+b] for a,b in zip(X,ext)], quality

    def add_day(self,rows):
        self.base.add_day([self.proxy(r) for r in rows])
        for r in rows:
            day=ordinal(r['date']);n=len(r['horses']);winners=set(r.get('place_winners') or [h['number'] for h in sorted(r['horses'],key=lambda h:h['finish'])[:r['place_k']]])
            times=[h['race_seconds'] for h in r['horses'] if h.get('race_seconds')]
            for h in r['horses']:
                key=self.key(r,h);ep=h.get('early_position');pos=h['finish'];margin=(h['race_seconds']-min(times))*1200/r['distance'] if times and h.get('race_seconds') else None
                opponents=avg([float(x.get('rating') or 0) for x in r['horses'] if x['number']!=h['number']])
                entry=dict(day=day,distance=r['distance'],rating=float(h.get('rating') or 0),grade=grade(r.get('grade')),
                    placed=h['number'] in winners,form=clip((n-pos)/max(1,n-1),0,1),
                    adjusted_margin=margin-(opponents-float(h.get('rating') or 0))*.05 if margin is not None else None,
                    early_strength=(n-ep)/max(1,n-1) if ep and 1<=ep<=n else None,
                    finish_gain=clip((ep-pos)/max(1,n-1),-1,1) if ep else 0,leader=int(ep<=2) if ep else 0,
                    early_seconds=h.get('early_seconds'),last_seconds=h.get('last_seconds'))
                self.records[key].append(entry)
                self.records[key]=[x for i,x in enumerate(self.records[key]) if x['day']>=day-365 or i>=len(self.records[key])-10]
                if h.get('horse_id'): self.ids[key]=str(h['horse_id'])
                for kind in ('jockey','trainer'):
                    pk=r['venue']+'|'+kind+'|'+person(h.get(kind));self.people[pk].append([day,entry['placed']])
                    self.people[pk]=[x for x in self.people[pk] if x[0]>=day-365]
            self.through=max(self.through,r['date'])

    def export(self):
        return dict(version=VERSION,through=self.through,base=self.base.export(),records=dict(self.records),people=dict(self.people),ids=self.ids)


def prepare(rows):
    store=History();out=[];byday=defaultdict(list)
    for r in rows:byday[r['date']].append(r)
    for date in sorted(byday):
        for r in sorted(byday[date],key=lambda x:(x['venue'],x['race_no'])):
            field,X,q=store.field(r)
            out.append(dict(r,X=X,quality=q,order=sorted(range(len(field)),key=lambda i:field[i]['finish']),numbers=[h['number'] for h in field]))
        store.add_day(byday[date])
    return out,store


def attach(races,context):
    store=History(context)
    for r in races:
        if context['through']>=r['date']:continue
        field,X,q=store.field(r);by_no={h['number']:(x,v) for h,x,v in zip(field,X,q)}
        for h in r['horses']:
            h['features_v7'],h['quality_v7']=by_no[h['number']]
            if h.get('horse_id'):store.ids.setdefault(store.key(r,h),str(h['horse_id']))
        r['feature_version_v7']=VERSION;r['history_through_v7']=context['through']
    context['ids']=store.ids
