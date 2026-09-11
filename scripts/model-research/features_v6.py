"""Shared, pre-race-only feature construction for training and the live collector."""
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta

VERSION = '6.0-conditions'
FEATURES = ['place_1y','win_1y','distance_place','relative_rating','recent_form',
 'jockey_place','trainer_place','relative_burden','days_since_run','history_count',
 'finish_fraction','form_trend','finish_consistency','distance_change','burden_change',
 'recent_margin','relative_speed','opponent_rating','jockey_horse','distance_experience',
 'field_size','place_slots','distance','seoul','busan','jeju','sparse_field',
 'speed_available','margin_available','relative_recent_form','rating_level','long_break']

def clip(x,lo,hi): return max(lo,min(hi,x))
def avg(xs,default=0): return sum(xs)/len(xs) if xs else default
def norm(v,vals):
 lo,hi=min(vals),max(vals)
 return (v-lo)/(hi-lo) if hi>lo else .5
def person(x): return re.sub(r'^\([^)]*\)\s*','',str(x or '')).strip()
def ordinal(date): return datetime.strptime(str(date),'%Y%m%d').toordinal()
def horse_key(venue,name): return venue+'|'+str(name).strip()

class History:
 def __init__(self,context=None):
  self.horses=defaultdict(list);self.people=defaultdict(list);self.clocks={};self.through=''
  if context:
   if context.get('version')!=VERSION: raise ValueError('History feature version mismatch')
   self.horses.update(context['horses']);self.people.update(context['people'])
   self.clocks=context.get('clocks',{});self.through=context['through']

 def field(self,r):
  day=ordinal(r['date']);venue=r['venue'];field=[]
  for h in sorted(r['horses'],key=lambda x:int(x['number'])):
   hist=[x for x in self.horses[horse_key(venue,h['name'])] if x['day']<day]
   yr=[x for x in hist if x['day']>=day-365];recent=hist[-5:][::-1]
   dist=[x for x in hist if x['distance']==r['distance']]
   js=[x for x in self.people[venue+'|jockey|'+person(h.get('jockey'))] if day-365<=x[0]<day]
   ts=[x for x in self.people[venue+'|trainer|'+person(h.get('trainer'))] if day-365<=x[0]<day]
   ff=[(x['n']-x['finish'])/max(1,x['n']-1) for x in recent]
   weights=[1-i*.09 for i in range(len(recent))]
   rg=sum(clip((8-x['finish'])/7,0,1)*w for x,w in zip(recent,weights))/sum(weights) if weights else .35
   speed=[x['speed'] for x in recent if x.get('speed') is not None]
   margin=[x['margin'] for x in recent if x.get('margin') is not None]
   jh=[x for x in hist if x['jockey']==person(h.get('jockey'))]
   field.append(dict(h,history=hist,year=yr,recent=recent,dist=dist,rg=rg,
    jp=(sum(x[1]<=3 for x in js)+3)/(len(js)+10),tp=(sum(x[1]<=3 for x in ts)+3)/(len(ts)+10),
    ff=avg(ff,.4),trend=avg(ff[:2],.4)-avg(ff[2:],.4),consistency=math.sqrt(avg([(x-avg(ff))**2 for x in ff])),
    speed=avg(speed),margin=avg(margin),speed_count=len(speed),margin_count=len(margin),
    jh=(sum(x['finish']<=3 for x in jh)+1.2)/(len(jh)+4)))
  ratings=[float(x.get('rating') or 0) for x in field];burdens=[float(x.get('burden') or 54) for x in field]
  sparse=sum(len(x['year'])<3 for x in field)/len(field);n=len(field);k=2 if n<=7 else 3
  X=[];quality=[]
  for h in field:
   yr,hist,dist,recent=h['year'],h['history'],h['dist'],h['recent'];last=hist[-1] if hist else None
   days=day-last['day'] if last else 365;burden=float(h.get('burden') or 54);rating=float(h.get('rating') or 0)
   vals=[(sum(x['finish']<=3 for x in yr)+1.2)/(len(yr)+4),(sum(x['finish']==1 for x in yr)+.35)/(len(yr)+4),
    (sum(x['finish']<=3 for x in dist)+.8)/(len(dist)+3),norm(rating,ratings),h['rg'],
    norm(h['jp'],[x['jp'] for x in field]),norm(h['tp'],[x['tp'] for x in field]),clip((avg(burdens)-burden)/5,-1,1),
    min(days,365)/365,min(len(hist),20)/20,h['ff'],h['trend'],h['consistency'],
    clip((r['distance']-last['distance'])/1000,-1,1) if last else 0,
    clip((burden-last['burden'])/5,-1,1) if last else 0,
    clip(h['margin']/10,0,1),norm(h['speed'],[x['speed'] for x in field]),
    avg([x['opponent_rating'] for x in recent])/100,h['jh'],min(len(dist),10)/10,n/20,k/3,r['distance']/2500,
    int(venue=='seoul'),int(venue=='busan'),int(venue=='jeju'),sparse,h['speed_count']/5,h['margin_count']/5,
    norm(h['rg'],[x['rg'] for x in field]),rating/150,int(days>98)]
   X.append([round(float(v),10) for v in vals]);quality.append({'starts':len(yr),'sparse':sparse,'history':len(hist)})
  return field,X,quality

 def add_day(self,rows):
  # Freeze reference clocks for the entire date: no same-day result can enter a prediction.
  updates=defaultdict(list)
  for r in rows:
   day=ordinal(r['date']);venue=r['venue'];hs=r['horses'];times=[h['race_seconds'] for h in hs if h.get('race_seconds')]
   clock_key=venue+'|'+str(r['distance'])+'|'+str(r.get('track_condition') or '')
   reference=self.clocks.get(clock_key)
   for h in hs:
    sec=h.get('race_seconds');margin=(sec-min(times))*1200/r['distance'] if sec and times else None
    speed=clip((reference-sec)/reference*100,-15,15) if reference and sec else None
    key=horse_key(venue,h['name']);entry={'day':day,'finish':h['finish'],'n':len(hs),'distance':r['distance'],
     'burden':h['burden'],'rating':h.get('rating',0),'jockey':person(h.get('jockey')),
     'opponent_rating':avg([x.get('rating',0) for x in hs if x['number']!=h['number']]),'margin':margin,'speed':speed}
    self.horses[key].append(entry)
    # Keep one year plus at least ten starts, including infrequent runners.
    self.horses[key]=[x for i,x in enumerate(self.horses[key]) if x['day']>=day-365 or i>=len(self.horses[key])-10]
    for kind in ['jockey','trainer']:
     pk=venue+'|'+kind+'|'+person(h.get(kind));self.people[pk].append([day,h['finish']]);self.people[pk]=[x for x in self.people[pk] if x[0]>=day-365]
   if times:updates[clock_key].append(avg(times))
   self.through=max(self.through,r['date'])
  for key,vals in updates.items():self.clocks[key]=.95*self.clocks[key]+.05*avg(vals) if key in self.clocks else avg(vals)

 def export(self):
  return {'version':VERSION,'through':self.through,'horses':dict(self.horses),'people':dict(self.people),'clocks':self.clocks}

