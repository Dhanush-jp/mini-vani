def safe_percentage(present, total):
    try:
        p = float(present or 0)
        t = float(total or 0)
        return round((p * 100.0 / t), 2) if t > 0 else 0
    except Exception:
        return 0

def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default
