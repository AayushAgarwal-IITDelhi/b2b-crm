import os
import glob
import yaml
from typing import Dict, List, Optional
from exhibition_lead_agent.models.schema import SourceRegistry

class RegistryLoader:
    def __init__(self, sources_dir: str = "sources"):
        self.sources_dir = sources_dir
        self.registry: Dict[str, SourceRegistry] = {}
        self.load_all()

    def load_all(self):
        pattern = os.path.join(self.sources_dir, "*.yaml")
        for filepath in glob.glob(pattern):
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "key" in data:
                    source = SourceRegistry(**data)
                    self.registry[source.key] = source

    def get(self, key: str) -> Optional[SourceRegistry]:
        return self.registry.get(key)

    def list_keys(self) -> List[str]:
        return list(self.registry.keys())
