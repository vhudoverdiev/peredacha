"""Offline retrieval only: returns original handbook steps, never generated advice."""
import json
import math
from difflib import get_close_matches, SequenceMatcher
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'ai_assistant'
STOP = set('как что где когда зачем почему мне мой мои моя у я мы вы в во на и или а но по из для это эту этот при не нет ли бы можно нужно сделать пожалуйста работает'.split())
ALIASES = {
    'парол': 'парол', 'пароль': 'парол', '2fa': 'безопас', 'двухэтап': 'безопас',
    'добав': 'добав', 'созда': 'добав', 'создавать': 'добав',
    'запис': 'запис', 'записать': 'запис', 'записаться': 'запис',
    'выгру': 'скача', 'экспо': 'скача', 'скача': 'скача',
    'помен': 'смен', 'смени': 'смен', 'смена': 'смен',
    'кварт': 'помещ', 'помещ': 'помещ',
    'фильт': 'поиск', 'найти': 'поиск', 'поиск': 'поиск', 'искать': 'поиск',
    'распо': 'распоз', 'pdf': 'распоз', 'пдф': 'распоз',
}
# Extra search vocabulary points to existing pages; all answers remain verbatim.
HINTS = {4:'сменить объект выбрать жк', 7:'сменить пароль безопасность',
         9:'добавить замечание вручную', 10:'перенести акт вручную',
         11:'распознать акт pdf автоматически', 15:'изменить пункт замечания статус',
         18:'скачать авр акт выполненных работ', 19:'записать клиента осмотр',
         22:'нет свободного времени слоты осмотр', 33:'сообщить ошибка поддержка разработчик',
         36:'сменить объект выбрать жк', 37:'сменить пароль безопасность',
         39:'добавить замечание вручную', 40:'изменить пункт замечания статус',
         43:'записать клиента осмотр'}

def tokens(text):
    result = []
    for word in re.findall(r'[а-яa-z0-9]+', text.lower().replace('ё','е')):
        if word in STOP or len(word) < 2 or word.isdigit(): continue
        stem = word[:5] if len(word) > 5 else word
        result.append(ALIASES.get(word, ALIASES.get(stem, stem)))
    return result

ACTION_PATTERNS = {
    'delete': r'\b(?:удал\w*|стереть|стира\w*|убрать|убери\w*)\b',
    'create': r'\b(?:добав\w*|созда\w*|создать|завести|внести|занести)\b',
    'edit': r'\b(?:измен\w*|помен\w*|менять|исправ\w*|редакт\w*|смен\w*)\b',
    'export': r'\b(?:скача\w*|выгруз\w*|экспорт\w*)\b',
    'split': r'\b(?:раздел\w*)\b',
}
ENTITY_PATTERNS = (
    ('comment', r'комментар|примечан'),
    ('contractor', r'подряд|подрядн\w* организац'),
    ('role', r'\bрол[ьиь]\b'),
    ('remark', r'замечан|дефект'),
    ('user', r'пользоват|сотрудник'),
    ('premise', r'помещен|квартир|кладов|парков|коммерц'),
    ('project', r'объект|\bжк\b'),
)

def action_signature(text):
    normalized = text.lower().replace('ё', 'е')
    actions = {key for key, pattern in ACTION_PATTERNS.items() if re.search(pattern, normalized)}
    entity = next((key for key, pattern in ENTITY_PATTERNS if re.search(pattern, normalized)), None)
    return actions, entity


