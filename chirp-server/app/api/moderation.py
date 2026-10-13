"""
Reporting and blocking for notes (comments), which other members of a site
can read. Report: the site's admins get an inbox notification and a push
linking to the note. Block: the blocked person's notes are hidden from the
person who blocked them, everywhere notes are listed.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Comment, ContentBlock, ContentReport
from .auth import get_current_user

router = APIRouter()


def blocked_authors(db: Session, user) -> set:
    if user is None:
        return set()
    return {b.blocked_author for b in db.query(ContentBlock).filter(ContentBlock.user_id == user.id).all()}


def may_change(c: Comment, user) -> bool:
    """The author or an admin may edit or delete a note (anyone, with sign-in off)."""
    return user is None or user.role == "admin" or (c.author or "").lower() == user.username.lower()


def author_for(user, body: dict) -> str:
    """Notes are credited to the signed-in person, never to a name the app sends."""
    if user is not None:
        return user.username
    return (body.get("author") or "Anonymous")[:80]


def _where(c: Comment) -> str:
    return f"/recordings/{c.recording_id}" if c.recording_id else f"/library/{c.bird_profile_id}"


@router.post("/report")
def report_comment(body: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Comment).filter(Comment.id == body.get("comment_id"), Comment.deleted_at.is_(None)).first()
    if not c:
        raise HTTPException(404, "Note not found")
    reason = (body.get("reason") or "").strip()[:500] or None
    reporter = user.username if user else "Anonymous"
    db.add(ContentReport(comment_id=c.id, reporter=reporter, author=c.author, reason=reason))
    db.commit()
    try:
        from ..services.push_notifications import send_push_to_all
        excerpt = (c.body or "")[:80]
        send_push_to_all(db, "Note reported",
                         f"{reporter} reported a note by {c.author}: “{excerpt}”" + (f" ({reason})" if reason else ""),
                         url=_where(c), tag="report",
                         user_filter=lambda u: getattr(u, "role", None) == "admin")
    except Exception:
        pass  # the report is saved either way
    return {"ok": True}


@router.get("/blocks")
def list_blocks(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return sorted(blocked_authors(db, user), key=str.lower)


@router.post("/blocks")
def block_author(body: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user is None:
        raise HTTPException(400, "Sign in to block people")
    author = (body.get("author") or "").strip()
    if not author or author.lower() == user.username.lower():
        raise HTTPException(400, "Choose someone else to block")
    if author not in blocked_authors(db, user):
        db.add(ContentBlock(user_id=user.id, blocked_author=author, created_at=datetime.utcnow()))
        db.commit()
    return {"ok": True}


@router.delete("/blocks/{author}")
def unblock_author(author: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user is None:
        return {"ok": True}
    db.query(ContentBlock).filter(ContentBlock.user_id == user.id, ContentBlock.blocked_author == author).delete()
    db.commit()
    return {"ok": True}
