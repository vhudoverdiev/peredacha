from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
import os
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "{%s}" % WORD_NS
ET.register_namespace("w", WORD_NS)

RUSSIAN_MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


@dataclass
class DocumentChange:
    kind: str
    title: str
    before: str
    after: str


DEFAULT_OWNER_SINGLE_PHRASE = (
    "именуемая в дальнейшем «Участник долевого строительства», «Кредитор», "
    "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
    "заключили настоящее Соглашение о нижеследующем:"
)

DEFAULT_OWNER_PLURAL_PHRASE = (
    "именуемые в дальнейшем «Участник долевого строительства», «Кредитор», "
    "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
    "заключили настоящее Соглашение о нижеследующем:"
)

OWNER_DATA_TEMPLATE_FEMALE = (
    "Гражданка Фамилия Имя Отчество, «__» ______ ____ года рождения, "
    "пол женский, место рождения: _______, гражданство: Российская Федерация, "
    "страховой номер индивидуального лицевого счета в системе обязательного пенсионного страхования: _______, "
    "паспорт серии __ __ № ______, выдан ______ __.__.____ г., код подразделения ___-___, "
    "зарегистрирована по адресу: _______, телефон: _______, e-mail: _______"
)
OWNER_DATA_TEMPLATE_MALE = (
    "Гражданин Фамилия Имя Отчество, «__» ______ ____ года рождения, "
    "пол мужской, место рождения: _______, гражданство: Российская Федерация, "
    "страховой номер индивидуального лицевого счета в системе обязательного пенсионного страхования: _______, "
    "паспорт серии __ __ № ______, выдан ______ __.__.____ г., код подразделения ___-___, "
    "зарегистрирован по адресу: _______, телефон: _______, e-mail: _______"
)
OWNER_GENDER_OPTIONS = (
    {"value": "female", "title": "Женский"},
    {"value": "male", "title": "Мужской"},
)

MATERIALS_EXAMPLE = "- плиточный клей PLITONIT В – 12 (Двенадцать) мешков;\n- гипсовая штукатурка Ротбанд – 3 (Три) мешка"
CERTIFICATES_EXAMPLE = "- Подарочный сертификат Группы «Стройбат» (№ 2026-___) – 1 (Одна) шт. на сумму ______ руб."
MATERIALS_AUTO_TEMPLATE = CERTIFICATES_EXAMPLE + "\n" + MATERIALS_EXAMPLE
MATERIALS_SINGLE_EXAMPLE = "- финишная шпаклевка vetonit – 6 (Шесть) мешков;"
GIFT_EXAMPLE = MATERIALS_AUTO_TEMPLATE
DEFECTS_BASIS_EXAMPLE = (
    "взамен устранения Должником недостатков по стенам и царапин на створке стеклопакета, "
    "указанных в акте осмотра Застройщика от «__» ______ 2026 года, акте осмотра «ГОСТПРИЁМКА» "
    "(составлен ________) от «__» ______ 2026 года"
)
DEFECTS_BASIS_SIMPLE_EXAMPLE = "взамен устранения Должником недостатков указанных в акте осмотра Застройщика от «__» ______ 2026 года"
DEFECTS_BASIS_GIFT_EXAMPLE = (
    "взамен устранения Должником недостатков, указанных в акте осмотра Застройщика от «__» ______ 2026 года, "
    "акте осмотра «ГОСТПРИЁМКА» (составлен ________) от «__» ______ 2026 года (за исключением ________)"
)
DEFECTS_EXAMPLE = (
    "{defects_basis} квартиры {apartment_number}, находящейся на {floor_number}, "
    "расположенной по адресу: Архангельская область, город Северодвинск, улица Мира, дом 5 корпус 1 "
    "(далее – Квартира, Объект долевого строительства), которые Должник должен был устранить во исполнение "
    "обязательства по передаче объекта долевого строительства надлежащего качества по Договору участия "
    "в долевом строительстве {contract_full}, заключенному между Кредитором (Участником долевого строительства) "
    "и Должником (Застройщиком)."
)
ACCEPTANCE_MATERIALS_EXAMPLE = "Должник передал, а Кредитор принял указанные в настоящем пункте строительные материалы."
ACCEPTANCE_GIFT_EXAMPLE = "Должник передал, а Кредитор принял указанные в настоящем пункте Соглашения подарочные сертификаты."
SIGNATURE_ONE_EXAMPLE = "Фамилия И.О."
SIGNATURE_TWO_EXAMPLE = "Фамилия И.О.\nФамилия И.О."
CONTRACT_EXAMPLE = "№ МИР/ПЛ/КВ-О2-31 от «28» декабря 2024 года"
CONTRACT_EMPTY_EXAMPLE = "№ МИР/__/КВ-О2-___ от «__» ______ ____ года"
APARTMENT_EMPTY_EXAMPLE = "№ __"
FLOOR_EMPTY_EXAMPLE = "__ этаже"


ADDENDUM_FIELD_LABELS = {
    "agreement_date": "Дата соглашения",
    "city": "Город",
    "owner_one_gender": "Род 1 собственника",
    "owner_two_gender": "Род 2 собственника",
    "owner_one_data": "Данные 1 собственника",
    "owner_two_data": "Данные 2 собственника",
    "owner_single_phrase": "Род собственника",
    "owners_plural_phrase": "Род собственников",
    "contract_full": "Номер договора и дата",
    "transfer_type": "Тип передачи",
    "materials_block": "Что получает кредитор",
    "defects_basis": "Основание",
    "apartment_number": "Квартира",
    "floor_number": "Этаж",
    "defects_block": "Абзац целиком, если нужно",
    "acceptance_text": "Что передано",
    "creditor_signatures": "ФИО для подписи",
    # Старые плейсхолдеры оставлены для совместимости с шаблонами, где они уже используются.
    "addendum_number": "Номер доп. соглашения",
    "addendum_date": "Дата доп. соглашения",
    "contract_number": "Номер договора",
    "contract_date": "Дата договора",
    "buyer_name": "Покупатель",
    "seller_name": "Продавец / застройщик",
    "address": "Адрес объекта",
    "cadastral_number": "Кадастровый номер",
    "price": "Цена",
    "deadline": "Срок передачи",
    "registration_number": "Номер регистрации",
    "representative": "Представитель",
    "power_of_attorney": "Доверенность",
}


