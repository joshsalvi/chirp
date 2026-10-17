"""The release script once overwrote CHANGELOG.md with only the newest entry."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_changelog_keeps_history():
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    versions = re.findall(r"(?m)^## (\d+\.\d+\.\d+\.?[a-z]*)", text)
    assert len(versions) > 200
    assert "0.1.0.a" in versions or any(v.startswith("0.1.") for v in versions)
    newest = [v for v in versions if v.startswith("0.5.14.")]
    assert len(newest) == len(set(newest))
