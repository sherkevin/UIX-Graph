import json

with open(r'D:\Codes\UIX-Graph\config\reject_errors.diagnosis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== STEPS ===")
for s in data.get('steps', []):
    sid = s['id']
    has_result = 'result' in s
    has_next = len(s.get('next', []))
    mid = s.get('metric_id', '-')
    desc = s.get('description', '')[:60]
    print(f"  step id={sid} (type={type(sid).__name__}), metric={mid}, result={has_result}, next={has_next}, desc={desc}")

print("\n=== SCENES ===")
for sc in data.get('diagnosis_scenes', []):
    sid = sc['id']
    sn = sc.get('start_node', '?')
    print(f"  scene id={sid} (type={type(sid).__name__}), start_node={sn} (type={type(sn).__name__})")

print("\n=== STEP 1 BRANCHES ===")
for s in data.get('steps', []):
    if str(s['id']) == '1':
        for b in s.get('next', []):
            t = b.get('target')
            cond = b.get('condition', '')
            op = b.get('operator', '')
            limit = b.get('limit', '')
            print(f"  branch: target={t}(type={type(t).__name__}), cond={cond}, op={op}, limit={limit}")

print("\n=== STEP 10 ===")
for s in data.get('steps', []):
    if str(s['id']) in ('10', '11'):
        details = s.get('details', [])
        params = (details[0].get('params', {}) if details else {})
        print(f"  step {s['id']}: params={list(params.keys())}")
        for b in s.get('next', []):
            print(f"    next: target={b.get('target')}, results={list(b.get('results', {}).keys())}")

print("\n=== LEAF NODES (steps with result) ===")
for s in data.get('steps', []):
    if s.get('result'):
        print(f"  step {s['id']}: result={s['result']}")
        continue
    for detail in s.get('details') or []:
        if detail.get('result'):
            print(f"  step {s['id']}: result={detail['result']}")
        elif isinstance(detail.get('results'), dict) and detail['results'].get('rootCause'):
            print(f"  step {s['id']}: result={detail['results']}")
