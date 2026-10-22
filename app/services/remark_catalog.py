"""Local, explainable remark retrieval. No network calls or automatic corrections."""
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from app.work_points import WORK_POINT_LABELS

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'remark_catalog.json'
STOP_WORDS = frozenset('требуется необходимо произвести выполнить работа работы помещение помещении квартира квартире комплексно отмечено момент осмотра весь всех всей для при под над между имеется наличие отсутствие отсутствует установить установлен выполнено устранить следы номер комната комнате санузел санузле кухня кухни кухне коридор коридоре'.split())
SUFFIXES = tuple(sorted(('иями','ями','ами','ого','ему','ому','ыми','ими','ение','ения','ений','ться','ить','ать','ять','ов','ев','ей','ой','ый','ий','ая','яя','ое','ее','ые','ие','ую','юю','ом','ем','ам','ям','ах','ях','ия','ию','ии','а','я','ы','и','у','ю','е','о'), key=len, reverse=True))
OBJECT_HINTS = {
    '10': ('вентиляц','вытяжк'), '11': ('штукатур','шпаклев','потолк'),
    '12': ('монолит','пилон','фасад','ригел'), '13': ('стяжк',), '14': ('гидроизоляц',),
    '15': ('перегород','блочн'), '16': ('мусор','уборк'), '17': ('пвх','окон'),
    '18': ('подокон','откос'), '19': ('ростелеком','интернет'), '20': ('витраж',),
    '21': ('радиатор','отоплен'), '22': ('канализа','водоснабж','хвс','гвс','сантех'),
    '23': ('входн','двер'), '24': ('электр','щитк','розетк','выключат','проводк'),
}


def normalize(value):
    text = str(value or '').casefold().replace('ё', 'е')
    text = re.sub(r'^\s*(?:(?:пункт|п\.)\s*)?№?\s*\d+[.):\-\s]*', '', text)
    return ' '.join(re.findall(r'[а-яa-z0-9]+', text))


def point_keys(label):
    """Names are authoritative; source numbering is only provenance."""
    value = normalize(label)
    if 'отоплен' in value and ('канализа' in value or 'в с' in value):
        return ('21', '22')
    for number, name in WORK_POINT_LABELS.items():
        if int(number) >= 10 and value == normalize(name):
            return (number,)
    aliases = (('гидроизоляц','14'), ('подстилающ','13'), ('стяжк','13'),
               ('блочн','15'), ('пвх','17'), ('откос','18'), ('подоконник','18'),
               ('ростелеком','19'), ('витраж','20'), ('отоплен','21'),
               ('канализа','22'), ('входных двер','23'), ('электрик','24'),
               ('вентиляц','10'), ('штукатур','11'), ('шпаклев','11'),
               ('коробки здан','12'), ('разнорабоч','16'), ('прочее','25'))
    return next(((number,) for term,number in aliases if term in value), ())


def tokens(text):
    result = set()
    for word in normalize(text).split():
        if word in STOP_WORDS or len(word)<3 or word.isdigit():
            continue
        for suffix in SUFFIXES:
            if word.endswith(suffix) and len(word)-len(suffix)>=4:
                word=word[:-len(suffix)]
                break
        result.add(word)
    return frozenset(result)


def fingerprint(task):
    label=task.work_point.display_name if task.work_point else ''
    return sha256(f'{task.work_point_id}\0{label}\0{task.description or task.source_cell_value or ""}'.encode()).hexdigest()


