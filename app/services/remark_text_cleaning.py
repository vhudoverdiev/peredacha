"""Conservative cleanup of reference text, leaving source workbooks untouched."""
from collections import Counter
from math import log1p
import re

PREFIXES=('требуется','необходимо','отсутствует','отсутствуют')
SEED='замена правой левой ручки ручку балконной пары регулировка эксцентрика закрепить оконного блока требуется необходимо помещения комнаты строительных смесей комплексно входной двери снаружи квартиры комплексная очистка и регулировка отопления в помещении комнаты уплотнительная резинка районе отклонение плавного очертания'.split()


def vocabulary(texts):
    words=Counter(word.casefold().replace('ё','е') for text in texts for word in re.findall('[а-яА-ЯёЁ]+',text)
                  if 1<=len(word)<=22)
    for word in SEED: words[word]=max(words[word],10)
    return words


def clean_reference(text, words):
    def split(match):
        original=match.group(); word=original.casefold().replace('ё','е')
        prefix=next((prefix for prefix in PREFIXES if word.startswith(prefix) and word!=prefix),None)
        if len(word)<10 and not prefix: return original
        start=len(prefix) if prefix else 0
        tail=word[start:]
        # Whole conventional words stay intact. A glued action prefix is never
        # considered a word, even if repeated in several source cells.
        best={0:(0,[])}
        for end in range(1,len(tail)+1):
            options=[]
            for begin in range(max(0,end-22),end):
                part=tail[begin:end]
                if begin==0 and end==len(tail) and not prefix: continue
                if begin in best and words.get(part,0)>=2 and (len(part)>=2 or part in {'в','и','с','к'}):
                    score,parts=best[begin]
                    options.append((score+log1p(words[part])-3,parts+[part]))
            if options: best[end]=max(options,key=lambda item:item[0])
        if len(tail) not in best: return (original[:start]+' '+original[start:]) if prefix else original
        parts=best[len(tail)][1]
        if not prefix and parts and parts[0] in {'под','над','за','на','не','вы','от','по','при','про','со','об','без','пере'}:
            return original
        if not prefix and len(parts)<2: return original
        lengths=([len(prefix)] if prefix else [])+[len(part) for part in parts]
        position=0; result=[]
        for length in lengths:
            result.append(original[position:position+length]);position+=length
        return ' '.join(result)
    value=re.sub('[А-Яа-яЁё]{10,}',split,str(text or ''))
    value=re.sub(r'\s+',' ',value).strip(' -–—;"«»')
    value=strip_worker_marker(value)
    first=re.search('[а-яА-ЯёЁa-zA-Z]',value)
    if first:
        i=first.start();value=value[:i]+value[i].upper()+value[i+1:]
    return value


def strip_worker_marker(value):
    return re.sub(r'\s*\(\s*л\s*\.?\s*б\s*\.?\s*\)[\s.;,]*$', '', str(value), flags=re.I).rstrip() 