ADDENDUM_FIELD_GROUPS = [
    {
        "title": "1. Шапка",
        "fields": [
            {
                "key": "agreement_date",
                "label": ADDENDUM_FIELD_LABELS["agreement_date"],
                "type": "text",
                "placeholder": "",
                "hint": "Дата ставится автоматически. Поле можно изменить вручную.",
                "presets": [],
                "required": False,
            },
            {
                "key": "apartment_number",
                "label": ADDENDUM_FIELD_LABELS["apartment_number"],
                "type": "number",
                "hint": "Введите только цифру. В документе будет “№ ...”.",
                "presets": [],
                "required": True,
            },
            {
                "key": "floor_number",
                "label": ADDENDUM_FIELD_LABELS["floor_number"],
                "type": "number",
                "hint": "Введите только цифру. В документе будет “... этаже”.",
                "presets": [],
                "required": True,
            },
            {
                "key": "contract_full",
                "label": ADDENDUM_FIELD_LABELS["contract_full"],
                "type": "text",
                "placeholder": CONTRACT_EMPTY_EXAMPLE,
                "hint": "По умолчанию подставляется пустой шаблон договора; его можно сразу исправить.",
                "presets": [],
                "required": True,
            },
        ],
    },
    {
        "title": "2. Собственники",
        "fields": [
            {
                "key": "owner_one_gender",
                "label": ADDENDUM_FIELD_LABELS["owner_one_gender"],
                "type": "gender_buttons",
                "options": OWNER_GENDER_OPTIONS,
                "default": "female",
                "hint": "Выберите муж/жен — система сама подставит окончания в данных и фразе “именуемая/именуемый”.",
                "presets": [],
                "required": True,
            },
            {
                "key": "owner_one_data",
                "label": ADDENDUM_FIELD_LABELS["owner_one_data"],
                "type": "textarea",
                "rows": 4,
                "placeholder": OWNER_DATA_TEMPLATE_FEMALE,
                "owner_templates": {"female": OWNER_DATA_TEMPLATE_FEMALE, "male": OWNER_DATA_TEMPLATE_MALE},
                "hint": "Шаблон данных подставляется автоматически по выбранному полу. Заполните пустые места.",
                "presets": [],
                "required": True,
            },
            {
                "key": "owner_two_gender",
                "label": ADDENDUM_FIELD_LABELS["owner_two_gender"],
                "type": "gender_buttons",
                "options": OWNER_GENDER_OPTIONS,
                "default": "male",
                "owner_two_only": True,
                "hint": "Появляется, если выбрано 2 собственника.",
                "presets": [],
                "required": True,
            },
            {
                "key": "owner_two_data",
                "label": ADDENDUM_FIELD_LABELS["owner_two_data"],
                "type": "textarea",
                "rows": 4,
                "placeholder": OWNER_DATA_TEMPLATE_MALE,
                "owner_two_only": True,
                "owner_templates": {"female": OWNER_DATA_TEMPLATE_FEMALE, "male": OWNER_DATA_TEMPLATE_MALE},
                "hint": "Заполните данные второго собственника; подпись снизу сформируется автоматически.",
                "presets": [],
                "required": True,
            },
        ],
    },
    {
        "title": "5. Соглашение",
        "fields": [
            {
                "key": "transfer_type",
                "label": ADDENDUM_FIELD_LABELS["transfer_type"],
                "type": "transfer_buttons",
                "default": "materials",
                "options": [
                    {"value": "materials", "title": "Материалы", "template": MATERIALS_EXAMPLE, "acceptance": ACCEPTANCE_MATERIALS_EXAMPLE},
                    {"value": "certificates", "title": "Сертификаты", "template": CERTIFICATES_EXAMPLE, "acceptance": ACCEPTANCE_GIFT_EXAMPLE},
                ],
                "hint": "Кнопка автоматически заполнит блок получения и фразу передачи.",
                "presets": [],
                "required": True,
            },
            {
                "key": "materials_block",
                "label": ADDENDUM_FIELD_LABELS["materials_block"],
                "type": "textarea",
                "rows": 5,
                "placeholder": MATERIALS_AUTO_TEMPLATE,
                "default": MATERIALS_AUTO_TEMPLATE,
                "hint": "Автошаблон можно отредактировать вручную. Каждая строка станет отдельной строкой в Word.",
                "presets": [],
                "required": True,
            },
            {
                "key": "acceptance_text",
                "label": ADDENDUM_FIELD_LABELS["acceptance_text"],
                "type": "hidden",
                "default": ACCEPTANCE_MATERIALS_EXAMPLE,
                "presets": [],
                "required": False,
            },
        ],
    },
    {
        "title": "6. За какие замечания?",
        "fields": [
            {
                "key": "defects_basis",
                "label": ADDENDUM_FIELD_LABELS["defects_basis"],
                "type": "textarea",
                "rows": 2,
                "placeholder": "взамен устранения Должником недостатков указанных в акте осмотра",
                "default": "взамен устранения Должником недостатков указанных в акте осмотра",
                "hint": "Заменяется только эта строка. Остальной текст абзаца в Word остается без изменений.",
                "presets": [],
                "required": True,
            },
        ],
    },
]


ADDENDUM_OPTIONS = {
    "change_buyer": {
        "title": "Изменить данные покупателя",
        "clause": "Стороны согласовали изложить сведения о Покупателе в новой редакции: {buyer_name}.",
    },
    "change_object": {
        "title": "Уточнить объект / квартиру",
        "clause": "Стороны уточнили описание объекта: квартира {apartment_number}, расположенная по адресу: {address}.",
    },
    "change_price": {
        "title": "Изменить цену договора",
        "clause": "Цена договора с учетом настоящего дополнительного соглашения составляет {price}.",
    },
    "change_deadline": {
        "title": "Изменить срок передачи",
        "clause": "Срок передачи объекта участнику долевого строительства устанавливается: {deadline}.",
    },
    "add_registration": {
        "title": "Добавить сведения о регистрации",
        "clause": "Сведения о государственной регистрации: {registration_number}.",
    },
    "add_power_of_attorney": {
        "title": "Добавить доверенность",
        "clause": "Представитель действует на основании доверенности: {power_of_attorney}.",
    },
}


ADDENDUM_TEMPLATE_VARIANTS = {
    "materials": {
        "title": "Материалы / 1–2 собственника",
        "description": "Обычное соглашение с передачей строительных материалов.",
    },
    "gift": {
        "title": "Подарочный сертификат + материалы",
        "description": "Соглашение, где кредитор получает подарочный сертификат и материалы.",
    },
    "two_owners": {
        "title": "Два собственника",
        "description": "Шаблон с двумя строками собственников и двумя подписями кредитора.",
    },
}



def russian_date(value: date | None = None) -> str:
    value = value or date.today()
    return f"«{value.day:02d}» {RUSSIAN_MONTHS[value.month]} {value.year} года"


def addendum_template_options_for_template() -> list[dict[str, str]]:
    return [{"key": key, **value} for key, value in ADDENDUM_TEMPLATE_VARIANTS.items()]


def create_builtin_addendum_template(output_path: Path, variant: str = "materials") -> Path:
    """Create a clean .docx addendum template without requiring LibreOffice.

    This is used when the user does not upload a file, or uploads a legacy .doc
    while LibreOffice is not installed on the server. The text intentionally
    follows the highlighted examples so the same structured replacements work.
    """
    variant = variant if variant in ADDENDUM_TEMPLATE_VARIANTS else "materials"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    paragraphs = _builtin_addendum_paragraphs(variant)
    _write_minimal_docx(output_path, paragraphs)
    return output_path


