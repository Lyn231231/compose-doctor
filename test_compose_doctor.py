import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose_doctor import check, parse_ports  # noqa: E402


def codes(doc, check_paths=False):
    return sorted(f.code for f in check(doc, check_paths))


class TestParsePorts(unittest.TestCase):
    def test_short_forms(self):
        self.assertEqual(parse_ports("8080:80"), ("0.0.0.0", "8080"))
        self.assertEqual(parse_ports("127.0.0.1:8080:80"), ("127.0.0.1", "8080"))
        self.assertEqual(parse_ports("8080:80/udp"), ("0.0.0.0", "8080"))

    def test_long_form_and_container_only(self):
        self.assertEqual(parse_ports({"published": 9000, "host_ip": "127.0.0.1"}),
                         ("127.0.0.1", "9000"))
        self.assertIsNone(parse_ports({"target": 80}))
        self.assertIsNone(parse_ports("80"))


HEALTHY = {
    "services": {
        "web": {
            "image": "nginx:1.27-alpine",
            "restart": "unless-stopped",
            "ports": ["127.0.0.1:8080:80"],
            "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost"]},
            "logging": {"driver": "json-file", "options": {"max-size": "10m"}},
            "volumes": ["data:/usr/share/nginx/html"],
        }
    },
    "volumes": {"data": {}},
}


class TestChecks(unittest.TestCase):
    def test_clean_doc(self):
        self.assertEqual(codes(HEALTHY), [])

    def test_missing_image_and_build(self):
        self.assertIn("E001", codes({"services": {"x": {"restart": "always"}}}))

    def test_duplicate_host_port(self):
        doc = {"services": {
            "a": {"image": "x:1", "restart": "always", "ports": ["8080:80"]},
            "b": {"image": "y:1", "restart": "always", "ports": ["8080:81"]},
        }}
        self.assertIn("E003", codes(doc))

    def test_latest_tag(self):
        doc = {"services": {"a": {"image": "redis", "restart": "always"}}}
        self.assertIn("W102", codes(doc))
        doc = {"services": {"a": {"image": "redis:7.4", "restart": "always"}}}
        self.assertNotIn("W102", codes(doc))

    def test_unused_volume(self):
        doc = dict(HEALTHY)
        doc["volumes"] = {"data": {}, "orphan": {}}
        self.assertIn("W101", codes(doc))

    def test_unbounded_logs(self):
        doc = {"services": {"a": {"image": "x:1", "restart": "always"}}}
        self.assertIn("W105", codes(doc))

    def test_env_without_default(self):
        doc = {"services": {"a": {"image": "x:1", "restart": "always",
                                  "environment": ["DB_PASSWORD"]}}}
        self.assertIn("W106", codes(doc))
        doc = {"services": {"a": {"image": "x:1", "restart": "always",
                                  "environment": {"URL": None}}}}
        self.assertIn("W106", codes(doc))

    def test_bind_missing_only_when_asked(self):
        doc = {"services": {"a": {"image": "x:1", "restart": "always",
                                  "volumes": ["/definitely/not/here:/data"]}}}
        self.assertNotIn("E002", codes(doc))
        self.assertIn("E002", codes(doc, check_paths=True))

    def test_wildcard_bind_is_info(self):
        doc = {"services": {"a": {"image": "x:1", "restart": "always", "ports": ["8080:80"]}}}
        self.assertIn("I201", codes(doc))


if __name__ == "__main__":
    unittest.main()