class RemarkCatalog:
    def __init__(self, payload):
        self.version=payload['version']
        self.sources=payload['sources']
        self.entries=payload['entries']
        self.postings=defaultdict(set)
        self.exact=defaultdict(list)
        self.termsets=[]
        for i,entry in enumerate(self.entries):
            terms=tokens(entry['text']); self.termsets.append(terms)
            self.exact[normalize(entry['text'])].append(i)
            for term in terms: self.postings[term].add(i)
        size=max(len(self.entries),1)
        self.idf={term:1+math.log((size+1)/(len(ids)+1)) for term,ids in self.postings.items()}

    def retrieve(self, text, limit=8, point=None):
        query=tokens(text)
        if not query: return []
        votes=Counter()
        for term in query:
            for candidate in self.postings.get(term, ()):
                votes[candidate]+=self.idf[term]
        exact=self.exact.get(normalize(text), ())
        if point:
            votes=Counter({i:score for i,score in votes.items() if point in self.entries[i]['points']})
        ranked=sorted(votes,key=lambda i:(-votes[i],len(self.termsets[i]),-self.entries[i]['count'],len(self.entries[i]['text'])))[:180]
        ids=list(dict.fromkeys([*exact, *ranked]))
        total=sum(self.idf.get(term,1) for term in query)
        results=[]
        for i in ids:
            entry=self.entries[i]
            if point and point not in entry['points']: continue
            terms=self.termsets[i]
            common=query & terms
            overlap=sum(self.idf.get(term,1) for term in common)
            union=sum(self.idf.get(term,1) for term in query | terms)
            score=1.0 if i in exact else .65*overlap/max(total,1)+.35*overlap/max(union,1)
            results.append(dict(entry, score=round(score,4), common=sorted(common)))
        results.sort(key=lambda row:(-row['score'],-row['count'],row['text']))
        return results[:limit]

    @lru_cache(maxsize=8192)
    def classify(self, text):
        if getattr(self,'classifier',None) is not None:
            return self.classifier.classify(text)
        evidence=self.retrieve(text,limit=8)
        if not evidence: return {'state':'unknown','target':None,'evidence':[],'reason':'В справочнике нет близких примеров.'}
        top=evidence[0]
        scores={}
        exact_points=set()
        for row in evidence:
            for point in row['points']: scores[point]=max(scores.get(point,0),row['score'])
            if row['score']==1: exact_points.update(row['points'])
        ranking=sorted(scores,key=lambda p:(-scores[p],int(p)))
        target=ranking[0]
        margin=scores[target]-(scores[ranking[1]] if len(ranking)>1 else 0)
        actual_exact=self.exact.get(normalize(text),())
        source_points={p for i in actual_exact for p in self.entries[i]['points']}
        confident=len(tokens(text))>=2 and (len(source_points)==1 or (top['score']>=.85 and margin>=.14 and len(top['common'])>=2))
        normalized=normalize(text)
        hints={point for point,stems in OBJECT_HINTS.items() if any(stem in normalized for stem in stems)}
        if hints and target not in hints: confident=False
        if not hints and len(tokens(text))<4: confident=False
        # Conflicting physical objects should be reviewed as a compound remark.
        if len(hints)>1 and not hints <= {'17','23'}: confident=False
        if len(exact_points)>1 or len(top['points'])>1: confident=False
        return {'state':'confident' if confident else 'uncertain', 'target':target if confident else None,
                'candidates':ranking[:3], 'score':top['score'], 'evidence':evidence[:3],
                'reason':'Совпадает с примерами одного вида работ.' if confident else 'Есть похожие примеры, но уверенного однозначного соответствия нет.'}

    def suggestions(self, text, point=None, limit=6, include_ambiguous=False):
        # Prefix/word completion also works for an unfinished last word.
        words=normalize(text).split()
        if not words: return []
        complete=' '.join(words[:-1]); prefix=words[-1]
        results=self.retrieve(text,limit=40,point=point)
        if len(prefix)>=2:
            candidates=set()
            for term,ids in self.postings.items():
                if term.startswith(prefix): candidates.update(ids)
            for i in sorted(candidates)[:600]:
                entry=self.entries[i]
                if point and point not in entry['points']: continue
                if complete and not tokens(complete)<=self.termsets[i]: continue
                results.append(dict(entry,score=.6))
        unique={}
        for row in results:
            if not include_ambiguous and len(row['points'])>1: continue
            if len(tokens(row['text']))<2: continue
            key=(tuple(sorted(tokens(row['text']))),tuple(row['points']))
            rank=row['score'] + (.2 if normalize(row['text']).startswith(normalize(text)) else 0) + (.1 if len(row['text'])<=100 else 0)
            candidate=dict(row,completion_rank=rank)
            if key not in unique or rank>unique[key]['completion_rank']:
                unique[key]=candidate
        return sorted(unique.values(),key=lambda row:(-row['completion_rank'],-row['count'],len(row['text'])))[:limit]


@lru_cache(maxsize=1)
def get_base_catalog():
    return RemarkCatalog(json.loads(CATALOG_PATH.read_text(encoding='utf-8')))


@lru_cache(maxsize=4)
def _merged_catalog(engine, maximum, occurrences):
    from app.models import RemarkLibraryEntry
    base=get_base_catalog()
    merged={normalize(entry['text']):dict(entry,points=list(entry['points'])) for entry in base.entries}
    for row in RemarkLibraryEntry.query.order_by(RemarkLibraryEntry.id).all():
        from app.services.remark_text_cleaning import strip_worker_marker
        text=strip_worker_marker(row.text)
        key=normalize(text); points=json.loads(row.points_json)
        if key in merged:
            entry=merged[key]; entry['points']=sorted(set(entry['points'])|set(points),key=int)
            entry['count']+=row.occurrences
        else:
            merged[key]={'id':row.normalized_hash[:16],'text':text,'points':points,'count':row.occurrences,'origins':[]}
    result=RemarkCatalog({'version':base.version,'sources':base.sources,'entries':sorted(merged.values(),key=lambda row:normalize(row['text']))})
    # New entries are available as suggestions, not used to prove their own
    # point assignment correct. Verification retains the independent reference.
    result.classifier=base
    return result


def get_catalog():
    from flask import has_app_context
    if not has_app_context(): return get_base_catalog()
    from app import db
    from app.models import RemarkLibraryEntry
    from sqlalchemy import func
    maximum,occurrences=db.session.query(func.max(RemarkLibraryEntry.id),func.sum(RemarkLibraryEntry.occurrences)).one()
    if maximum is None:return get_base_catalog()
    return _merged_catalog(db.engine,maximum,occurrences)