def _builtin_addendum_paragraphs(variant: str) -> list[str]:
    if variant == "gift":
        owner_block = [
            "Гражданка Смоленская Римма Александровна, «28» мая 1986 года рождения, пол женский, место рождения: ________, гражданство: Российская Федерация, страховой номер индивидуального лицевого счета в системе обязательного пенсионного страхования: _______, паспорт серии __ __ № ______, выдан ______ __.__.____ г., код подразделения ___-___, зарегистрирована по адресу: _______, телефон: _______, e-mail: _______, именуемая в дальнейшем «Участник долевого строительства», «Кредитор», с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, заключили настоящее Соглашение о нижеследующем:",
        ]
        materials = [
            "- Подарочный сертификат Группы «Стройбат» (№ 2026-008) – 1 (Одна) шт. на сумму 5 000,00 руб.",
            "- Гипсовая шпаклевка Ротбанд – 10 (Десять) мешков;",
        ]
        defects = "взамен устранения Должником недостатков, указанных в акте осмотра Застройщика от «25» мая 2026 года, акте осмотра «ГОСТПРИЁМКА» (составлен Чепелевым И.В.) от «25» мая 2026 года (за исключением царапины на средней глухой створки оконного блока в помещении спальни) квартиры № 273, находящейся на 8 этаже, расположенной по адресу: Архангельская область, город Северодвинск, улица Мира, дом 5 корпус 1 (далее – Квартира, Объект долевого строительства), которые Должник должен был устранить во исполнение обязательства по передаче объекта долевого строительства надлежащего качества по Договору участия в долевом строительстве № МИР/БИ/КВ-О2-273 от «27» ноября 2024 года, заключенному между Кредитором (Участником долевого строительства) и Должником (Застройщиком)."
        acceptance = ACCEPTANCE_GIFT_EXAMPLE
        signatures = ["___________________/Смоленская Р.В."]
    else:
        owner_block = [
            "Гражданка Новицкая Ксения Николаевна, «18» мая 1991 года рождения, пол женский, место рождения: ________, гражданство: Российская Федерация, страховой номер индивидуального лицевого счета в системе обязательного пенсионного страхования: _______, паспорт серии __ __ № ______, выдан ______ __.__.____ г., код подразделения ___-___, зарегистрирована по адресу: _______, телефон: _______, e-mail: _______,",
            "Гражданин Новицкий Владислав Евгеньевич, «04» ноября 1989 года рождения, пол мужской, место рождения: ________, гражданство: Российская Федерация, страховой номер индивидуального лицевого счета в системе обязательного пенсионного страхования: _______, паспорт серии __ __ № ______, выдан ______ __.__.____ г., код подразделения ___-___, зарегистрирован по адресу: _______, телефон: _______, e-mail: _______, именуемые в дальнейшем «Участник долевого строительства», «Кредитор», с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, заключили настоящее Соглашение о нижеследующем:",
        ]
        materials = [
            "- плиточный клей PLITONIT В – 12 (Двенадцать) мешков;",
            "- гипсовая штукатурка Ротбанд – 3 (Три) мешка",
            "(вид, цвет и марка строительных материалов устанавливаются Застройщиком)",
        ]
        defects = "взамен устранения Должником недостатков по стенам и царапин на створке стеклопакета, указанных в акте осмотра Застройщика от «13» апреля 2026 года, акте осмотра «ГОСТПРИЁМКА» (составлен Чепелевым А.В.) от «13» апреля 2026 года квартиры № 31, находящейся на 4 этаже, расположенной по адресу: Архангельская область, город Северодвинск, улица Мира, дом 5 корпус 1 (далее – Квартира, Объект долевого строительства), которые Должник должен был устранить во исполнение обязательства по передаче объекта долевого строительства надлежащего качества по Договору участия в долевом строительстве № МИР/ПЛ/КВ-О2-31 от «28» декабря 2024 года, заключенному между Кредитором (Участником долевого строительства) и Должником (Застройщиком)."
        acceptance = ACCEPTANCE_MATERIALS_EXAMPLE
        signatures = ["___________________/Новицкая К.Н.", "___________________/Новицкий В.Е."]

    base = [
        "Приложение к договору поставки",
        "",
        "СОГЛАШЕНИЕ",
        "",
        "об отступном",
        f"город Северодвинск                                                                                                                             «14» апреля 2026 года",
        "Общество с ограниченной ответственностью Специализированный застройщик «Мир», идентификационный номер налогоплательщика (ИНН): 2902088977, основной государственный регистрационный номер (ОГРН): 1212900004020, дата государственной регистрации: «11» июня 2021 года, наименование регистрирующего органа: Инспекция Федеральной налоговой службы по г. Архангельску, код причины постановки на учет (КПП): 290201001, в лице управляющего – индивидуального предпринимателя Фролова Михаила Александровича, действующего на основании Устава, именуемое в дальнейшем «Застройщик», «Должник», с одной стороны и",
    ]
    base.extend(owner_block)
    base.extend([
        "1. Кредитор согласен на получение от Должника:",
        *materials,
        "",
        defects,
        "",
        acceptance,
        "",
        "2. Подписание настоящего соглашения Сторонами является доказательством исполнения Должником его обязательства по передаче объекта долевого строительства: помещения, надлежащего качества, в рамках указанных в настоящем соглашении недостатков, по Договору участия в долевом строительстве                                       № МИР/ПЛ/КВ-О2-31 от «28» декабря 2024 года, заключенному между Кредитором (Участником долевого строительства) и Должником (Застройщиком).",
        "",
        "3. Кредитор самостоятельно и за свой счет производит все необходимые для устранения указанных недостатков работ.",
        "С момента подписания настоящего Соглашения у Должника прекращаются гарантийные обязательства по указанным недостаткам.",
        "",
        "4. Во всем остальном стороны руководствуются действующим законодательством РФ.",
        "",
        "5. Настоящее Соглашение составлено в 2 (Двух) экземплярах, имеющих одинаковую силу.",
        "",
        "«Должник»",
        "",
        "ООО СЗ «Мир»                                                                                                     _____________________/Фролов М.А.",
        "«Кредитор»",
        "",
        *signatures,
    ])
    return base


def _write_minimal_docx(output_path: Path, paragraphs: list[str]) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    body_parts: list[str] = []
    for text in paragraphs:
        if text == "":
            body_parts.append("<w:p/>")
            continue
        xml_space = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") or "  " in text else ""
        body_parts.append(f"<w:p><w:r><w:t{xml_space}>{escape(text)}</w:t></w:r></w:p>")
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORD_NS}"><w:body>'
        + "".join(body_parts)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        + '</w:body></w:document>'
    )
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def addendum_options_for_template() -> list[dict[str, str]]:
    return [{"key": key, **value} for key, value in ADDENDUM_OPTIONS.items()]


def addendum_fields_for_template() -> list[dict[str, object]]:
    groups: list[dict[str, object]] = deepcopy(ADDENDUM_FIELD_GROUPS)
    today_text = russian_date()
    for group in groups:
        for field in group.get("fields", []):
            key = field.get("key")
            if key == "agreement_date":
                field["default"] = today_text
                field["placeholder"] = today_text
            elif key == "contract_full":
                field["default"] = CONTRACT_EMPTY_EXAMPLE
            elif key == "owner_one_data":
                field["default"] = OWNER_DATA_TEMPLATE_FEMALE
            elif key == "owner_two_data":
                field["default"] = OWNER_DATA_TEMPLATE_MALE
            elif key == "materials_block":
                field["default"] = MATERIALS_AUTO_TEMPLATE
                field["placeholder"] = MATERIALS_AUTO_TEMPLATE
            elif key == "defects_basis":
                field["default"] = "взамен устранения Должником недостатков указанных в акте осмотра"
            elif key == "acceptance_text":
                field["default"] = ACCEPTANCE_MATERIALS_EXAMPLE
            elif key == "transfer_type":
                field["default"] = "materials"
    return groups


def addendum_field_keys() -> list[str]:
    keys: list[str] = []
    for group in ADDENDUM_FIELD_GROUPS:
        for field in group["fields"]:
            keys.append(str(field["key"]))
    keys.extend(key for key in ADDENDUM_FIELD_LABELS if key not in keys)
    return keys


def validate_addendum_template(source_path: Path) -> tuple[bool, str]:
    """Basic safety check: do not process unrelated Word files as addendum templates."""
    text = _extract_docx_plain_text(Path(source_path))
    normalized = _normalize_for_search(text)
    strong_markers = [
        "кредитор согласен на получение",
        "взамен устранения",
        "должник передал",
        "кредитор принял",
    ]
    has_agreement = "соглашение" in normalized or "дополнительное соглашение" in normalized
    marker_count = sum(1 for marker in strong_markers if marker in normalized)
    if has_agreement and marker_count >= 2:
        return True, ""
    return False, "Вы загружаете не доп. соглашение. Загрузите шаблон доп. соглашения или оставьте поле файла пустым, чтобы использовать встроенный шаблон."