class KnowledgeAssistant:
    def __init__(self, path=ROOT/'cards.json'):
        self.data = json.loads(Path(path).read_text(encoding='utf-8'))
        self.entries = self.data['entries']
        self.canonical = {}
        for entry in self.entries:
            if re.search(r': (?:что делать на шаге|в каком порядке выполнить шаги)', entry['question']):
                prefix = entry['question'].split(':', 1)[0].rstrip('?')
                parent = next((e for e in self.entries if e['question'].rstrip('?') == prefix), None)
                if parent:
                    self.canonical[entry['id']] = parent
        self.examples = []
        self.exact_examples = {}
        by_id = {e['id']: e for e in self.entries}
        for intent in json.loads((ROOT/'intents.json').read_text()):
            for example in intent['examples']:
                self.examples.append((self.normalize(example), by_id[intent['id']]))
                self.exact_examples[self.normalize(example)] = by_id[intent['id']]
        self.signatures = {e['id']: action_signature(e['question']) for e in self.entries}
        self.docs = []
        self.df = Counter()
        for entry in self.entries:
            title = tokens(entry['title'] + ' ' + entry.get('question','') + ' ' + entry.get('aliases','') + ' ' + HINTS.get(entry.get('page'), ''))
            counts = Counter(tokens(' '.join(entry['steps'])))
            counts.update(title * 4)
            self.docs.append(counts)
            self.df.update(counts.keys())

    @staticmethod
    def normalize(text):
        text = text.lower().replace('ё','е')
        return ' '.join(re.sub(r'[^а-яa-z0-9 ]',' ',text).split())

    def faq(self):
        pages={4,7,8,9,11,15,16,18,19,23,28,33}
        return [dict(question=e['question'], group=e['group']) for e in self.entries if e['id'].startswith('guide-') and e.get('page') in pages]

    def answer(self, question, device='desktop'):
        normalized = self.normalize(question)
        if normalized in self.exact_examples:
            return self.result(self.exact_examples[normalized])
        if re.search(r'\bпо\b', normalized) and re.search(r'акт|распозна|вручну|ручном', normalized) and not action_signature(normalized)[0]:
            return self.result(next(e for e in self.entries if e['id'] == 'card-480'))
        # Meaning questions must resolve terminology, not a procedure that mentions it.
        definition_query = re.search(r'что (?:значит|означает|такое)|объясни|поясни|значение|как понимать', normalized)
        if definition_query and not action_signature(normalized)[0]:
            definitions = [e for e in self.entries if e.get('definition_pattern') and re.search(e['definition_pattern'], normalized)]
            if definitions:
                # Prefer a specific phrase over a short abbreviation such as ПО.
                definitions.sort(key=lambda e: len(re.search(e['definition_pattern'], normalized).group()), reverse=True)
                return self.result(definitions[0])
        if normalized in self.exact_examples:
            return self.result(self.exact_examples[normalized])
        if re.fullmatch(r'(привет|здравствуй|здравствуйте|добрый день|добрый вечер|спасибо|благодарю)', normalized):
            return dict(found=True, title='Здравствуйте! Я AI агент', steps=['Помогу разобраться с CRM «Передача»: найти нужный раздел, подготовить документ, добавить замечание или записать клиента на осмотр. Выберите частый вопрос или напишите свой.'],  related=self.defaults())
        if re.search(r'что.*уме|кто ты|кто такой|твои возмож|чем.*помо|что такое (?:crm|црм|сера)|что.*сера|что (?:умеет|может|такое) crm|что (?:умеет|может|такое) црм', normalized):
            return dict(found=True, title='Чем могу помочь', steps=['Объясню, как работать с объектами, помещениями, замечаниями, осмотрами, подрядчиками и задачами.', 'Подскажу действия с АВР, документами, материалами, замерами, импортом Excel и распознаванием актов.', 'Помогу найти настройки доступа, историю изменений, обновления и способ сообщить об ошибке. Доступность действий зависит от вашей роли.', 'Я не вижу данные вашего объекта и не изменяю их. Выберите вопрос ниже или напишите, что хотите сделать.'],  related=self.defaults())
        for e in self.entries:
            if normalized == re.sub(r'[^а-яa-z0-9 ]','',e['question'].lower().replace('ё','е')).strip():
                return self.result(e)
        query_actions, query_entity = action_signature(normalized)
        def compatible(entry):
            if entry['id'] in self.canonical:
                return False
            actions, entity = self.signatures[entry['id']]
            if query_actions and not query_actions.intersection(actions):
                return False
            if query_entity and entity and query_entity != entity:
                return False
            return True
        # Explicit variants are safe anchors; near matches require a high score
        # and a gap to the next intent, otherwise ask a clarifying question.
        example_scores = {}
        for example, e in self.examples:
            if not compatible(e): continue
            matcher = SequenceMatcher(None, normalized, example)
            if matcher.quick_ratio() < .87: continue
            score = matcher.ratio()
            if score > example_scores.get(e['id'], (0, None))[0]:
                example_scores[e['id']] = (score, e)
        close = sorted(example_scores.values(), key=lambda pair: pair[0], reverse=True)
        if len(query_actions) <= 1 and len(normalized) >= 10 and close and close[0][0] >= .87 and (len(close)<2 or close[0][0]-close[1][0] >= .04):
            return self.result(close[0][1])
        query = set(tokens(question))
        corrected = set()
        for term in query:
            alternatives = get_close_matches(term, self.df.keys(), n=1, cutoff=.86) if len(term)>=5 and term not in self.df else []
            corrected.add(alternatives[0] if alternatives else term)
        query = corrected
        ranks = []
        for entry, doc in zip(self.entries, self.docs):
            if not compatible(entry): continue
            matched = query.intersection(doc)
            if not matched: continue
            coverage = len(matched)/len(query)
            score = sum((1 + math.log(1 + doc[t])) * math.log(2 + len(self.entries)/(1+self.df[t])) for t in matched) * coverage
            ranks.append((score, coverage, entry))
        ranks.sort(key=lambda pair: (pair[0] * (1.25 if not pair[2]['id'].startswith('card-') else 1)), reverse=True)
        related = [dict(question=e['question'], group=e['group']) for _,_,e in ranks[:3]] or self.defaults()
        if len(query_actions)>1 or len(query)<2 or sum(t in self.df for t in query)/len(query)<.6 or not ranks or ranks[0][1]<.6:
            return dict(found=False,title='Уточним, что вы хотите сделать',steps=['Попробуйте выбрать подходящий вопрос ниже или укажите раздел и действие. Например: «Как изменить пункт замечания?»'],related=related)
        return self.result(ranks[0][2], [dict(question=e['question'],group=e['group']) for _,_,e in ranks[1:3]])

    def defaults(self):
        pages=(9,19,33)
        return [dict(question=e['question'],group=e['group']) for e in self.entries if e.get('page') in pages][:3]

    def result(self, entry, related=None):
        entry = self.canonical.get(entry['id'], entry)
        return dict(found=True,title=entry['question'],steps=entry['steps'],related=related or [])
