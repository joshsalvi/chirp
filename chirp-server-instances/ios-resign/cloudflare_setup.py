#!/usr/bin/env python3
"""
Put the re-sign page (port 8099) on https://iosresign.ourchirp.com through a
Cloudflare Tunnel, behind Cloudflare Access so only the listed emails can open
it. Safe to run again: it reuses the tunnel, DNS record and Access app it
finds and updates them.

    CF_API_TOKEN=... python3 cloudflare_setup.py \
        --account 17f7812beec0c527583ac428818fa5fa \
        --zone e985b279e2ea714fc9ecccce7b9c8c20 \
        --hostname iosresign.ourchirp.com --email josh.salvi@gmail.com

Token permissions: Account → Cloudflare Tunnel: Edit, Account → Access: Apps
and Policies: Edit, Zone (ourchirp.com) → DNS: Edit.

Prints the tunnel token: put it in the stack's .env as RESIGN_TUNNEL_TOKEN
(the cloudflared container in the ios-resign profile runs it).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"


class CF:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                data = json.load(e)
            except Exception:
                raise SystemExit(f"{method} {path}: HTTP {e.code}")
        if not data.get("success", False):
            errs = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in data.get("errors") or [])
            raise SystemExit(f"{method} {path} failed: {errs or data}")
        return data.get("result")


def tunnel(cf, acc, name):
    found = cf.call("GET", f"/accounts/{acc}/cfd_tunnel?name={name}&is_deleted=false") or []
    if found:
        t = found[0]
        print(f"Tunnel {name}: reusing {t['id']}")
    else:
        t = cf.call("POST", f"/accounts/{acc}/cfd_tunnel", {"name": name, "config_src": "cloudflare"})
        print(f"Tunnel {name}: created {t['id']}")
    return t["id"]


def ingress(cf, acc, tid, hostname, service):
    cf.call("PUT", f"/accounts/{acc}/cfd_tunnel/{tid}/configurations", {"config": {"ingress": [
        {"hostname": hostname, "service": service},
        {"service": "http_status:404"},
    ]}})
    print(f"Ingress: {hostname} → {service}")


def dns(cf, zone, hostname, tid):
    target = f"{tid}.cfargotunnel.com"
    rec = {"type": "CNAME", "name": hostname, "content": target, "proxied": True,
           "comment": "Chirp iOS re-sign page (Cloudflare Tunnel)"}
    found = cf.call("GET", f"/zones/{zone}/dns_records?name={hostname}") or []
    if found:
        r = found[0]
        if r["type"] != "CNAME":
            raise SystemExit(f"{hostname} already has a {r['type']} record; remove it first")
        cf.call("PUT", f"/zones/{zone}/dns_records/{r['id']}", rec)
        print(f"DNS: updated {hostname} → {target}")
    else:
        cf.call("POST", f"/zones/{zone}/dns_records", rec)
        print(f"DNS: created {hostname} → {target}")


def access(cf, acc, hostname, emails):
    include = [{"email": {"email": e}} for e in emails]
    apps = cf.call("GET", f"/accounts/{acc}/access/apps") or []
    app = next((a for a in apps if a.get("domain") == hostname), None)
    body = {"name": "Chirp iOS re-sign", "domain": hostname, "type": "self_hosted",
            "session_duration": "24h", "app_launcher_visible": False,
            "policies": [{"name": "Chirp admins", "decision": "allow", "include": include,
                          "precedence": 1}]}
    if app:
        cf.call("PUT", f"/accounts/{acc}/access/apps/{app['id']}", body)
        print(f"Access: updated app for {hostname} (allowed: {', '.join(emails)})")
    else:
        cf.call("POST", f"/accounts/{acc}/access/apps", body)
        print(f"Access: created app for {hostname} (allowed: {', '.join(emails)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", required=True)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--hostname", default="iosresign.ourchirp.com")
    ap.add_argument("--service", default="http://localhost:8099")
    ap.add_argument("--email", action="append", required=True, help="allowed to open the page (repeatable)")
    ap.add_argument("--name", default="chirp-ios-resign")
    ap.add_argument("--no-access", action="store_true", help="skip Cloudflare Access (not recommended)")
    a = ap.parse_args()
    token = os.environ.get("CF_API_TOKEN")
    if not token:
        sys.exit("Set CF_API_TOKEN")
    cf = CF(token)
    tid = tunnel(cf, a.account, a.name)
    ingress(cf, a.account, tid, a.hostname, a.service)
    dns(cf, a.zone, a.hostname, tid)
    if not a.no_access:
        access(cf, a.account, a.hostname, a.email)
    tok = cf.call("GET", f"/accounts/{a.account}/cfd_tunnel/{tid}/token")
    print("\nAdd to the stack's .env:")
    print(f"RESIGN_TUNNEL_TOKEN={tok}")
    print(f"RESIGN_PUBLIC_URL=https://{a.hostname}/")


if __name__ == "__main__":
    main()