def validate_rows(rows):
 seen=set();out=[];issues=[]
 for r in sorted(rows,key=lambda x:(x['date'],x['venue'],x['race_no'])):
  key=(r['date'],r['venue'],r['race_no']);hs=r['horses'];n=len(hs)
  reason=None
  if key in seen:reason='duplicate_race'
  elif not 3<=n<=16:reason='field_size'
  elif len({h['number'] for h in hs})!=n or len({h['name'] for h in hs})!=n:reason='duplicate_starter'
  elif sorted(h['finish'] for h in hs)!=list(range(1,n+1)):reason='ambiguous_finish'
  elif r.get('place_k')!=(2 if n<=7 else 3):reason='payout_rule_mismatch'
  elif not 500<=r['distance']<=4000 or any(not 35<=h['burden']<=75 for h in hs):reason='invalid_conditions'
  if reason:issues.append({'race':key,'reason':reason});continue
  seen.add(key);out.append(r)
 return out,issues

def prepare(rows):
 store=History();out=[];byday=defaultdict(list)
 for r in rows:byday[r['date']].append(r)
 for date in sorted(byday):
  for r in sorted(byday[date],key=lambda x:(x['venue'],x['race_no'])):
   field,X,q=store.field(r);out.append(dict(r,X=X,quality=q,order=sorted(range(len(field)),key=lambda i:field[i]['finish']),numbers=[h['number'] for h in field]))
  store.add_day(byday[date])
 return out,store

def attach(races,context):
 store=History(context)
 for r in races:
  # A context newer than the race is never valid, even for a historical UI card.
  if context['through']>=r['date']:continue
  field,X,q=store.field(r);by_no={h['number']:(x,v) for h,x,v in zip(field,X,q)}
  for h in r['horses']:h['features_v6'],h['quality_v6']=by_no[h['number']]
  r['feature_version']=VERSION;r['history_through']=context['through']
