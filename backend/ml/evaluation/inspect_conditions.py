import json
import zipfile
from app.services.triage.evidence_provider import ddxplus_provider

with zipfile.ZipFile("D:/22687585.zip", "r") as z:
    conds = json.loads(z.read("release_conditions.json").decode("utf-8"))

check_list = [
    "Panic attack",
    "Pericarditis",
    "Myocarditis",
    "Unstable angina",
    "Guillain-Barré syndrome",
    "HIV (initial infection)",
    "Boerhaave",
    "Anaphylaxis",
    "Spontaneous pneumothorax",
    "Acute pulmonary edema",
]

for name in check_list:
    raw_sev = conds.get(name, {}).get("severity")
    provider_sev = ddxplus_provider.get_condition_severity(name)
    print(f"{name:30s} | Raw DDXPlus severity: {str(raw_sev):5s} | Provider severity: {provider_sev}")
