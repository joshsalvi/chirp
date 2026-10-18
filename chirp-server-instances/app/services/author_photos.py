"""Profile photos for note authors: notes store only the author's username,
so the photo is looked up here and added as author_photo_url."""


def with_author_photos(db, items: list) -> list:
    from ..models import User
    names = {i.get("author") for i in items if i.get("author")}
    photos = {}
    if names:
        for u in db.query(User).filter(User.username.in_(names)).all():
            if getattr(u, "photo_url", None):
                photos[u.username] = u.photo_url
    for i in items:
        i["author_photo_url"] = photos.get(i.get("author"))
    return items
