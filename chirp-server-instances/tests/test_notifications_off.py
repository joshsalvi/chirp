"""CHIRP_NOTIFICATIONS_OFF stops every push and email from this server."""


def test_notifications_off(monkeypatch):
    from app.services import apns_push, push_notifications, email_service
    monkeypatch.setenv("CHIRP_NOTIFICATIONS_OFF", "1")
    r = apns_push.send_apns_push(None, "tok", "t", "b")
    assert not r and "CHIRP_NOTIFICATIONS_OFF" in r.error
    r = push_notifications.send_push_to_subscription(None, object(), "t", "b")
    assert not r and "CHIRP_NOTIFICATIONS_OFF" in r.error
    assert email_service._send({"host": "x", "port": 25}, "a@b.c", "s", "<p>h</p>") is False
    monkeypatch.setenv("CHIRP_NOTIFICATIONS_OFF", "")
    from app.services.notify_off import notifications_off
    assert not notifications_off()
