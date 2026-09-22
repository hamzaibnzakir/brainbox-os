from enum import Enum

class Risk(str, Enum):
    READ = "read"
    PREPARE = "prepare"
    WRITE = "write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"

SAFE_SPECULATIVE_RISKS = {Risk.READ, Risk.PREPARE}

def speculative_allowed(risk: Risk, confirmed: bool) -> bool:
    return confirmed or risk in SAFE_SPECULATIVE_RISKS
