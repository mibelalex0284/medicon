import json

with open("ml/evaluation/audit_results.json") as f:
    d = json.load(f)

print("=== N=1000 SUMMARY ===")
print("N:", d["n"])
print("Top-1 Recall:", f"{d['top1_recall']:.2%}")
print("Top-3 Recall:", f"{d['top3_recall']:.2%}")
print("Top-5 Recall:", f"{d['top5_recall']:.2%}")
print("Avg Target Rank:", f"{d['avg_rank']:.2f}")
print("Median Target Rank:", d["median_rank"])
print("Avg Questions:", f"{d['avg_turns']:.2f}")
print("Median Questions:", d["median_turns"])
print("Avg Entropy Reduction:", f"{d['avg_entropy_reduction']:.4f}")
print("Dependency Violations:", d["dependency_violations"])
print("Distinct Questions:", d["distinct_questions_count"])
print("Total Questions Asked:", d["total_questions_asked"])
print("Low IG Questions (< 0.01):", d["low_ig_questions"])
print("Stop Reasons:", d["stop_reasons"])
print("Turns Distribution:", d["turns_distribution"])
print("High Severity Cases (DDXPlus >= 3):", d["high_sev_total"])
print("High Severity Escalated:", d["high_sev_escalated"])
print("High Severity Escalation Rate:", f"{d['high_sev_escalation_rate']:.2%}")
print("CareRoute Red Flag Cases in GT:", d["careroute_red_flag_cases"])
print("CareRoute Red Flag Detected/Escalated:", d["careroute_red_flag_detected"])
print("High Severity Failures Count:", len(d["high_sev_failures"]))

# Breakdown of failure types
from collections import Counter
types_cnt = Counter(f["failure_type"] for f in d["high_sev_failures"])
print("\nFailure Type Breakdown:")
for k, v in types_cnt.items():
    print(f"  {k}: {v} ({v/len(d['high_sev_failures']):.1%})")

# Breakdown of conditions in failures
cond_fail_cnt = Counter(f["pathology"] for f in d["high_sev_failures"])
print("\nConditions in Failures:")
for k, v in cond_fail_cnt.most_common(10):
    print(f"  {k}: {v}")
