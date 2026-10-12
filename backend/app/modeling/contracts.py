from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TrainingRequest:
    dataset_id: str
    target_column: str
    task: str
    split_strategy: str


class ModelTrainer(Protocol):
    """Future adapter: returns an artifact ID registered with its dataset and split."""

    def train(self, request: TrainingRequest) -> str: ...
