from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Protocol:
    name: str
    version: str
    visit_windows: dict[int, tuple[int, int]]
    dose_mg: float
    dose_frequency: str
    prohibited_medications: tuple[str, ...]
    required_assessments: tuple[str, ...]
    data_entry_deadline_days: int

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "visit_windows": {str(key): list(value) for key, value in self.visit_windows.items()},
            "dose_mg": self.dose_mg,
            "dose_frequency": self.dose_frequency,
            "prohibited_medications": list(self.prohibited_medications),
            "required_assessments": list(self.required_assessments),
            "data_entry_deadline_days": self.data_entry_deadline_days,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "Protocol":
        visit_windows = {
            int(key): (int(value[0]), int(value[1]))
            for key, value in dict(payload["visit_windows"]).items()
        }
        return cls(
            name=str(payload["name"]),
            version=str(payload["version"]),
            visit_windows=visit_windows,
            dose_mg=float(payload["dose_mg"]),
            dose_frequency=str(payload["dose_frequency"]),
            prohibited_medications=tuple(str(item).lower() for item in payload["prohibited_medications"]),
            required_assessments=tuple(str(item) for item in payload["required_assessments"]),
            data_entry_deadline_days=int(payload["data_entry_deadline_days"]),
        )


TRIAL_PROTOCOL = Protocol(
    name="TG-101 Imaging Response Study",
    version="1.0",
    visit_windows={
        1: (0, 7),
        2: (21, 35),
        3: (49, 63),
        4: (77, 91),
    },
    dose_mg=100,
    dose_frequency="once_daily",
    prohibited_medications=("warfarin", "phenytoin"),
    required_assessments=("safety_labs", "imaging_scan"),
    data_entry_deadline_days=5,
)