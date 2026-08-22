# -*- coding: utf-8 -*-
import sys
import json
import importlib.util

CASES = [
    ("1h30m15s", 5415),
    ("45m", 2700),
    ("2h", 7200),
    ("90s", 90),
    (" 1h 5s ", 3605),
    ("", 0),
    ("0h0m0s", 0),
    ("10m5", "ERR"),
    ("abc", "ERR"),
    ("-1h", "ERR"),
    ("1m1h", "ERR"),
    ("1h1h", "ERR")
]

def main():
    path = sys.argv[1]
    spec = importlib.util.spec_from_file_location("user_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "parse_duration")
    
    out = []
    for inp, expected in CASES:
        try:
            result = fn(inp)
            if expected == "ERR":
                status = "fail"
                got = repr(result)
            else:
                if result == expected:
                    status = "ok"
                else:
                    status = "fail"
                    got = repr(result)
        except ValueError:
            if expected == "ERR":
                status = "ok"
            else:
                status = "fail"
                got = "ValueError"
        except Exception as e:
            status = "fail"
            got = type(e).__name__
        
        case_result = {"case": inp, "status": status}
        if status == "fail":
            case_result["got"] = got
        out.append(case_result)
    
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()
