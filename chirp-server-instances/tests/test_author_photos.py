"""Note authors' profile photos are added to note responses."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_with_author_photos():
    from app.services.author_photos import with_author_photos

    class U:
        def __init__(self, n, p): self.username, self.photo_url = n, p

    class Q:
        def filter(self, *a): return self
        def all(self): return [U("wren", "/api/v1/auth/me/photo/1.jpg"), U("jay", None)]

    class DB:
        def query(self, m): return Q()

    out = with_author_photos(DB(), [{"author": "wren"}, {"author": "jay"}, {"author": None}])
    assert [o["author_photo_url"] for o in out] == ["/api/v1/auth/me/photo/1.jpg", None, None]
