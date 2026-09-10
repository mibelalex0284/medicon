import os
import joblib
import pandas as pd
import pytest
from ml.inference import SymptomClassifier, symptom_classifier


# --- REGRESSION TESTS (EXISTING) ---


def test_classifier_artifact_is_ready():
    assert symptom_classifier.is_ready is True


def test_dermatology_symptom_prediction():
    text = "I have a red itchy skin rash with flaking, silver scales, and peeling on my elbows"
    result = symptom_classifier.predict(text, top_k=3)

    assert result["predicted_disease"] in ["Psoriasis", "Fungal infection", "Acne"]
    assert result["recommended_specialty"] == "DERM"
    assert result["confidence"] > 0.30
    assert len(result["top_predictions"]) == 3
    assert result["top_predictions"][0]["probability"] >= result["top_predictions"][1]["probability"]


def test_respiratory_symptom_prediction():
    text = "I have a persistent cough and have been having trouble breathing, coughing up a lot of thick mucous"
    result = symptom_classifier.predict(text, top_k=3)

    assert result["predicted_disease"] in ["Bronchial Asthma", "Pneumonia", "Common Cold"]
    assert result["recommended_specialty"] in ["RESPIRATORY", "GENERAL"]
    assert result["confidence"] > 0.15


def test_orthopedics_symptom_prediction():
    text = "My muscles feel weak, neck is really stiff, my joints are swelling up, and it is painful to walk"
    result = symptom_classifier.predict(text, top_k=3)

    assert result["predicted_disease"] in ["Arthritis", "Cervical Spondylosis", "Cervical spondylosis"]
    assert result["recommended_specialty"] == "ORTHO"
    assert result["confidence"] > 0.20


def test_empty_input_handling():
    result = symptom_classifier.predict("", top_k=3)
    assert result["predicted_disease"] == "Unknown"
    assert result["confidence"] == 0.0
    assert result["is_uncertain"] is True


# --- DATASET AUDIT TESTS ---


def test_dataset_structure_and_class_count():
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "ml", "data", "Symptom2Disease.csv"
    )
    assert os.path.exists(data_path), f"Dataset missing at {data_path}"
    df = pd.read_csv(data_path)
    assert len(df) == 1200
    assert df["label"].nunique() == 24


def test_dataset_class_balance():
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "ml", "data", "Symptom2Disease.csv"
    )
    df = pd.read_csv(data_path)
    counts = df["label"].value_counts()
    for disease, count in counts.items():
        assert count == 50, f"Class '{disease}' has {count} samples, expected exactly 50"


def test_dataset_no_missing_values():
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "ml", "data", "Symptom2Disease.csv"
    )
    df = pd.read_csv(data_path)
    assert df["label"].isnull().sum() == 0
    assert df["text"].isnull().sum() == 0
    assert (df["text"].astype(str).str.strip() == "").sum() == 0


def test_dataset_label_validity():
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "ml", "data", "Symptom2Disease.csv"
    )
    df = pd.read_csv(data_path)
    labels = df["label"].unique()
    for l in labels:
        assert isinstance(l, str)
        assert len(l.strip()) > 0


# --- MODEL & ARTIFACT TESTS ---


def test_artifact_metadata_and_version():
    artifact_path = symptom_classifier.DEFAULT_ARTIFACT_PATH
    bundle = joblib.load(artifact_path)

    assert "metadata" in bundle
    meta = bundle["metadata"]
    assert meta["version"] == "2.0.0"
    assert "trained_at" in meta
    assert meta["test_accuracy"] >= 0.90
    assert meta["selected_threshold"] == 0.50
    assert "input_quality_guard" in meta


def test_artifact_all_24_classes_recognized():
    artifact_path = symptom_classifier.DEFAULT_ARTIFACT_PATH
    bundle = joblib.load(artifact_path)

    classes = bundle.get("classes", [])
    assert len(classes) == 24
    assert len(set(classes)) == 24


def test_prediction_probabilities_sum_to_approximately_one():
    text = "Severe throbbing headache on one side of my head with nausea and sensitivity to bright light"
    result = symptom_classifier.predict(text, top_k=24)

    probs = [p["probability"] for p in result["top_predictions"]]
    assert len(probs) == 24
    assert sum(probs) == pytest.approx(1.0, abs=0.01)


def test_calibrated_confidence_within_zero_one_bounds():
    text = "High fever, body aches, chills, extreme fatigue and headache"
    result = symptom_classifier.predict(text, top_k=3)

    assert 0.0 <= result["confidence"] <= 1.0
    for p in result["top_predictions"]:
        assert 0.0 <= p["probability"] <= 1.0


# --- CALIBRATION & ABSTENTION TESTS ---


