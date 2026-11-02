"""Web Push: VAPID keys, device subscriptions and sending.

Keys come from the environment (VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY, both base64url raw)
or are generated on first use and stored in the database, so a fresh install works
without any setup. Push needs a secure origin: http://localhost on the same computer,
or HTTPS when the app is reached from a phone.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlmodel import Session, select

from app.models import AppSetting, PushSubscription

log = logging.getLogger(__name__)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class VapidKeys:
    private_raw: str  # base64url, 32 bytes
    public_raw: str  # base64url, 65-byte uncompressed point (what the browser needs)


def _setting(session: Session, key: str) -> Optional[str]:
    row = session.get(AppSetting, key)
    return row.value if row else None


def vapid_keys(session: Session) -> VapidKeys:
    env_priv, env_pub = os.getenv("VAPID_PRIVATE_KEY"), os.getenv("VAPID_PUBLIC_KEY")
    if env_priv and env_pub and "your-" not in env_priv:
        return VapidKeys(env_priv, env_pub)
    priv, pub = _setting(session, "vapid_private"), _setting(session, "vapid_public")
    if priv and pub:
        return VapidKeys(priv, pub)
    v = Vapid02()
    v.generate_keys()
    priv = _b64url(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
    pub = _b64url(
        v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    session.add(AppSetting(key="vapid_private", value=priv))
    session.add(AppSetting(key="vapid_public", value=pub))
    session.commit()
    return VapidKeys(priv, pub)


def vapid_subject() -> str:
    # Push services want a contact; it is sent to them, never shown to anyone else.
    return os.getenv("VAPID_SUBJECT") or "mailto:weekforge@localhost"


def save_subscription(session: Session, endpoint: str, p256dh: str, auth: str, user_agent: str) -> PushSubscription:
    sub = session.exec(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).first()
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent[:200])
    else:
        sub.p256dh, sub.auth = p256dh, auth
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def remove_subscription(session: Session, endpoint: str) -> bool:
    sub = session.exec(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).first()
    if sub is None:
        return False
    session.delete(sub)
    session.commit()
    return True


@dataclass
class SendResult:
    sent: int = 0
    removed: int = 0  # subscriptions the push service says are gone (404/410)
    failed: int = 0


def send_to_all(session: Session, title: str, body: str, url: str = "/", tag: str = "") -> SendResult:
    keys = vapid_keys(session)
    vapid = Vapid02.from_raw(keys.private_raw.encode())
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    result = SendResult()
    for sub in session.exec(select(PushSubscription)).all():
        try:
            webpush(
                {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": vapid_subject()},
                ttl=60 * 60,
                timeout=10,
            )
            result.sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                session.delete(sub)
                result.removed += 1
            else:
                log.warning("push failed (%s) for subscription %s", status, sub.id)
                result.failed += 1
    session.commit()
    return result
