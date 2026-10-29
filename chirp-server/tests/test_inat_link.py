"""iNaturalist posts carry the Chirp link exactly once."""
from unittest.mock import patch, MagicMock

from app.services import inat_service as inat


def test_with_chirp_link_appends_once():
    out = inat.with_chirp_link("AI second opinion: Song Sparrow")
    assert out.endswith("Recorded with Chirp: https://ourchirp.com")
    assert inat.with_chirp_link(out) == out
    assert inat.with_chirp_link("") == "Recorded with Chirp: https://ourchirp.com"
    assert inat.with_chirp_link("see OurChirp.com") == "see OurChirp.com"


def test_post_comment_body_includes_link():
    resp = MagicMock(status_code=200, text="{}")
    resp.json.return_value = {"id": 1}
    client = MagicMock()
    client.__enter__.return_value.post.return_value = resp
    with patch.object(inat.httpx, "Client", return_value=client):
        inat.post_comment("tok", 123, "Nice call")
    post = client.__enter__.return_value.post
    body = post.call_args.kwargs["json"]["comment"]["body"]
    assert body == "Nice call\n\nRecorded with Chirp: https://ourchirp.com"
