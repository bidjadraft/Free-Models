#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, time, urllib.request, urllib.error

API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()
API = "https://ollama.com/api"
OUT_FILE = "ollama.txt"
MAX_SECONDS = 10

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

def list_models(key):
    st, d = http_json(f"{API}/tags", headers={"Authorization": f"Bearer {key}"})
    if st != 200:
        return []
    return [m["name"] for m in d.get("models", []) if "name" in m]

def test_model(key, model):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False
    }
    t0 = time.time()
    st, d = http_json(f"{API}/chat", "POST",
                      {"Authorization": f"Bearer {key}"}, body, timeout=MAX_SECONDS)
    elapsed = time.time() - t0
    if st == 0:
        return "slow" if elapsed >= MAX_SECONDS else "error"
    if elapsed > MAX_SECONDS:
        return "slow"
    
    msg = json.dumps(d, ensure_ascii=False).lower()
    if st == 200 and "message" in d:
        return "free"
    
    if "not included in your free usage" in msg or "add usage credits" in msg:
        return "paid"
    
    if "model not found" in msg or "does not exist" in msg:
        return "gone"
    if st == 429:
        return "ratelimited"
    return "error"

def rank_score(name):
    n = name.lower()
    if "gemma" in n:
        return 1
    if "gpt" in n:
        return 2
    return 3

def read_old():
    try:
        return [l.strip() for l in open(OUT_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []

def write_models(models):
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for m in sorted(models, key=rank_score):
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

    working, paid, slow, other = [], [], [], []
    print("testing...")
    for m in sorted(all_models):
        cat = test_model(key, m)
        icon = {"free": "OK", "paid": "PAID", "gone": "GONE", "ratelimited": "RATE", "slow": "SLOW", "error": "ERR"}.get(cat, "?")
        print(f"{icon} {m}")
        if cat == "free":
            working.append(m)
        elif cat == "paid":
            paid.append(m)
        elif cat == "slow":
            slow.append(m)
        else:
            other.append(m)
        time.sleep(1)

    old = read_old()
    added = [m for m in working if m not in old]
    removed = [m for m in old if m not in working]
    write_models(working)

    print("-" * 40)
    print(f"free={len(working)}")
    print(f"paid={len(paid)}")
    print(f"slow={len(slow)}")
    print("added=" + (",".join(added) if added else "-"))
    print("removed=" + (",".join(removed) if removed else "-"))
    print(f"file={OUT_FILE}")

if __name__ == "__main__":
    main()