def test_calibration_metadata_exists():
    artifact_path = symptom_classifier.DEFAULT_ARTIFACT_PATH
    bundle = joblib.load(artifact_path)
    meta = bundle.get("metadata", {})

    assert "test_brier_score" in meta
    assert "test_ece" in meta
    assert meta["test_brier_score"] < 0.20
    assert meta["test_ece"] < 0.30


def test_low_confidence_abstention():
    # Ambiguous or weak symptom prompt
    text = "hello"
    result = symptom_classifier.predict(text)

    assert result["is_uncertain"] is True
    assert result["confidence"] < symptom_classifier.default_threshold
    assert result["abstention_reason"] is not None


def test_custom_abstention_threshold_application():
    text = "I have a red itchy skin rash with flaking, silver scales, and peeling on my elbows"
    # With very high threshold, prediction must abstain
    strict_result = symptom_classifier.predict(text, confidence_threshold=0.99)
    assert strict_result["is_uncertain"] is True

    # With very low threshold, prediction must not abstain
    lenient_result = symptom_classifier.predict(text, confidence_threshold=0.10)
    assert lenient_result["is_uncertain"] is False


def test_confident_prediction_does_not_unnecessarily_abstain():
    text = "Joint pain and stiffness that is worse in the morning, swollen fingers and difficult moving knees"
    result = symptom_classifier.predict(text)

    assert result["is_uncertain"] is False
    assert result["confidence"] >= symptom_classifier.default_threshold
    assert result["abstention_reason"] is None


# --- INPUT QUALITY GUARD TESTS ---


def test_whitespace_input_handling():
    result = symptom_classifier.predict("   \t  \n  ")
    assert result["predicted_disease"] == "Unknown"
    assert result["confidence"] == 0.0
    assert result["is_uncertain"] is True
    assert result["input_quality_status"] == "INSUFFICIENT_INFORMATION"


def test_extremely_short_input_handling():
    for short_text in ["a", "hi", "bad", "xyz"]:
        result = symptom_classifier.predict(short_text)
        assert result["predicted_disease"] == "Unknown"
        assert result["confidence"] == 0.0
        assert result["is_uncertain"] is True
        assert result["input_quality_status"] == "INSUFFICIENT_INFORMATION"


def test_non_alphabetic_input_handling():
    result = symptom_classifier.predict("12345 67890 !@#$%")
    assert result["predicted_disease"] == "Unknown"
    assert result["confidence"] == 0.0
    assert result["is_uncertain"] is True
    assert result["input_quality_status"] == "INSUFFICIENT_INFORMATION"


def test_irrelevant_nonsense_input_handling():
    nonsense_inputs = [
        "asdfghjkl",
        "My computer is slow",
    ]
    for text in nonsense_inputs:
        result = symptom_classifier.predict(text)
        assert result["predicted_disease"] == "Unknown"
        assert result["confidence"] == 0.0
        assert result["is_uncertain"] is True
        assert result["input_quality_status"] == "INSUFFICIENT_INFORMATION"


# --- SPECIALTY MAPPING TESTS ---


VALID_SPECIALTIES = {"DERM", "CARDIO", "RESPIRATORY", "ORTHO", "NEURO", "GENERAL"}


def test_all_24_disease_classes_map_to_valid_specialties():
    artifact_path = symptom_classifier.DEFAULT_ARTIFACT_PATH
    bundle = joblib.load(artifact_path)
    classes = bundle.get("classes", [])
    mapping = bundle.get("disease_to_specialty", {})

    assert len(classes) == 24
    for cls in classes:
        spec = (
            mapping.get(cls)
            or mapping.get(cls.lower())
            or mapping.get(cls.title())
        )
        assert spec is not None, f"Class '{cls}' has no mapped specialty"
        assert spec in VALID_SPECIALTIES, f"Specialty '{spec}' for class '{cls}' is invalid"


def test_previously_unmapped_casing_classes_are_resolved():
    artifact_path = symptom_classifier.DEFAULT_ARTIFACT_PATH
    bundle = joblib.load(artifact_path)
    mapping = bundle.get("disease_to_specialty", {})

    # These 6 classes had case mismatch in Stage 5:
    assert mapping.get("Cervical spondylosis") == "ORTHO"
    assert mapping.get("allergy") == "GENERAL"
    assert mapping.get("diabetes") == "GENERAL"
    assert mapping.get("gastroesophageal reflux disease") == "GENERAL"
    assert mapping.get("peptic ulcer disease") == "GENERAL"
    assert mapping.get("urinary tract infection") == "GENERAL"


def test_specialty_mapping_is_deterministic():
    for _ in range(5):
        result = symptom_classifier.predict("I have an itchy red skin rash with silver scales on my knees")
        assert result["recommended_specialty"] == "DERM"
