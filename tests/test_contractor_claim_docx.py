import re
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from config import Config
from app import create_app, db
from app.models import Apartment, Contractor, Project, STATUS_CONCESSION, STATUS_DONE, STATUS_NOT_STARTED, Task, User, WorkPoint
from app.services.contractor_claim_docx import _salutation, build_contractor_claim_docx


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "contractor-claim-docx-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


def _docx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"\s+", " ", text)


def _document_root(path: Path):
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    return ET.fromstring(xml)


def _assert_bold_text(testcase: unittest.TestCase, document_xml: str, text: str) -> None:
    testcase.assertRegex(document_xml, rf"<w:rPr>.*?<w:b/>.*?</w:rPr><w:t(?: [^>]*)?>{re.escape(text)}[^<]*</w:t>")


class ContractorClaimDocxTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        TestConfig.EXPORT_FOLDER = self.tempdir.name
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(
            name='ЖК "Квартал 100" - 7 очередь',
            address="Архангельская обл., г. Северодвинск, ул. Ломоносова 79 к 3",
            developer_name='ООО СЗ "Аквилон-Северодвинск"',
            inn_kpp="2901297953/290101001",
            ogrn="1192901006924",
            legal_address="164515, г. Северодвинск, ул. Ломоносова, д. 85, корпус 1, офис 2",
            developer_director="Поплевин В.Е.",
            developer_representative="Худовердиев В.С.",
            developer_representative_phone="8 900 000-00-00",
        )
        self.contractor = Contractor(
            project=self.project,
            name='ООО "Коробка"',
            legal_address="164520, Архангельская обл., г. Северодвинск, ул. Индустриальная, д.27, кв.7",
            contract_number="07-04/2025",
            contract_date="07.04.2025",
            director_full_name="Елена Петровна",
            email="contractor@example.test",
        )
        self.point = WorkPoint(point_number="12", short_name="12. Возведение коробки здания")
        self.contractor.work_points.append(self.point)
        self.apartment = Apartment(project=self.project, apartment_number="1", owner_name="Иванов И.И.")
        self.apartment.construction_number = "1-2-1"
        self.contractor.apartments.append(self.apartment)
        self.author = User(
            username="engineer",
            full_name="Костылева Н.А.",
            phone="8(8184) 52-00-00 (доб.354)",
            email="kostyleva@group-akvilon.ru",
            password_hash="unused",
        )
        self.open_task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            source_uid="claim-open",
            description="Не выполнена заделка штробы.",
            source_row_index=10,
            status=STATUS_NOT_STARTED,
        )
        self.second_open_task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            source_uid="claim-open-2",
            description="Сбить наплывы строительных смесей.",
            source_row_index=11,
            status=STATUS_NOT_STARTED,
        )
        self.done_task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            source_uid="claim-done",
            description="Выполнена зачистка поверхности.",
            source_row_index=12,
            status=STATUS_DONE,
            is_done=True,
            responsible=self.author,
        )
        self.concession_task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            source_uid="claim-concession",
            description="Согласовано денежное возмещение.",
            source_row_index=13,
            status=STATUS_CONCESSION,
            is_done=False,
        )
        db.session.add_all([self.project, self.contractor, self.point, self.apartment, self.author, self.open_task, self.second_open_task, self.done_task, self.concession_task])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.tempdir.cleanup()

    def test_claim_docx_uses_project_contractor_and_author_data(self):
        path = build_contractor_claim_docx(
            [self.open_task, self.second_open_task, self.done_task, self.concession_task],
            project=self.project,
            contractor=self.contractor,
            author=self.author,
        )

        self.assertTrue(path.exists())
        text = _docx_text(path)
        self.assertIn("ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ", text)
        self.assertIn("Претензия", text)
        self.assertIn('Дефектная ведомость ЖК "Квартал 100" - 7 очередь', text)
        self.assertIn("2901297953/290101001", text)
        self.assertIn("1192901006924", text)
        self.assertIn('ООО "Коробка"', text)
        self.assertIn("Уважаемая Елена Петровна!", text)
        self.assertIn("договора подряда № 07-04/2025 от 07.04.2025", text)
        self.assertIn("гарантийных обязательств п.1.7, договора подряда", text)
        self.assertNotIn("гарантийных обязательств ________", text)
        self.assertIn("Направлено на адрес эл. почты: contractor@example.test", text)
        self.assertIn("№ кв", text)
        self.assertIn("№ строительный", text)
        self.assertIn("1-2-1", text)
        self.assertNotIn("Возведение коробки здания", text)
        self.assertNotIn("12. Возведение коробки здания", text)
        self.assertIn("Не выполнена заделка штробы.", text)
        self.assertIn("Сбить наплывы строительных смесей.", text)
        self.assertIn("Выполнена зачистка поверхности.", text)
        self.assertIn('Выполненные работы ЖК "Квартал 100" - 7 очередь', text)
        self.assertIn("Согласовано денежное возмещение. (отступные)", text)
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        pages = document_xml.split('<w:br w:type="page"/>')
        self.assertEqual(len(pages), 3)
        self.assertNotIn("Согласовано денежное возмещение.", pages[1])
        self.assertIn("Согласовано денежное возмещение. (отступные)", pages[2])
        self.assertIn("8 900 000-00-00 Худовердиев В.С.", text)
        self.assertNotIn("Худовердиев В.С. 8 900 000-00-00", text)
        self.assertIn("Исп.: Костылева Н.А.", text)
        self.assertIn("8(8184) 52-00-00 (доб.354)", text)
        self.assertIn("kostyleva@group-akvilon.ru", text)

    def test_letter_shift_preserves_width_and_table_cells(self):
        from app.services.contractor_claim_docx import _shift_letter_block, _paragraph, _signature_block
        paragraph = _shift_letter_block(_paragraph("Text", left=284, right=-709))
        self.assertIn('w:left="114"', paragraph)
        self.assertIn('w:right="-539"', paragraph)
        table = _signature_block(self.project)
        shifted = _shift_letter_block(table)
        self.assertIn('<w:tblInd w:w="-170" w:type="dxa"/>', shifted)
        self.assertEqual(table.split("</w:tblPr>", 1)[1], shifted.split("</w:tblPr>", 1)[1])

    def test_empty_sections_do_not_create_pages(self):
        for tasks, breaks in (([], 0), ([self.open_task], 1), ([self.done_task], 1)):
            path = build_contractor_claim_docx(
                tasks, project=self.project, contractor=self.contractor, author=self.author,
            )
            root = _document_root(path)
            self.assertEqual(len(root.findall(f".//{W}br[@{W}type='page']")), breaks)
            body = root.find(f"{W}body")
            if tasks:
                self.assertEqual(list(body)[-2].tag, f"{W}tbl")

    def test_claim_docx_matches_reference_page_and_table_layout(self):
        import base64
        from app.services.contractor_claim_docx import STAMP_IMAGE_PATH
        self.project.signature_image = base64.b64encode(STAMP_IMAGE_PATH.read_bytes()).decode("ascii")
        path = build_contractor_claim_docx(
            [self.open_task, self.second_open_task, self.done_task, self.concession_task],
            project=self.project,
            contractor=self.contractor,
            author=self.author,
        )
        root = _document_root(path)
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
            document_rels = archive.read("word/_rels/document.xml.rels").decode("utf-8")
            stamp_bytes = archive.read("word/media/image1.png")
            content_types = archive.read("[Content_Types].xml").decode("utf-8")

        page_breaks = root.findall(f".//{W}br[@{W}type='page']")
        self.assertEqual(len(page_breaks), 2)
        self.assertIn("<wp:inline", document_xml)
        self.assertIn('r:embed="rIdStamp"', document_xml)
        self.assertRegex(document_xml, r'cx="[1-9][0-9]+"')
        self.assertRegex(document_xml, r'cy="[1-9][0-9]+"')
        self.assertIn('Id="rIdStamp"', document_rels)
        self.assertIn('Target="media/image1.png"', document_rels)
        self.assertIn('ContentType="image/png"', content_types)
        self.assertGreater(len(stamp_bytes), 0)
        self.assertRegex(document_xml, r'<w:color w:val="0000FF"/>.*?<w:t>kostyleva@group-akvilon\.ru</w:t>')
        self.assertRegex(document_xml, r'<w:color w:val="0000FF"/>.*?<w:t>contractor@example\.test</w:t>')
        first_page_xml = document_xml.split('<w:br w:type="page"/>', 1)[0]
        self.assertIn("<w:t>Исп.: Костылева Н.А.</w:t>", first_page_xml)
        self.assertIn("<w:t>т. 8(8184) 52-00-00 (доб.354)</w:t>", first_page_xml)
        self.assertIn("<w:t>kostyleva@group-akvilon.ru</w:t>", first_page_xml)
        self.assertRegex(first_page_xml, r'<w:spacing w:after="0" w:line="379" w:lineRule="auto"/>.*?</w:p><w:p><w:pPr><w:jc w:val="right"/>.*?<w:t>Исп\.:')
        self.assertRegex(first_page_xml, r'<w:t>Исп\.: Костылева Н\.А\.</w:t>.*?</w:p><w:p><w:pPr><w:jc w:val="right"/>.*?<w:t>т\. 8\(8184\) 52-00-00 \(доб\.354\)</w:t>')
        self.assertRegex(first_page_xml, r'<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t>Исп\.: Костылева Н\.А\.')
        self.assertIn("<w:t>Поплевин В.Е.</w:t>", first_page_xml)
        self.assertNotIn('w:right="-992"', first_page_xml)
        self.assertIn('<w:bottom w:val="single" w:sz="4" w:space="1" w:color="auto"/>', document_xml)
        self.assertIn('<w:jc w:val="center"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>', document_xml)
        self.assertRegex(document_xml, r'<w:sz w:val="28"/>.*?<w:t>ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ</w:t>')
        self.assertRegex(document_xml, r'<w:sz w:val="44"/>.*?<w:t>Специализированный застройщик</w:t>')
        self.assertRegex(document_xml, r'<w:sz w:val="20"/>.*?<w:t>ИНН/КПП 2901297953/290101001, ОГРН 1192901006924</w:t>')
        self.assertIn('<w:ind w:left="114" w:right="-539" w:firstLine="424"/>', document_xml)
        self.assertIn('<w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>', document_xml)
        self.assertIn("<w:t>164520, Архангельская обл., г. Северодвинск</w:t>", document_xml)
        self.assertIn("<w:t>ул. Индустриальная, д.27, кв.7</w:t>", document_xml)
        _assert_bold_text(self, document_xml, "Исх. №____  от")
        _assert_bold_text(self, document_xml, 'ООО "Коробка"')
        _assert_bold_text(self, document_xml, "№ 07-04/2025")
        _assert_bold_text(self, document_xml, "164520, Архангельская обл., г. Северодвинск")
        _assert_bold_text(self, document_xml, "ул. Индустриальная, д.27, кв.7")
        _assert_bold_text(self, document_xml, "Уважаемая Елена Петровна!")
        self.assertRegex(document_xml, r'<w:jc w:val="center"/>.*?<w:t>Уважаемая Елена Петровна!</w:t>')
        self.assertRegex(
            document_xml,
            r'<w:t>ул\. Индустриальная, д\.27, кв\.7</w:t></w:r></w:p>'
            r'<w:p><w:pPr><w:ind w:left="114" w:right="-539"/>.*?</w:p>'
            r'<w:p><w:pPr><w:jc w:val="center"/>'
            r'<w:ind w:left="114" w:right="-539"/>'
            r'<w:spacing w:before="0" w:after="120"',
        )

        page_margins = root.find(f".//{W}sectPr/{W}pgMar")
        self.assertEqual(page_margins.attrib[f"{W}top"], "567")
        self.assertEqual(page_margins.attrib[f"{W}right"], "1133")
        self.assertEqual(page_margins.attrib[f"{W}bottom"], "709")
        self.assertEqual(page_margins.attrib[f"{W}left"], "1134")

        tables = root.findall(f".//{W}tbl")
        self.assertEqual(len(tables), 3)
        signature_grid = [column.attrib[f"{W}w"] for column in tables[0].findall(f"{W}tblGrid/{W}gridCol")]
        first_grid = [column.attrib[f"{W}w"] for column in tables[1].findall(f"{W}tblGrid/{W}gridCol")]
        completed_grid = [column.attrib[f"{W}w"] for column in tables[2].findall(f"{W}tblGrid/{W}gridCol")]
        self.assertEqual(signature_grid, ["5900", "1600", "1840"])
        signature_vertical = [cell.attrib[f"{W}val"] for cell in tables[0].findall(f".//{W}vAlign")]
        self.assertEqual(signature_vertical, ["center", "center", "center"])
        self.assertEqual(first_grid, ["701", "1985", "6653"])
        self.assertEqual(completed_grid, ["846", "2126", "6367"])

        first_title_size = tables[1].find(f".//{W}sz").attrib[f"{W}val"]
        self.assertEqual(first_title_size, "28")
        body_sizes = [node.attrib[f"{W}val"] for node in tables[1].findall(f".//{W}sz")]
        self.assertIn("24", body_sizes)

    def test_salutation_detects_director_gender(self):
        self.contractor.director_full_name = "Владимир Сергеевич"
        self.assertEqual(_salutation(self.contractor), "Уважаемый Владимир Сергеевич!")
        self.contractor.director_full_name = "Елена Петровна"
        self.assertEqual(_salutation(self.contractor), "Уважаемая Елена Петровна!")
        self.contractor.director_full_name = ""
        self.assertEqual(_salutation(self.contractor), "Уважаемые коллеги!")


if __name__ == "__main__":
    unittest.main()
