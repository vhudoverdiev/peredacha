import base64
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse, parse_qs

from app.two_factor import current_totp, generate_totp_secret, provisioning_uri, qr_svg_data_uri, verify_totp


class TwoFactorContractsTests(unittest.TestCase):
    RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_generated_secret_is_base32_without_padding_and_decodes(self):
        with patch("app.two_factor.secrets.token_bytes", return_value=b"1" * 20):
            secret = generate_totp_secret()

        self.assertNotIn("=", secret)
        self.assertEqual(base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8)), b"1" * 20)

    def test_totp_matches_known_rfc_vector(self):
        with patch("app.two_factor.time.time", return_value=59):
            self.assertEqual(current_totp(self.RFC_SECRET, digits=8), "94287082")

    def test_verify_totp_accepts_neighbor_window_and_strips_spaces(self):
        with patch("app.two_factor.time.time", return_value=90):
            previous_code = current_totp(self.RFC_SECRET)

        with patch("app.two_factor.time.time", return_value=120):
            self.assertTrue(verify_totp(self.RFC_SECRET, f" {previous_code[:3]} {previous_code[3:]} "))
            self.assertFalse(verify_totp(self.RFC_SECRET, previous_code, window=0))
            self.assertFalse(verify_totp(self.RFC_SECRET, "12345"))
            self.assertFalse(verify_totp(None, previous_code))

    def test_invalid_secret_never_raises_from_verify(self):
        with patch("app.two_factor.time.time", return_value=120):
            self.assertFalse(verify_totp("not base32!!!", "123456"))

    def test_provisioning_uri_encodes_issuer_username_and_totp_parameters(self):
        uri = provisioning_uri("qa@example.com", self.RFC_SECRET, issuer="Peredacha CRM")
        parsed = urlparse(uri)
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "otpauth")
        self.assertEqual(parsed.netloc, "totp")
        self.assertEqual(unquote(parsed.path), "/Peredacha CRM:qa@example.com")
        self.assertEqual(params["secret"], [self.RFC_SECRET])
        self.assertEqual(params["issuer"], ["Peredacha CRM"])
        self.assertEqual(params["algorithm"], ["SHA1"])
        self.assertEqual(params["digits"], ["6"])
        self.assertEqual(params["period"], ["30"])

    def test_qr_svg_data_uri_returns_empty_for_empty_value(self):
        self.assertEqual(qr_svg_data_uri("   "), "")


if __name__ == "__main__":
    unittest.main()
