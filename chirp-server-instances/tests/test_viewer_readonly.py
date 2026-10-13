"""0.5.11.a: viewer accounts can't change recordings; their allowed writes still work."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_viewer_write_rules():
    from app.main import viewer_may_write as ok
    for m, p in [("GET", "/api/v1/recordings/abc"), ("POST", "/api/v1/auth/me/profile"),
                 ("PUT", "/api/v1/auth/me/notification-prefs"), ("POST", "/api/v1/notifications/read-all"),
                 ("DELETE", "/api/v1/notifications"), ("POST", "/api/v1/push/register-native"),
                 ("POST", "/api/v1/recordings/abc/comments"), ("PUT", "/api/v1/birds/p1/comments/c1"),
                 ("POST", "/api/v1/live-detect/analyze"), ("POST", "/api/v1/instances/switch"),
                 ("POST", "/api/v1/birds/ensure/Blue Jay"), ("POST", "/api/v1/recordings/abc/share")]:
        assert ok(m, p), (m, p)
    for m, p in [("DELETE", "/api/v1/recordings/abc"), ("PATCH", "/api/v1/recordings/abc"),
                 ("POST", "/api/v1/recordings/abc/archive"), ("POST", "/api/v1/recordings/bulk-delete"),
                 ("POST", "/api/v1/recordings/abc/reanalyze"), ("POST", "/api/v1/recordings/abc/ai-recheck"),
                 ("PUT", "/api/v1/settings"), ("POST", "/api/v1/live-detect/save-session"),
                 ("PUT", "/api/v1/auth/users/u1/role"), ("POST", "/api/v1/recordings/upload-manual"),
                 ("DELETE", "/api/v1/birds/photos/x")]:
        assert not ok(m, p), (m, p)
