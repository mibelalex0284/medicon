import json

# First re-run audit for N=100 to get exact breakdown for N=100
from ml.evaluation.audit_stage4b2 import run_comprehensive_audit

res_100 = run_comprehensive_audit(100)

print("=== N=100 BREAKDOWN ===")
print("Total Patients:", res_100["n"])
print("High-severity DDXPlus cases (sev >= 3):", res_100["high_sev_total"])
print("High-severity cases Escalated:", res_100["high_sev_escalated"])
print("High-severity cases Non-escalated (Failures):", len(res_100["high_sev_failures"]))

# Check how many of the 79 cases actually contained a CareRoute-X red flag
cr_rf_in_high_sev = 0
cr_rf_in_high_sev_escalated = 0
non_rf_in_high_sev = 0
non_rf_in_high_sev_escalated = 0

for f in res_100["high_sev_failures"]:
    print("Failure:", f["patient_id"], f["pathology"], "DDXPlus sev:", f["severity"], "CR Red Flags:", f["cr_red_flags_present"], "Top Cond:", f["final_top_cond"], "Type:", f["failure_type"])

print("\n--- Failure Type Classification for N=100 ---")
for idx, f in enumerate(res_100["high_sev_failures"], 1):
    has_rf = len(f["cr_red_flags_present"]) > 0
    if not has_rf:
        print(f"Case {idx}: {f['pathology']} (DDXPlus sev {f['severity']}) -> G. BENCHMARK MISMATCH (No CareRoute-X red flags exist in patient)")
    else:
        print(f"Case {idx}: {f['pathology']} (DDXPlus sev {f['severity']}) -> {f['failure_type']}")
