def collect_manual_act_entries(form, points):
    allowed={point['number'] for point in points}
    if 'act_point' not in form:
        return [(point['number'],form.get(f'description_{point["number"]}','').strip()) for point in points
                if form.get(f'description_{point["number"]}','').strip()]
    numbers=form.getlist('act_point'); texts=form.getlist('act_description')
    if len(numbers)!=len(texts) or len(numbers)>100:
        raise ValueError('В акте можно добавить до 100 замечаний. Проверьте заполнение строк.')
    result=[]
    for number,text in zip(numbers,texts):
        text=text.strip()
        if not text: continue
        if number not in allowed: raise ValueError('Выберите пункт для каждого заполненного замечания.')
        result.append((number,text))
    return result
