#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, json, base64, time, urllib.request, urllib.error

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
API = "https://generativelanguage.googleapis.com/v1beta"
OUT_FILE = "free_pdf_models.txt"

FAMILY = re.compile(r"^gemini-", re.I)
TIER = re.compile(r"-(flash-lite|flash)(?:-|$)", re.I)
CAPABILITY = re.compile(
    r"(tts|audio|live|transcribe|translate|embedding|aqa|image|imagen|veo|"
    r"omni|lyria|nano-banana|gemma|learnlm|robotics|computer|speech|music|"
    r"video|clip|vision-encoder|guard|retrieval|pro)", re.I)


def http_json(url, method="GET", headers=None, body=None, timeout=60):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": {"message": str(e)}}
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def make_test_pdf():
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 24 Tf 100 700 Td (Hello PDF Test) Tj ET"
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(pdf))
        pdf += str(i).encode() + b" 0 obj\n" + o + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        pdf += ("%010d 00000 n \n" % off).encode()
    pdf += (b"trailer\n<< /Size " + str(len(objs) + 1).encode() +
            b" /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    return pdf


def list_models(key):
    st, d = http_json(f"{API}/models?pageSize=1000", headers={"x-goog-api-key": key})
    return d.get("models", []) if st == 200 else []


def name_tier(name):
    n = name.lower()
    if not FAMILY.search(n):
        return None
    if CAPABILITY.search(n):
        return None
    m = TIER.search(n)
    return m.group(1).lower() if m else None


def is_doc_model(name):
    return name_tier(name) is not None


def rank_score(name):
    n = name.lower()
    v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
    version = float(v.group(1)) if v else 0.0
    tier = name_tier(name) or ""
    tier_w = {"flash": 2, "flash-lite": 1}.get(tier, 0)
    score = version * 100 + tier_w * 10
    if "preview" in n:
        score -= 2
    if "latest" in n:
        score += 5
    return score


def test_model(key, model, pdf_b64):
    body = {"contents": [{"parts": [
        {"text": "What is this file? Reply with OK only."},
        {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}}
    ]}]}
    st, d = http_json(f"{API}/models/{model}:generateContent", "POST",
                      {"x-goog-api-key": key}, body)
    msg = json.dumps(d, ensure_ascii=False).lower()
    if st == 200:
        return "free"
    if st in (401, 403):
        return "paid"
    if st == 400:
        return "no_pdf"
    if st == 404:
        return "gone"
    if st == 429:
        if "billing" in msg or "denied" in msg or "not available" in msg:
            return "paid"
        return "ratelimited"
    return "error"


def read_old_models():
    try:
        return [l.strip() for l in open(OUT_FILE, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []


def write_models(models):
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for m in sorted(models, key=rank_score, reverse=True):
            f.write(m + "\n")


def main():
    key = API_KEY
    if not key:
        print("NO_KEY")
        return

    all_models = list_models(key)
    print(f"total={len(all_models)}")
    if not all_models:
        print("FETCH_FAIL")
        return

    candidates = []
    for m in all_models:
        name = m["name"].split("/")[-1]
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        if not is_doc_model(name):
            continue
        candidates.append(name)
    candidates = sorted(set(candidates))
    print(f"candidates={len(candidates)}")

    pdf_b64 = base64.b64encode(make_test_pdf()).decode()
    working, paid, other = [], [], []
    print("testing...")
    for m in candidates:
        cat = test_model(key, m, pdf_b64)
        icon = {"free": "OK", "paid": "PAID", "no_pdf": "NOPDF",
                "gone": "GONE", "ratelimited": "RATE", "error": "ERR"}.get(cat, "?")
        print(f"{icon} {m}")
        if cat == "free":
            working.append(m)
        elif cat == "paid":
            paid.append(m)
        else:
            other.append(m)
        time.sleep(1)

    old = read_old_models()
    added = [m for m in working if m not in old]
    removed = [m for m in old if m not in working]
    write_models(working)

    print("-" * 40)
    print(f"free={len(working)}")
    print(f"paid={len(paid)}")
    print("added=" + (",".join(added) if added else "-"))
    print("removed=" + (",".join(removed) if removed else "-"))
    print(f"file={OUT_FILE}")


if __name__ == "__main__":
    main()
