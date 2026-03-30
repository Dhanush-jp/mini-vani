from fastapi import FastAPI
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestRegressor
import numpy as np

app = FastAPI(title="Risk ML Service", version="1.0.0")


class RiskRequest(BaseModel):
    attendance_pct: float = Field(ge=0, le=100)
    sgpa: float = Field(ge=0, le=10)
    cgpa: float = Field(ge=0, le=10)
    backlogs: int = Field(ge=0, le=40)


def build_training_data() -> tuple[np.ndarray, np.ndarray]:
    rows = []
    labels = []
    for attendance in range(35, 101, 5):
        for sgpa in np.arange(3.0, 10.1, 0.5):
            for backlogs in range(0, 9):
                cgpa = max(2.0, sgpa - np.random.uniform(0.0, 1.5))
                risk = 10 - (attendance / 20) - (sgpa / 2.5) - (cgpa / 3) + (backlogs * 0.65)
                risk = float(np.clip(risk, 1, 10))
                rows.append([attendance, sgpa, cgpa, backlogs])
                labels.append(risk)
    return np.array(rows), np.array(labels)


X_train, y_train = build_training_data()
model = RandomForestRegressor(n_estimators=200, random_state=42)
model.fit(X_train, y_train)


def generate_suggestions(risk_score: float, payload: RiskRequest) -> str:
    suggestions = []
    if payload.attendance_pct < 75:
        suggestions.append("Improve attendance to above 80% with weekly attendance tracking.")
    if payload.sgpa < 6 or payload.cgpa < 6:
        suggestions.append("Schedule subject-wise remediation and mentorship for low GPA recovery.")
    if payload.backlogs > 0:
        suggestions.append("Prioritize backlog clearance with targeted revision plan.")
    if risk_score >= 8:
        suggestions.append("Immediate academic intervention and parent/counselor review recommended.")
    if not suggestions:
        suggestions.append("Maintain current performance and continue regular monitoring.")
    return " ".join(suggestions)


@app.post("/predict-risk")
def predict_risk(payload: RiskRequest):
    features = np.array([[payload.attendance_pct, payload.sgpa, payload.cgpa, payload.backlogs]])
    score = float(np.clip(model.predict(features)[0], 1, 10))
    return {"risk_score": round(score, 2), "suggestions": generate_suggestions(score, payload)}


@app.get("/health")
def health():
    return {"status": "ok"}
