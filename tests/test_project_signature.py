import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from PIL import Image
from tests import test_apartment_history_contracts as fixture
from app import db
from app.models import Project
from app.services.contractor_claim_docx import _write_claim_docx
from app.services.project_signature import normalize_signature
from werkzeug.datastructures import FileStorage


def image_upload(color="black"):
    data = BytesIO()
    Image.new("RGBA", (300, 80), color).save(data, format="PNG")
    data.seek(0)
    return data


class ProjectSignatureTests(unittest.TestCase):
    setUp = fixture.ApartmentHistoryContractsTests.setUp
    tearDown = fixture.ApartmentHistoryContractsTests.tearDown

    def save(self, **extra):
        return self.client.post(f"/objects/{self.project.id}/edit",
                                data={"name": self.project.name, "has_apartments": "y", **extra},
                                content_type="multipart/form-data")

    def test_upload_replace_preserve_remove_and_document(self):
        self.assertEqual(self.save(signature=(image_upload(), "sign.png")).status_code, 302)
        first = self.project.signature_image
        self.assertTrue(first)
        self.assertEqual(self.save().status_code, 302)
        self.assertEqual(self.project.signature_image, first)
        self.save(signature=(image_upload("blue"), "new.png"))
        self.assertNotEqual(self.project.signature_image, first)
        with TemporaryDirectory() as folder:
            output = Path(folder) / "claim.docx"
            _write_claim_docx(output, [], project=self.project, contractor=None, author=self.user)
            with ZipFile(output) as archive:
                self.assertEqual(archive.read("word/media/image1.png"),
                                 base64.b64decode(self.project.signature_image))
                self.assertIn(b'cy="253333"', archive.read("word/document.xml"))
        other = Project(name="Other")
        db.session.add(other)
        db.session.commit()
        self.assertIsNone(other.signature_image)
        self.save(remove_signature="y")
        self.assertIsNone(self.project.signature_image)

    def test_no_signature_means_no_image_in_claim(self):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "claim.docx"
            _write_claim_docx(output, [], project=self.project, contractor=None, author=self.user)
            with ZipFile(output) as archive:
                self.assertNotIn("word/media/image1.png", archive.namelist())
                self.assertNotIn(b"<w:drawing>", archive.read("word/document.xml"))
                self.assertNotIn(b"rIdStamp", archive.read("word/_rels/document.xml.rels"))

    def test_invalid_image_keeps_existing_signature(self):
        self.save(signature=(image_upload(), "sign.png"))
        previous = self.project.signature_image
        response = self.save(signature=(BytesIO(b"not an image"), "sign.png"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось прочитать", response.get_data(as_text=True))
        self.assertEqual(self.project.signature_image, previous)

    def test_create_with_signature(self):
        response = self.client.post("/objects/new", data={
            "name": "Signature object", "has_apartments": "y",
            "signature": (image_upload(), "signature.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(name="Signature object").one()
        self.assertTrue(project.signature_image)
        self.assertIsNone(self.project.signature_image)

    def test_oversized_file_rejected(self):
        with self.assertRaises(ValueError):
            normalize_signature(FileStorage(stream=BytesIO(b"x" * (5 * 1024 * 1024 + 1))))

if __name__ == "__main__":
    unittest.main()