def _extract_docx_plain_text(source_path: Path) -> str:
    try:
        with zipfile.ZipFile(source_path, "r") as archive:
            parts = []
            for name in archive.namelist():
                if not _is_word_xml(name):
                    continue
                root = ET.fromstring(archive.read(name))
                for paragraph in root.iter(f"{XML_NS}p"):
                    text = _paragraph_text(paragraph).strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts)
    except Exception:
        return ""


def prepare_uploaded_word_file(source_path: Path, work_dir: Path | None = None, fallback_variant: str = "materials") -> Path:
    """Return a .docx path for an uploaded Word file.

    .docx files are used directly. Legacy .doc files are accepted too: the app
    first tries real conversion to .docx, which preserves the original Word
    layout. If no converter is available on the server, the upload still does
    not fail: a built-in .docx addendum template is used as a safe fallback so
    the user can generate the document from the form. Exact fonts/indents of an
    old binary .doc can only be preserved after conversion by LibreOffice or
    Microsoft Word.
    """
    suffix = source_path.suffix.lower()
    if suffix == ".docx":
        return source_path
    if suffix != ".doc":
        raise ValueError("Поддерживаются только файлы .doc и .docx.")

    output_dir = Path(work_dir or source_path.parent) / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)

    converters = (
        _convert_doc_with_libreoffice,
        _convert_doc_with_ms_word,
        _convert_doc_with_pandoc,
        _convert_doc_text_fallback,
    )
    for converter in converters:
        try:
            converted = converter(source_path, output_dir)
            if converted and converted.exists():
                return converted
        except Exception:
            # Do not block .doc uploads because one converter is unavailable.
            # The next converter or the final built-in template fallback will handle it.
            continue

    # Last-resort fallback: accept the .doc upload and generate from the selected
    # built-in template instead of showing a hard error to the user.
    fallback_path = output_dir / f"{source_path.stem}_fallback_template.docx"
    return create_builtin_addendum_template(fallback_path, fallback_variant)


