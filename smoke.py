import time, json, sys
sys.path.insert(0, ".")
from pc.runtime import Runtime
r=Runtime()
r.update_config({"overlay": False, "ocr_source":"demo", "poll_interval":1.0, "translator":"free", "dedup_window":5})
print("START", r.start())
time.sleep(2)
for i in range(8):
    time.sleep(1.2)
    st=r.state()
    print(st["status"], st["status_text"], st["running"], st["stats"], st["peers"], st["relay_online"])
    if len(r.subs)>=3: break
with r.lock:
    for s in list(r.subs)[-6:]:
        print(s["lang"], s["src"], "=>", s["trans"], s["engine"], s["degraded"])
    print("LOGS")
    for l in list(r.logs)[-12:]: print(l["level"], l["msg"])
print("DEV", json.dumps(r.asr_devices(), ensure_ascii=False)[:400])
print("MODELS", r.asr_models_state())
r.shutdown()
print("DONE")
