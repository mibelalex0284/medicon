import json

with open("ml/evaluation/audit_results.json") as f:
    d = json.load(f)

cond_stats = d["cond_stats"]

rows = []
for cond, s in cond_stats.items():
    n = s["total"]
    if n == 0:
        continue
    t1 = s["top1"] / n
    t3 = s["top3"] / n
    t5 = s["top5"] / n
    avg_q = s["turns"] / n
    avg_r = s["ranks"] / max(1, s["ranked_cnt"])
    esc_rec = (s["escalated"] / s["high_sev"]) if s["high_sev"] > 0 else 1.0
    rows.append({
        "condition": cond,
        "n": n,
        "top1": t1,
        "top3": t3,
        "top5": t5,
        "avg_q": avg_q,
        "avg_r": avg_r,
        "high_sev": s["high_sev"],
        "esc_rec": esc_rec,
    })

# Sort ascending by Top-1
rows.sort(key=lambda r: (r["top1"], -r["n"]))

print(f"{'Condition':<32} | {'N':<3} | {'Top-1':<7} | {'Top-3':<7} | {'Top-5':<7} | {'Avg Q':<5} | {'Avg Rank':<8} | {'Esc Recall':<10}")
print("-" * 95)
for r in rows:
    print(f"{r['condition']:<32} | {r['n']:<3} | {r['top1']:<7.1%} | {r['top3']:<7.1%} | {r['top5']:<7.1%} | {r['avg_q']:<5.2f} | {r['avg_r']:<8.2f} | {r['esc_rec']:<10.1%}")

# Identify 5 weakest (lowest Top-1) and 5 strongest (highest Top-1)
print("\n--- 5 Weakest Conditions ---")
for r in rows[:5]:
    print(f"  {r['condition']} (N={r['n']}, Top-1={r['top1']:.1%}, Top-3={r['top3']:.1%}, Top-5={r['top5']:.1%}, Avg Rank={r['avg_r']:.2f})")

rows_desc = sorted(rows, key=lambda r: (-r["top1"], -r["n"]))
print("\n--- 5 Strongest Conditions ---")
for r in rows_desc[:5]:
    print(f"  {r['condition']} (N={r['n']}, Top-1={r['top1']:.1%}, Top-3={r['top3']:.1%}, Top-5={r['top5']:.1%}, Avg Rank={r['avg_r']:.2f})")
