from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.models.triage_answer import TriageAnswer
from app.models.triage_assessment import TriageAssessment
from app.models.triage_question import QuestionResponseType, TriageQuestion
from app.models.triage_session import TriageSession, TriageSessionStatus


DEFAULT_QUESTION_BANK = [
    {
        "code": "TQ_CHEST_PAIN_SEVERITY",
        "question_text": "Are you experiencing severe, crushing, or radiating chest pain?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "CARDIO",
        "priority": 1,
    },
    {
        "code": "TQ_BREATHING_DIFFICULTY",
        "question_text": "Are you having difficulty catching your breath or breathing while resting?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "RESPIRATORY",
        "priority": 2,
    },
    {
        "code": "TQ_CONSCIOUSNESS_FAINTING",
        "question_text": "Did you lose consciousness, faint, or experience sudden blackouts?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "CARDIO",
        "priority": 3,
    },
    {
        "code": "TQ_BLEEDING_SEVERE",
        "question_text": "Is there severe, pulsing, or uncontrolled bleeding?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "GENERAL",
        "priority": 4,
    },
    {
        "code": "TQ_NEURO_SUDDEN_DEFICIT",
        "question_text": "Have you noticed sudden one-sided facial drooping, arm weakness, or speech difficulty?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "CARDIO",
        "priority": 5,
    },
    {
        "code": "TQ_ALLERGIC_ANAPHYLAXIS",
        "question_text": "Are your lips, tongue, or throat swelling, or are you breaking out in sudden hives with breathing trouble?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "GENERAL",
        "priority": 6,
    },
    {
        "code": "TQ_SYMPTOM_DURATION",
        "question_text": "How long have you been experiencing these primary symptoms?",
        "response_type": QuestionResponseType.DURATION,
        "category": "GENERAL",
        "priority": 10,
    },
    {
        "code": "TQ_DERM_RASH_ITCHING",
        "question_text": "Is the skin rash spreading rapidly, blistered, or intensely itchy?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "DERM",
        "priority": 15,
    },
    {
        "code": "TQ_ENT_SORE_THROAT_EAR",
        "question_text": "Do you have difficulty swallowing, severe ear pain, or persistent sinus congestion?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "ENT",
        "priority": 20,
    },
    {
        "code": "TQ_ORTHO_JOINT_INJURY",
        "question_text": "Is there joint swelling, severe bone pain, or inability to bear weight?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "ORTHO",
        "priority": 25,
    },
    {
        "code": "TQ_FEVER_HIGH",
        "question_text": "Do you have a measured high fever above 38.5°C (101.3°F)?",
        "response_type": QuestionResponseType.YES_NO,
        "category": "GENERAL",
        "priority": 30,
    },
]


class TriageRepository:
    def ensure_default_questions(self, db: Session) -> None:
        """Seeds standard controlled question bank if not yet present."""
        count = db.query(TriageQuestion).count()
        if count == 0:
            for item in DEFAULT_QUESTION_BANK:
                q = TriageQuestion(
                    code=item["code"],
                    question_text=item["question_text"],
                    response_type=item["response_type"],
                    category=item["category"],
                    priority=item["priority"],
                    is_active=True,
                )
                db.add(q)
            db.commit()

    def get_session(self, db: Session, session_id: str) -> Optional[TriageSession]:
        return (
            db.query(TriageSession)
            .options(
                joinedload(TriageSession.answers).joinedload(TriageAnswer.question),
                joinedload(TriageSession.assessment).joinedload(
                    TriageAssessment.recommended_specialty
                ),
            )
            .filter(TriageSession.id == session_id)
            .first()
        )

    def get_question_by_id(
        self, db: Session, question_id: str
    ) -> Optional[TriageQuestion]:
        return db.query(TriageQuestion).filter(TriageQuestion.id == question_id).first()

    def get_question_by_code(
        self, db: Session, code: str
    ) -> Optional[TriageQuestion]:
        return db.query(TriageQuestion).filter(TriageQuestion.code == code).first()

    def get_next_question(
        self, db: Session, session_id: str
    ) -> Optional[TriageQuestion]:
        self.ensure_default_questions(db)

        # Find questions already answered in this session
        answered_q_ids = [
            row[0]
            for row in db.query(TriageAnswer.question_id)
            .filter(TriageAnswer.triage_session_id == session_id)
            .all()
        ]

        query = db.query(TriageQuestion).filter(TriageQuestion.is_active.is_(True))
        if answered_q_ids:
            query = query.filter(~TriageQuestion.id.in_(answered_q_ids))

        return query.order_by(TriageQuestion.priority.asc()).first()

    def add_answer(
        self, db: Session, session_id: str, question_id: str, answer_value: str
    ) -> TriageAnswer:
        answer = TriageAnswer(
            triage_session_id=session_id,
            question_id=question_id,
            answer_value=answer_value.strip(),
        )
        db.add(answer)
        db.commit()
        db.refresh(answer)
        return answer

    def get_session_answers(
        self, db: Session, session_id: str
    ) -> List[TriageAnswer]:
        return (
            db.query(TriageAnswer)
            .options(joinedload(TriageAnswer.question))
            .filter(TriageAnswer.triage_session_id == session_id)
            .all()
        )


triage_repo = TriageRepository()
