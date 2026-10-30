"""
Test doubles, so the suite runs with no API keys and no network.

FakeTurbopuffer   a small in-memory imitation of the turbopuffer HTTP API,
                  served on localhost. It stores rows, applies the filters
                  this app uses (ContainsAny, Eq, In, Glob, And), deletes by
                  filter, and ranks by word overlap. The real SDK talks to it,
                  so request shapes are exercised for real.
FakeClaude        returns scripted replies, including streaming, and records
                  what it was sent.
"""

from __future__ import annotations

import fnmatch
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse


def _words(s) -> set:
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


def _match(row: dict, f) -> bool:
    if f is None:
        return True
    if f[0] in ("And", "Or"):
        parts = [_match(row, x) for x in f[1]]
        return all(parts) if f[0] == "And" else any(parts)
    attr, op, val = f[0], f[1], f[2]
    v = row.get(attr)
    if op == "ContainsAny":
        return bool(set(v or []) & set(val))
    if op == "Eq":
        return v == val
    if op == "In":
        return v in val
    if op == "Glob":
        return fnmatch.fnmatchcase(str(v or ""), val)
    raise ValueError(f"filter {op} not imitated")


class FakeTurbopuffer:
    def __init__(self):
        self.db: dict[str, dict] = {}
        self.requests: list = []
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, code=200):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _ns(self):
                return urlparse(self.path).path.split("/namespaces/")[-1].split("/")[0]

            def do_DELETE(self):
                if self._ns() not in fake.db:   # like the real API: deleting a missing namespace is a 404
                    return self._send({"error": "namespace not found", "status": "error"}, 404)
                fake.db.pop(self._ns())
                self._send({"status": "ok"})

            def do_GET(self):
                pre = parse_qs(urlparse(self.path).query).get("prefix", [""])[0]
                self._send({"namespaces": [{"id": n} for n in fake.db if n.startswith(pre)], "next_cursor": None})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])) or b"{}")
                ns = self._ns()
                fake.requests.append((self.path, body))
                if urlparse(self.path).path.endswith("/query"):
                    if ns not in fake.db:
                        return self._send({"error": "namespace not found", "status": "error"}, 404)
                    if "queries" in body:
                        lists = [fake._query(ns, q) for q in body["queries"]]
                        fused, seen = [], set()
                        for i in range(max(map(len, lists), default=0)):
                            for l in lists:
                                if i < len(l) and l[i]["id"] not in seen:
                                    seen.add(l[i]["id"])
                                    fused.append(l[i])
                        return self._send({"results": [{"rows": fused}], "billing": {}, "performance": {}})
                    return self._send({"rows": fake._query(ns, body), "billing": {}, "performance": {}})
                if "delete_by_filter" in body and ns not in fake.db:
                    return self._send({"error": "namespace not found", "status": "error"}, 404)
                rows = fake.db.setdefault(ns, {})
                if "delete_by_filter" in body:
                    for k in [k for k, r in rows.items() if _match(r, body["delete_by_filter"])]:
                        del rows[k]
                for k in body.get("deletes", []):
                    rows.pop(k, None)
                for r in body.get("upsert_rows", []):
                    rows[r["id"]] = r
                self._send({"status": "OK", "message": "ok", "rows_affected": len(body.get("upsert_rows", [])),
                            "billing": {}})

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.port}"

    def _query(self, ns: str, q: dict) -> list:
        rows = [r for r in self.db.get(ns, {}).values() if _match(r, q.get("filters"))]
        rank = q.get("rank_by")
        if rank and len(rank) == 3 and rank[1] in ("ANN", "BM25"):
            text = rank[2][1] if rank[1] == "ANN" else rank[2]
            qw = _words(text)
            scored = sorted(rows, key=lambda r: -len(qw & _words(r.get("content", ""))))
            key = "$dist" if rank[1] == "ANN" else "$score"
            out = [dict(r, **{key: round(1 / (1 + len(qw & _words(r.get("content", "")))), 4)}) for r in scored]
        elif rank:
            out = sorted(rows, key=lambda r: r.get(rank[0]) or 0, reverse=rank[1] == "desc")
        else:
            out = rows
        out = out[: q.get("top_k", 10)]
        keep = q.get("include_attributes")
        if isinstance(keep, list):
            out = [{k: v for k, v in r.items() if k in keep or k in ("id", "$dist", "$score")} for r in out]
        return out

    def close(self):
        self.server.shutdown()


# ---------------------------------------------------------------------------
def text(t):
    return NS(type="text", text=t)


def tool(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


def reply(blocks, stop="end_turn", tin=500, tout=80):
    return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=tin, output_tokens=tout))


class _Stream:
    def __init__(self, final):
        self.final = final
        self.text_stream = iter([b.text[i:i + 12] for b in final.content if b.type == "text"
                                 for i in range(0, len(b.text), 12)])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.final


class FakeClaude:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list = []

    @property
    def messages(self):
        return self

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)

    def stream(self, **kw):
        self.calls.append(kw)
        return _Stream(self.script.pop(0))
