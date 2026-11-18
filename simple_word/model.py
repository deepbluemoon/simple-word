class Simplifier:
    """Deterministic placeholder; replace with the trained model later."""

    def __init__(self, artifact_dir: str):
        self.artifact_dir = artifact_dir

    def simplify(self, sentences: list[str]) -> list[str]:
        return list(sentences)