def _convert_doc_with_libreoffice(source_path: Path, output_dir: Path) -> Path | None:
    converter = shutil.which("soffice") or shutil.which("libreoffice") or shutil.which("lowriter")
    if not converter:
        return None

    before = {path.resolve() for path in output_dir.glob("*.docx")}
    command = [
        converter,
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(output_dir),
        str(source_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=90)
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(details or "конвертер завершился с ошибкой")

    expected = output_dir / f"{source_path.stem}.docx"
    if expected.exists():
        return expected
    after = [path for path in output_dir.glob("*.docx") if path.resolve() not in before]
    if after:
        return max(after, key=lambda path: path.stat().st_mtime)
    raise RuntimeError("конвертация завершилась, но .docx-файл не найден")


def _convert_doc_with_ms_word(source_path: Path, output_dir: Path) -> Path | None:
    """Convert .doc to .docx using Microsoft Word on Windows, when available."""
    if os.name != "nt":
        return None

    output_path = output_dir / f"{source_path.stem}_word.docx"

    # pywin32 is optional. It is the cleanest option when installed.
    try:
        import win32com.client  # type: ignore

        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        document = None
        try:
            document = word.Documents.Open(str(source_path.resolve()), ReadOnly=True)
            document.SaveAs(str(output_path.resolve()), FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
        finally:
            if document is not None:
                document.Close(False)
            word.Quit()
        return output_path if output_path.exists() else None
    except Exception as pywin32_exc:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise RuntimeError(f"pywin32 недоступен ({pywin32_exc}); PowerShell не найден")

        def ps_quote(value: Path) -> str:
            return str(value.resolve()).replace("'", "''")

        script_path = output_dir / "convert_doc_to_docx.ps1"
        script_path.write_text(
            """$ErrorActionPreference = 'Stop'
$source = '{source}'
$output = '{output}'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$document = $null
try {{
    $document = $word.Documents.Open($source, $false, $true)
    $document.SaveAs([ref] $output, [ref] 16)
}} finally {{
    if ($document -ne $null) {{ $document.Close([ref] $false) }}
    if ($word -ne $null) {{ $word.Quit() }}
}}
""".format(source=ps_quote(source_path), output=ps_quote(output_path)),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"pywin32 недоступен ({pywin32_exc}); PowerShell/Word не смог конвертировать файл: {details}")
        return output_path if output_path.exists() else None



def _convert_doc_with_pandoc(source_path: Path, output_dir: Path) -> Path | None:
    """Try converting legacy .doc with pandoc when it is installed."""
    converter = shutil.which("pandoc")
    if not converter:
        return None
    output_path = output_dir / f"{source_path.stem}_pandoc.docx"
    completed = subprocess.run(
        [converter, str(source_path), "-o", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(details or "pandoc завершился с ошибкой")
    return output_path if output_path.exists() else None


def _convert_doc_text_fallback(source_path: Path, output_dir: Path) -> Path | None:
    """Create a simple .docx from readable text in a legacy .doc file.

    This fallback is intentionally not advertised as layout-preserving. It makes
    old .doc uploads usable on lightweight servers where LibreOffice/Microsoft
    Word are not installed. The structured replacement code can then fill the
    addendum using the regular form fields.
    """
    text = _extract_legacy_doc_text(source_path)
    if not text or len(re.sub(r"\s+", "", text)) < 40:
        return None
    paragraphs = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    paragraphs = [line for line in paragraphs if line]
    if not paragraphs:
        return None
    output_path = output_dir / f"{source_path.stem}_text_fallback.docx"
    _write_minimal_docx(output_path, paragraphs)
    return output_path


def _extract_legacy_doc_text(source_path: Path) -> str:
    for extractor in (_extract_doc_text_with_antiword, _extract_doc_text_with_catdoc, _extract_doc_text_from_binary):
        try:
            text = extractor(source_path)
            if text and len(re.sub(r"\s+", "", text)) >= 40:
                return _clean_extracted_doc_text(text)
        except Exception:
            continue
    return ""


def _extract_doc_text_with_antiword(source_path: Path) -> str:
    tool = shutil.which("antiword")
    if not tool:
        return ""
    completed = subprocess.run(
        [tool, "-m", "UTF-8", str(source_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


def _extract_doc_text_with_catdoc(source_path: Path) -> str:
    tool = shutil.which("catdoc")
    if not tool:
        return ""
    completed = subprocess.run(
        [tool, "-d", "utf-8", str(source_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


def _extract_doc_text_from_binary(source_path: Path) -> str:
    """Very small pure-Python safety net for legacy .doc files.

    It scans the binary file for long UTF-16LE and CP1251 text fragments. This
    cannot preserve formatting and is used only if no real converter/text tool is
    available.
    """
    data = source_path.read_bytes()
    fragments: list[str] = []

    # Most Russian text in old Word .doc files can be found as UTF-16LE runs.
    decoded = data.decode("utf-16le", errors="ignore")
    fragments.extend(_readable_fragments(decoded, min_len=12))

    # Some documents contain ANSI/CP1251 fragments.
    decoded_cp = data.decode("cp1251", errors="ignore")
    fragments.extend(_readable_fragments(decoded_cp, min_len=20))

    # Keep order, remove duplicates and obvious binary noise.
    seen: set[str] = set()
    clean: list[str] = []
    for fragment in fragments:
        fragment = re.sub(r"\s+", " ", fragment).strip()
        if fragment and fragment not in seen and _looks_like_text(fragment):
            seen.add(fragment)
            clean.append(fragment)
    return "\n".join(clean)


def _readable_fragments(text: str, min_len: int = 12) -> list[str]:
    fragments: list[str] = []
    buffer: list[str] = []
    for char in text:
        if char in "\n\r\t" or char == " " or "А" <= char <= "я" or char == "ё" or char == "Ё" or char.isalnum() or char in "№«».,;:!?()/-–—_+@\"'":
            buffer.append(char)
        else:
            if len(buffer) >= min_len:
                fragments.append("".join(buffer))
            buffer = []
    if len(buffer) >= min_len:
        fragments.append("".join(buffer))
    return fragments


def _looks_like_text(value: str) -> bool:
    if len(value) < 8:
        return False
    letters = sum(1 for char in value if char.isalpha())
    return letters >= max(3, len(value) // 5)


def _clean_extracted_doc_text(text: str) -> str:
    text = text.replace("\x00", "")
    lines = []
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"[\t ]+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)

def build_addendum_docx(source_path: Path, output_path: Path, fields: dict[str, str], option_keys: list[str] | None = None) -> list[DocumentChange]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_fields = _normalize_fields(fields)
    changes: list[DocumentChange] = []
    replacements = _build_replacements(normalized_fields)
    appended_clauses = _build_clauses(normalized_fields, option_keys or [])

    with zipfile.ZipFile(source_path, "r") as source_docx, zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as output_docx:
        for item in source_docx.infolist():
            data = source_docx.read(item.filename)
            if _is_word_xml(item.filename):
                root = ET.fromstring(data)
                if item.filename == "word/document.xml":
                    changes.extend(_apply_addendum_structured_edits(root, normalized_fields))
                    if appended_clauses:
                        changes.extend(_append_clauses(root, appended_clauses))
                changes.extend(_replace_text_placeholders(root, replacements))
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output_docx.writestr(item, data)

    return changes


def safe_docx_filename(original_name: str, prefix: str = "dop-soglashenie") -> str:
    stem = Path(original_name or prefix).stem
    stem = re.sub(r"[^\w\-.]+", "_", stem, flags=re.UNICODE).strip("._") or prefix
    return f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"


def _normalize_fields(fields: dict[str, str]) -> dict[str, str]:
    normalized = {key: str(value or "").strip() for key, value in fields.items()}

    owner_count = _normalize_owner_count(normalized.get("owner_count", "1"))
    normalized["owner_count"] = owner_count
    normalized["owner_one_gender"] = _normalize_owner_gender(normalized.get("owner_one_gender"), "female")
    normalized["owner_two_gender"] = _normalize_owner_gender(normalized.get("owner_two_gender"), "male")

    normalized.setdefault("agreement_date", "")
    if not normalized["agreement_date"]:
        normalized["agreement_date"] = russian_date()
    else:
        normalized["agreement_date"] = _normalize_russian_date_text(normalized["agreement_date"])

    # Город не показываем в форме и не перезаписываем: остается тот, что был в загруженном Word.
    normalized["city"] = (normalized.get("city") or "").strip()

    if not normalized.get("contract_full"):
        normalized["contract_full"] = CONTRACT_EMPTY_EXAMPLE
    normalized["contract_full"] = _normalize_contract_text(normalized["contract_full"])

    if normalized.get("apartment_number"):
        normalized["apartment_number"] = _normalize_apartment_number(normalized["apartment_number"])
    if normalized.get("floor_number"):
        normalized["floor_number"] = _normalize_floor_text(normalized["floor_number"])

    normalized["owner_one_data"] = _normalize_owner_data_by_gender(
        normalized.get("owner_one_data") or _owner_data_template(normalized["owner_one_gender"]),
        normalized["owner_one_gender"],
    )
    if owner_count == "2":
        normalized["owner_two_data"] = _normalize_owner_data_by_gender(
            normalized.get("owner_two_data") or _owner_data_template(normalized["owner_two_gender"]),
            normalized["owner_two_gender"],
        )
    else:
        normalized["owner_two_data"] = ""

    normalized["owner_single_phrase"] = _owner_phrase_for_gender(normalized["owner_one_gender"])
    normalized["owners_plural_phrase"] = DEFAULT_OWNER_PLURAL_PHRASE

    transfer_type = str(normalized.get("transfer_type") or "materials").strip().lower()
    if not normalized.get("materials_block"):
        normalized["materials_block"] = CERTIFICATES_EXAMPLE if transfer_type == "certificates" else MATERIALS_AUTO_TEMPLATE
    if transfer_type == "certificates":
        normalized["acceptance_text"] = ACCEPTANCE_GIFT_EXAMPLE
    elif normalized.get("acceptance_text"):
        normalized["acceptance_text"] = _normalize_acceptance_text(normalized["acceptance_text"])
    if not normalized.get("acceptance_text"):
        normalized["acceptance_text"] = ACCEPTANCE_MATERIALS_EXAMPLE

    if normalized.get("creditor_signatures"):
        normalized["creditor_signatures"] = _normalize_signature_block(normalized["creditor_signatures"])
    else:
        normalized["creditor_signatures"] = _build_signatures_from_owners(normalized)
    return normalized


def _normalize_contract_text(raw: str) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if value and not value.startswith("№"):
        value = f"№ {value}"
    if value and re.search(r"\d{4}$", value) and not value.endswith("года"):
        value = f"{value} года"
    return value


def _normalize_apartment_number(raw: str) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if not value:
        return value
    if value.startswith("№"):
        return re.sub(r"^№\s*", "№ ", value)
    return f"№ {value}"


def _normalize_floor_text(raw: str) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if not value:
        return value
    if "этаж" in value.lower() or "этаже" in value.lower():
        return value
    return f"{value} этаже"


def _normalize_owner_count(raw: str) -> str:
    value = str(raw or "1").strip().lower()
    if value in {"2", "two", "два"}:
        return "2"
    return "1"


def _normalize_owner_gender(raw: str | None, default: str = "female") -> str:
    value = str(raw or default).strip().lower()
    if value in {"male", "m", "м", "муж", "мужской", "именуемый"}:
        return "male"
    if value in {"female", "f", "ж", "жен", "женский", "именуемая"}:
        return "female"
    return default


def _owner_data_template(gender: str) -> str:
    return OWNER_DATA_TEMPLATE_MALE if _normalize_owner_gender(gender) == "male" else OWNER_DATA_TEMPLATE_FEMALE


def _owner_phrase_for_gender(gender: str) -> str:
    if _normalize_owner_gender(gender) == "male":
        return (
            "именуемый в дальнейшем «Участник долевого строительства», «Кредитор», "
            "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
            "заключили настоящее Соглашение о нижеследующем:"
        )
    return (
        "именуемая в дальнейшем «Участник долевого строительства», «Кредитор», "
        "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
        "заключили настоящее Соглашение о нижеследующем:"
    )


def _normalize_owner_data_by_gender(raw: str, gender: str) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if not value:
        value = _owner_data_template(gender)
    is_male = _normalize_owner_gender(gender) == "male"
    citizen = "Гражданин" if is_male else "Гражданка"
    registered = "зарегистрирован" if is_male else "зарегистрирована"
    sex = "мужской" if is_male else "женский"

    value = re.sub(r"^Гражданка/Гражданин\b", citizen, value, flags=re.IGNORECASE)
    value = re.sub(r"^Гражданка\b|^Гражданин\b", citizen, value, flags=re.IGNORECASE)
    value = re.sub(r"пол\s+(?:_______|женский|мужской)", f"пол {sex}", value, flags=re.IGNORECASE)
    value = value.replace("зарегистрирован(а)", registered)
    value = re.sub(r"зарегистрирован(?:а)?\b", registered, value, flags=re.IGNORECASE)
    return value


def _extract_owner_full_name(owner_data: str) -> str:
    text = re.sub(r"\s+", " ", (owner_data or "").strip().strip(","))
    text = re.sub(r"^Граждан(?:ка|ин)\s+", "", text, flags=re.IGNORECASE)
    match = re.match(r"([А-ЯЁ][а-яё\-]+)\s+([А-ЯЁ][а-яё\-]+)(?:\s+([А-ЯЁ][а-яё\-]+))?", text)
    if not match:
        return ""
    parts = [part for part in match.groups() if part]
    if len(parts) < 2:
        return ""
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    return f"{parts[0]} {parts[1][0]}."


def _build_signatures_from_owners(fields: dict[str, str]) -> str:
    lines: list[str] = []
    first = _extract_owner_full_name(fields.get("owner_one_data", ""))
    if first:
        lines.append(f"___________________/{first}")
    if fields.get("owner_count") == "2":
        second = _extract_owner_full_name(fields.get("owner_two_data", ""))
        if second:
            lines.append(f"___________________/{second}")
    return "\n".join(lines)


def _normalize_owner_phrase(raw: str, singular: bool) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if not value:
        return DEFAULT_OWNER_SINGLE_PHRASE if singular else DEFAULT_OWNER_PLURAL_PHRASE
    lower = value.lower()
    if singular:
        if lower in {"именуемая", "именуемый"}:
            return (
                "именуемая в дальнейшем «Участник долевого строительства», «Кредитор», "
                "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
                "заключили настоящее Соглашение о нижеследующем:"
                if lower == "именуемая"
                else
                "именуемый в дальнейшем «Участник долевого строительства», «Кредитор», "
                "с другой стороны, руководствуясь ст. 409 Гражданского кодекса РФ, "
                "заключили настоящее Соглашение о нижеследующем:"
            )
    else:
        if lower == "именуемые":
            return DEFAULT_OWNER_PLURAL_PHRASE
    return value


def _normalize_acceptance_text(raw: str) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    lower = value.lower()
    if lower in {"материалы", "строительные материалы"}:
        return ACCEPTANCE_MATERIALS_EXAMPLE
    if lower in {"сертификаты", "подарочные сертификаты"}:
        return ACCEPTANCE_GIFT_EXAMPLE
    return value


def _normalize_signature_block(raw: str) -> str:
    lines = []
    for line in _split_lines(raw):
        clean = line.strip()
        if not clean:
            continue
        if "/" not in clean:
            clean = f"___________________/{clean}"
        lines.append(clean)
    return "\n".join(lines)


def _normalize_russian_date_text(raw: str) -> str:
    value = raw.strip()
    if not value:
        return russian_date()
    for pattern in (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", r"^(\d{4})-(\d{1,2})-(\d{1,2})$"):
        match = re.match(pattern, value)
        if not match:
            continue
        if pattern.startswith("^(\\d{1,2})"):
            day, month, year = map(int, match.groups())
        else:
            year, month, day = map(int, match.groups())
        return russian_date(date(year, month, day))
    if "года" not in value and re.search(r"\d{4}$", value):
        return f"{value} года"
    return value


def _build_replacements(fields: dict[str, str]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if fields.get("contract_full"):
        contract_full = fields["contract_full"]
        replacements["{{contract_full}}"] = contract_full
        replacements["{contract_full}"] = contract_full
        replacements["[contract_full]"] = contract_full
    for key, value in fields.items():
        clean_value = str(value or "").strip()
        if not clean_value:
            continue
        variants = {
            key,
            key.upper(),
            key.replace("_", " ").upper(),
            ADDENDUM_FIELD_LABELS.get(key, key),
        }
        for variant in variants:
            replacements[f"{{{{{variant}}}}}"] = clean_value
            replacements[f"{{{variant}}}"] = clean_value
            replacements[f"[{variant}]"] = clean_value
    return replacements


def _is_word_xml(name: str) -> bool:
    return (
        name == "word/document.xml"
        or (name.startswith("word/header") and name.endswith(".xml"))
        or (name.startswith("word/footer") and name.endswith(".xml"))
    )


def _apply_addendum_structured_edits(root: ET.Element, fields: dict[str, str]) -> list[DocumentChange]:
    changes: list[DocumentChange] = []
    changes.extend(_replace_agreement_date_and_city(root, fields.get("agreement_date", ""), fields.get("city", "")))
    changes.extend(_replace_owner_block(root, fields))
    changes.extend(_replace_contract_references(root, fields.get("contract_full", "")))
    changes.extend(_replace_materials_block(root, fields.get("materials_block", "")))
    changes.extend(_replace_defects_parts(root, fields))
    changes.extend(_replace_acceptance_text(root, fields.get("acceptance_text", "")))
    changes.extend(_replace_creditor_signatures(root, fields.get("creditor_signatures", "")))
    return changes


def _document_body(root: ET.Element) -> ET.Element | None:
    return root.find(f"{XML_NS}body")


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{XML_NS}t"))


def _set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    text_nodes = list(paragraph.iter(f"{XML_NS}t"))
    if not text_nodes:
        run = ET.SubElement(paragraph, f"{XML_NS}r")
        text_node = ET.SubElement(run, f"{XML_NS}t")
        text_nodes = [text_node]
    text_nodes[0].text = text
    if text.startswith(" ") or text.endswith(" "):
        text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for text_node in text_nodes[1:]:
        text_node.text = ""




def _text_node_ranges(paragraph: ET.Element) -> list[tuple[ET.Element, int, int]]:
    ranges: list[tuple[ET.Element, int, int]] = []
    cursor = 0
    for node in paragraph.iter(f"{XML_NS}t"):
        value = node.text or ""
        start = cursor
        cursor += len(value)
        ranges.append((node, start, cursor))
    return ranges


def _replace_paragraph_regex_preserve_runs(paragraph: ET.Element, pattern: re.Pattern[str], replacement: str, count: int = 0) -> bool:
    """Replace text in a paragraph without flattening all runs.

    Word often splits one visual line into many runs: normal text, highlighted text,
    bold text, and so on.  Rebuilding the paragraph would keep only the first run's
    formatting and can break the look of uploaded templates.  This helper maps the
    regex match back to the original <w:t> nodes and changes only the matched range.
    Text before and after the range stays in its original runs.
    """
    full_text = _paragraph_text(paragraph)
    if not full_text:
        return False
    matches = list(pattern.finditer(full_text))
    if count:
        matches = matches[:count]
    if not matches:
        return False

    # Work backwards so earlier character offsets stay valid.
    for match in reversed(matches):
        _replace_paragraph_range_preserve_runs(paragraph, match.start(), match.end(), replacement)
    return True


def _replace_paragraph_range_preserve_runs(paragraph: ET.Element, start: int, end: int, replacement: str) -> None:
    ranges = _text_node_ranges(paragraph)
    if not ranges:
        _set_paragraph_text(paragraph, replacement)
        return

    first_index = None
    last_index = None
    for idx, (_, node_start, node_end) in enumerate(ranges):
        if first_index is None and node_end >= start and node_start <= start:
            first_index = idx
        if node_start <= end and node_end >= end:
            last_index = idx
            break
    if first_index is None:
        first_index = 0
    if last_index is None:
        last_index = len(ranges) - 1

    first_node, first_start, _ = ranges[first_index]
    last_node, last_start, _ = ranges[last_index]
    first_text = first_node.text or ""
    last_text = last_node.text or ""
    prefix = first_text[:max(0, start - first_start)]
    suffix = last_text[max(0, end - last_start):]

    first_node.text = prefix + replacement + suffix
    if first_node.text.startswith(" ") or first_node.text.endswith(" "):
        first_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for idx in range(first_index + 1, last_index + 1):
        ranges[idx][0].text = ""

def _body_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [child for child in list(body) if child.tag == f"{XML_NS}p"]


def _child_index(body: ET.Element, child: ET.Element) -> int:
    return list(body).index(child)


def _paragraph_like(text: str, template: ET.Element | None = None) -> ET.Element:
    paragraph = ET.Element(f"{XML_NS}p")
    if template is not None:
        ppr = template.find(f"{XML_NS}pPr")
        if ppr is not None:
            paragraph.append(deepcopy(ppr))
        run_template = template.find(f"{XML_NS}r")
    else:
        run_template = None
    run = ET.SubElement(paragraph, f"{XML_NS}r")
    if run_template is not None:
        rpr = run_template.find(f"{XML_NS}rPr")
        if rpr is not None:
            run.append(deepcopy(rpr))
    text_node = ET.SubElement(run, f"{XML_NS}t")
    if text.startswith(" ") or text.endswith(" "):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text
    return paragraph


def _insert_replacement_paragraphs(body: ET.Element, start_child: ET.Element, end_child: ET.Element, texts: list[str]) -> None:
    children = list(body)
    start_index = children.index(start_child)
    end_index = children.index(end_child)
    template = start_child
    for _ in range(end_index - start_index + 1):
        body.remove(list(body)[start_index])
    for offset, text in enumerate(texts):
        body.insert(start_index + offset, _paragraph_like(text, template))


def _split_lines(text: str) -> list[str]:
    return [line.rstrip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


def _normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _format_with_fields(text: str, fields: dict[str, str]) -> str:
    if not text:
        return ""
    try:
        return text.format_map(_DefaultFields(fields))
    except Exception:
        return text


def _resolve_defects_block(fields: dict[str, str]) -> str:
    manual_text = (fields.get("defects_block") or "").strip()
    if manual_text:
        return _format_with_fields(manual_text, fields)

    basis = (fields.get("defects_basis") or "").strip()
    apartment_number = (fields.get("apartment_number") or "").strip()
    floor_number = (fields.get("floor_number") or "").strip()
    contract_full = (fields.get("contract_full") or "").strip()
    if not all([basis, apartment_number, floor_number, contract_full]):
        return ""
    return _format_with_fields(DEFECTS_EXAMPLE, fields)


def _replace_agreement_date_and_city(root: ET.Element, agreement_date: str, city: str) -> list[DocumentChange]:
    """Replace only the highlighted date/city fragments and keep the paragraph layout intact."""
    changes: list[DocumentChange] = []
    if not agreement_date:
        return changes
    body = _document_body(root)
    if body is None:
        return changes
    date_regex = re.compile(r"«(?:\d{1,2}|__+)»\s+[А-Яа-яёЁ_]+\s+(?:\d{4}|__+)\s+года")
    city_regex = re.compile(r"город\s+[А-Яа-яёЁA-Za-z0-9.\-]+")
    for paragraph in _body_paragraphs(body):
        original = _paragraph_text(paragraph)
        if not original:
            continue
        normalized = _normalize_for_search(original)
        if "город" not in normalized and not date_regex.search(original):
            continue

        before = original
        touched = False
        if city and "город" in normalized:
            touched = _replace_paragraph_regex_preserve_runs(paragraph, city_regex, city, count=1) or touched
        touched = _replace_paragraph_regex_preserve_runs(paragraph, date_regex, agreement_date, count=1) or touched
        if touched:
            changes.append(DocumentChange("replace", "Дата соглашения", before, _paragraph_text(paragraph)))
            break
    return changes


def _replace_owner_block(root: ET.Element, fields: dict[str, str]) -> list[DocumentChange]:
    owner_one = fields.get("owner_one_data", "").strip()
    owner_two = fields.get("owner_two_data", "").strip()
    owner_count = _normalize_owner_count(fields.get("owner_count", "1"))
    if not owner_one:
        return []

    body = _document_body(root)
    if body is None:
        return []
    paragraphs = _body_paragraphs(body)
    start_idx = None
    for idx, paragraph in enumerate(paragraphs):
        text = _paragraph_text(paragraph).strip()
        if text.startswith("Граждан"):
            start_idx = idx
            break
    if start_idx is None:
        return []
    end_idx = None
    for idx in range(start_idx, len(paragraphs)):
        text = _paragraph_text(paragraphs[idx])
        if "именуем" in text and "Кредитор" in text:
            end_idx = idx
            break
    if end_idx is None:
        end_idx = start_idx
    before = "\n".join(_paragraph_text(paragraphs[idx]).strip() for idx in range(start_idx, end_idx + 1) if _paragraph_text(paragraphs[idx]).strip())

    if owner_count == "2" and owner_two:
        phrase = fields.get("owners_plural_phrase", "").strip() or DEFAULT_OWNER_PLURAL_PHRASE
        replacement = [
            f"{owner_one.rstrip(' ,')},",
            f"{owner_two.rstrip(' ,')}, {phrase}",
        ]
    else:
        phrase = fields.get("owner_single_phrase", "").strip() or DEFAULT_OWNER_SINGLE_PHRASE
        replacement = [f"{owner_one.rstrip(' ,')}, {phrase}"]

    _insert_replacement_paragraphs(body, paragraphs[start_idx], paragraphs[end_idx], replacement)
    after = "\n".join(replacement)
    return [DocumentChange("replace", "Собственник / кредитор", before, after)]


def _replace_contract_references(root: ET.Element, contract_full: str) -> list[DocumentChange]:
    contract_full = (contract_full or "").strip()
    if not contract_full:
        return []
    changes: list[DocumentChange] = []
    body = _document_body(root)
    if body is None:
        return changes
    # Ищет фрагменты вида: № МИР/... от «28» декабря 2024 года.
    # Замена выполняется внутри существующих run-ов, чтобы не сбивать шрифты, отступы и интервалы.
    pattern = re.compile(r"№\s*МИР/[А-ЯA-ZЁ0-9_\-/]+\s+от\s+«(?:\d{1,2}|__+)»\s+[А-Яа-яёЁ_]+\s+(?:\d{4}|__+)(?:\s+года)?")
    for paragraph in _body_paragraphs(body):
        original = _paragraph_text(paragraph)
        if "№" not in original or "МИР/" not in original or " от " not in original:
            continue
        if _replace_paragraph_regex_preserve_runs(paragraph, pattern, contract_full):
            changes.append(DocumentChange("replace", "Номер договора", original, _paragraph_text(paragraph)))
    return changes


def _replace_materials_block(root: ET.Element, materials_block: str) -> list[DocumentChange]:
    lines = _split_lines(materials_block)
    if not lines:
        return []
    body = _document_body(root)
    if body is None:
        return []
    paragraphs = _body_paragraphs(body)
    start_idx = None
    for idx, paragraph in enumerate(paragraphs):
        if "Кредитор согласен на получение от Должника" in _paragraph_text(paragraph):
            start_idx = idx + 1
            break
    if start_idx is None or start_idx >= len(paragraphs):
        return []

    end_idx = None
    for idx in range(start_idx, len(paragraphs)):
        text = _paragraph_text(paragraphs[idx]).strip()
        normalized = _normalize_for_search(text)
        if normalized.startswith("(вид") or normalized.startswith("взамен устранения"):
            end_idx = idx - 1
            break
    if end_idx is None:
        return []

    while start_idx <= end_idx and not _paragraph_text(paragraphs[start_idx]).strip():
        start_idx += 1
    while end_idx >= start_idx and not _paragraph_text(paragraphs[end_idx]).strip():
        end_idx -= 1
    if start_idx > end_idx:
        anchor = paragraphs[start_idx - 1]
        insert_index = _child_index(body, anchor) + 1
        for offset, line in enumerate(lines):
            body.insert(insert_index + offset, _paragraph_like(line, anchor))
        return [DocumentChange("replace", "Что получает кредитор", "", "\n".join(lines))]

    before = "\n".join(_paragraph_text(paragraphs[idx]).strip() for idx in range(start_idx, end_idx + 1) if _paragraph_text(paragraphs[idx]).strip())
    _insert_replacement_paragraphs(body, paragraphs[start_idx], paragraphs[end_idx], lines)
    return [DocumentChange("replace", "Что получает кредитор", before, "\n".join(lines))]


def _replace_defects_parts(root: ET.Element, fields: dict[str, str]) -> list[DocumentChange]:
    """Update the highlighted parts of the defects paragraph without rebuilding the whole paragraph."""
    body = _document_body(root)
    if body is None:
        return []

    manual_value = (fields.get("defects_block") or "").strip()
    if manual_value:
        value = _format_with_fields(manual_value, fields)
        for paragraph in _body_paragraphs(body):
            original = _paragraph_text(paragraph)
            if _normalize_for_search(original).startswith("взамен устранения"):
                _set_paragraph_text(paragraph, value)
                return [DocumentChange("replace", "Текст “взамен устранения...”", original, value)]
        return []

    changes: list[DocumentChange] = []
    basis = (fields.get("defects_basis") or "").strip()
    apartment = (fields.get("apartment_number") or "").strip()
    floor = (fields.get("floor_number") or "").strip()

    for paragraph in _body_paragraphs(body):
        original = _paragraph_text(paragraph)
        normalized = _normalize_for_search(original)
        if not normalized.startswith("взамен устранения"):
            continue

        touched = False
        if basis:
            touched = _replace_paragraph_regex_preserve_runs(
                paragraph,
                re.compile(r"^.*?(?=\s+квартиры\s+№)", re.DOTALL),
                basis,
                count=1,
            ) or touched
        if apartment:
            touched = _replace_paragraph_regex_preserve_runs(
                paragraph,
                re.compile(r"№\s*[0-9A-Za-zА-Яа-яЁё\-/]+(?=,\s*наход)", re.IGNORECASE),
                apartment,
                count=1,
            ) or touched
        if floor:
            touched = _replace_paragraph_regex_preserve_runs(
                paragraph,
                re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+\s+этаже(?=,)", re.IGNORECASE),
                floor,
                count=1,
            ) or touched
        if touched:
            changes.append(DocumentChange("replace", "Текст “взамен устранения...”", original, _paragraph_text(paragraph)))
        break
    return changes


def _replace_acceptance_text(root: ET.Element, acceptance_text: str) -> list[DocumentChange]:
    value = (acceptance_text or "").strip()
    if not value:
        return []
    body = _document_body(root)
    if body is None:
        return []
    for paragraph in _body_paragraphs(body):
        original = _paragraph_text(paragraph)
        normalized = _normalize_for_search(original)
        if normalized.startswith("должник передал") and "кредитор принял" in normalized:
            _set_paragraph_text(paragraph, value)
            return [DocumentChange("replace", "Фраза о передаче", original, value)]
    return []


def _replace_creditor_signatures(root: ET.Element, creditor_signatures: str) -> list[DocumentChange]:
    lines = _split_lines(creditor_signatures)
    if not lines:
        return []
    body = _document_body(root)
    if body is None:
        return []
    paragraphs = _body_paragraphs(body)
    label_idx = None
    for idx, paragraph in enumerate(paragraphs):
        if "«Кредитор»" in _paragraph_text(paragraph):
            label_idx = idx
    if label_idx is None:
        return []

    label_paragraph = paragraphs[label_idx]
    label_text = _paragraph_text(label_paragraph)
    before_parts: list[str] = []
    line_offset = 0

    # В некоторых шаблонах первая подпись стоит в одной строке с «Кредитор».
    # Оставляем эту строку на месте, чтобы не ломать горизонтальные отступы.
    inline_match = re.match(r"(.*?«Кредитор»)(\s*)(.*)$", label_text)
    if inline_match and inline_match.group(3).strip():
        before_parts.append(inline_match.group(3).strip())
        _set_paragraph_text(label_paragraph, f"{inline_match.group(1)}{inline_match.group(2)}{lines[0]}")
        line_offset = 1

    remaining_lines = lines[line_offset:]
    start_idx = label_idx + 1
    signature_paragraphs: list[ET.Element] = []
    for paragraph in paragraphs[start_idx:]:
        text = _paragraph_text(paragraph)
        # После блока подписей в этих соглашениях обычно нет других смысловых абзацев.
        if text.strip():
            signature_paragraphs.append(paragraph)
            before_parts.append(text.strip())

    for idx, line in enumerate(remaining_lines):
        if idx < len(signature_paragraphs):
            _set_paragraph_text(signature_paragraphs[idx], line)
        else:
            anchor = signature_paragraphs[-1] if signature_paragraphs else label_paragraph
            body.insert(_child_index(body, anchor) + 1, _paragraph_like(line, anchor))

    # Удаляем лишние старые подписи, если теперь строк меньше.
    for paragraph in signature_paragraphs[len(remaining_lines):]:
        body.remove(paragraph)

    before = "\n".join(part for part in before_parts if part)
    return [DocumentChange("replace", "Кредитор снизу", before, "\n".join(lines))]


def _build_clauses(fields: dict[str, str], option_keys: list[str]) -> list[tuple[str, str]]:
    clauses: list[tuple[str, str]] = []
    for key in option_keys:
        option = ADDENDUM_OPTIONS.get(key)
        if not option:
            continue
        clause = option["clause"].format_map(_DefaultFields(fields))
        clauses.append((option["title"], clause))
    return clauses


def _replace_text_placeholders(root: ET.Element, replacements: dict[str, str]) -> list[DocumentChange]:
    changes: list[DocumentChange] = []
    for paragraph in root.iter(f"{XML_NS}p"):
        text_nodes = list(paragraph.iter(f"{XML_NS}t"))
        if not text_nodes:
            continue
        original = "".join(node.text or "" for node in text_nodes)
        updated = original
        for placeholder, value in replacements.items():
            if placeholder in updated:
                updated = updated.replace(placeholder, value)
        if updated != original:
            text_nodes[0].text = updated
            for text_node in text_nodes[1:]:
                text_node.text = ""
            changes.append(DocumentChange("replace", "Замена в шаблоне", original, updated))
    return changes


def _append_clauses(root: ET.Element, clauses: list[tuple[str, str]]) -> list[DocumentChange]:
    body = root.find(f"{XML_NS}body")
    if body is None:
        return []
    insert_at = len(body)
    for index, child in enumerate(list(body)):
        if child.tag == f"{XML_NS}sectPr":
            insert_at = index
            break

    paragraphs = [_paragraph("Дополнительные изменения")]
    for number, (_, clause) in enumerate(clauses, start=1):
        paragraphs.append(_paragraph(f"{number}. {clause}"))

    for offset, paragraph in enumerate(paragraphs):
        body.insert(insert_at + offset, paragraph)

    return [
        DocumentChange("append", title, "", clause)
        for title, clause in clauses
    ]


def _paragraph(text: str) -> ET.Element:
    paragraph = ET.Element(f"{XML_NS}p")
    run = ET.SubElement(paragraph, f"{XML_NS}r")
    text_node = ET.SubElement(run, f"{XML_NS}t")
    text_node.text = text
    return paragraph


class _DefaultFields(dict):
    def __init__(self, values: dict[str, str]):
        super().__init__({key: str(value or "").strip() for key, value in values.items()})

    def __getitem__(self, key: str) -> str:
        value = super().get(key, "")
        return value or f"[{ADDENDUM_FIELD_LABELS.get(key, key)}]"

    def __missing__(self, key: str) -> str:
        return f"[{escape(ADDENDUM_FIELD_LABELS.get(key, key))}]"
