# -*- coding: utf-8 -*-
import sys, os, re, json, time, random, argparse, subprocess, tempfile, traceback, statistics, requests
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# VRAM-guard — модуль стенда, проверяющий, поместится ли модель в видеопамять.
# Частью методики не является: без него бенчмарк работает так же, просто не
# предупреждает о нехватке видеопамяти. Путь задаётся переменной VRAM_GUARD_PATH.
try:
    _guard_path = os.environ.get("VRAM_GUARD_PATH")
    if _guard_path:
        sys.path.insert(0, _guard_path)
    from vram_guard_reference import check_can_load, OLLAMA_BASE_URL  # noqa: F811
except Exception:
    def check_can_load(model, estimate_override_MB=None):
        """Заглушка: считаем, что модель загрузить можно."""
        return type("Verdict", (), {"ok": True, "reason": "guard-not-installed"})()

def _load_fixture(name):
    """Читает файл фикстуры рядом со скриптом (fixtures/<name>), без экранирования."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", name), encoding="utf-8") as fh:
        return fh.read().rstrip("\n")


rng = random.Random(20260822)


class HarnessError(Exception):
    """Поломка ОСНАСТКИ (нет раннера, крах, нечитаемый вывод) — не провал модели.

    Отделено намеренно: раньше отсутствие codegen_runner.py давало score=0.0,
    неотличимый в таблице от честного провала модели (см. audit round 2, P1).
    """

def unload(model):
    try:
        requests.post(f"{OLLAMA_BASE_URL}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    except:
        pass
    time.sleep(3)

def gen(model, prompt, fmt, think, est_MB, soft_guard):
    v = check_can_load(model, estimate_override_MB=est_MB)
    if not v.ok and not soft_guard:
        raise RuntimeError("VRAM guard refused: " + str(getattr(v,"reason",v)))
    elif not v.ok and soft_guard:
        print(f"WARNING: VRAM guard refused for {model}", file=sys.stderr)
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 32768}
    }
    if fmt:
        payload["format"] = fmt
    if think is not None:
        payload["think"] = think
    
    r = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=1200)
    r.raise_for_status()
    return r.json()

def parse_json(text):
    text = text.strip()
    # Remove markdown-style code block markers
    if text.startswith("```"):
        text = text[3:]
        if text.startswith("json"):
            text = text[4:]
        if text.endswith("```"):
            text = text[:-3]
    
    try:
        return json.loads(text)
    except:
        # Try to find first { or [ and last } or ]
        start_idx = -1
        end_idx = -1
        
        for i, c in enumerate(text):
            if c == '{' or c == '[':
                start_idx = i
                break
                
        for i in range(len(text) - 1, -1, -1):
            if text[i] == '}' or text[i] == ']':
                end_idx = i
                break
        
        if start_idx != -1 and end_idx != -1:
            frag = text[start_idx:end_idx+1]
            try:
                return json.loads(frag)
            except:
                pass
            # последовательность объектов без внешних скобок: {..},{..},{..}
            # (так отвечает nemotron на пакетных задачах — содержательно это массив)
            if frag.startswith("{") and "}," in frag:
                try:
                    return json.loads("[" + frag + "]")
                except:
                    pass

    return None

# Model configurations
MODELS = [
    ("coder", "qwen3-coder:30b", None, None, False),
    ("q36", "qwen3.6:27b", False, 17800, False),
    ("devstral", "devstral-small-2:24b", False, 17300, False),
    ("glm47flash", "glm-4.7-flash:latest", False, 20200, True),
    ("nemotron", "nemotron-cascade-2:30b", False, 21500, True)
]

# Task definitions
TASKS = []

def task_log_extract():
    # Generate log data
    start_time = time.mktime(time.strptime("2026-08-21 10:00:00", "%Y-%m-%d %H:%M:%S"))
    lines = []
    
    level_weights = [70, 20, 10]  # INFO, WARN, ERROR
    level_choices = ["INFO", "WARN", "ERROR"]
    
    subsystems = ["wifi", "flash", "ble", "http", "mqtt"]
    devices = [f"DEV-{i:03d}" for i in range(1, 13)]
    
    error_messages = {
        "ERROR": ["disk full", "write failed", "timeout", "crc mismatch"],
        "WARN": ["retrying", "slow response", "buffer 80%"],
        "INFO": ["heartbeat ok", "segment closed", "connected"]
    }
    
    errors_by_subsys = {sub: 0 for sub in subsystems}
    disk_full_devices = set()
    first_error_ts = None
    last_error_ts = None
    
    for i in range(400):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        level = rng.choices(level_choices, weights=level_weights)[0]
        subsystem = rng.choice(subsystems)
        device = rng.choice(devices)
        
        if level == "ERROR":
            errors_by_subsys[subsystem] += 1
            msg = rng.choice(error_messages[level])
            lines.append(f"{ts} [{level}] {subsystem} {device}: {msg}")
            
            if msg == "disk full":
                disk_full_devices.add(device)
                
            if first_error_ts is None:
                first_error_ts = ts
            last_error_ts = ts
        elif level == "WARN":
            lines.append(f"{ts} [{level}] {subsystem} {device}: {rng.choice(error_messages[level])}")
        else:
            lines.append(f"{ts} [{level}] {subsystem} {device}: {rng.choice(error_messages[level])}")
            
        start_time += rng.randint(1, 40)
    
    # Create prompt
    prompt = "Ниже лог из 400 строк. Верни ТОЛЬКО JSON {\"errors_by_subsys\": {subsys: int}, \"disk_full_devices\": [str], \"first_error_ts\": str, \"last_error_ts\": str}. errors_by_subsys — число строк уровня ERROR по каждой подсистеме (wifi, flash, ble, http, mqtt). disk_full_devices — уникальные устройства с ошибкой 'disk full', отсортированные. first/last_error_ts — метки времени первой и последней строки ERROR в формате как в логе.\n\n" + "\n".join(lines)
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                return (0.0, "check error: invalid JSON structure")
            
            # Check errors_by_subsys
            errors_match = True
            for sub in subsystems:
                if str(result.get("errors_by_subsys", {}).get(sub, 0)) != str(errors_by_subsys[sub]):
                    errors_match = False
                    break
            
            # Check disk_full_devices
            disk_full_match = set(result.get("disk_full_devices", [])) == disk_full_devices
            
            # Check timestamps
            first_match = result.get("first_error_ts") == first_error_ts
            last_match = result.get("last_error_ts") == last_error_ts
            
            score = 0.0
            note_parts = []
            
            if errors_match:
                score += 0.25
                note_parts.append("errors_by_subsys match")
            else:
                note_parts.append("errors_by_subsys mismatch")
                
            if disk_full_match:
                score += 0.25
                note_parts.append("disk_full_devices match")
            else:
                note_parts.append("disk_full_devices mismatch")
                
            if first_match:
                score += 0.25
                note_parts.append("first_error_ts match")
            else:
                note_parts.append("first_error_ts mismatch")
                
            if last_match:
                score += 0.25
                note_parts.append("last_error_ts match")
            else:
                note_parts.append("last_error_ts mismatch")
                
            return (score, ", ".join(note_parts))
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "log_extract",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_bulk200():
    # Generate data
    info_phrases = ["INFO: heartbeat ok", "INFO: segment closed", "INFO: recovered after error", "INFO: wifi connected"]
    warn_phrases = ["WARN: buffer 80%", "WARN: retry 2/3", "WARN: slow flash write"]
    error_phrases = ["ERROR: disk full", "ERROR: crc mismatch", "ERROR: write failed"]
    
    lines = []
    expected_classes = []
    for i in range(200):
        r = rng.random()
        if r < 0.6:
            text = rng.choice(info_phrases)
            expected_class = "ok"
        elif r < 0.85:
            text = rng.choice(warn_phrases)
            expected_class = "warning"
        else:
            text = rng.choice(error_phrases)
            expected_class = "error"

        lines.append(f"{i:03d} {text}")
        expected_classes.append(expected_class)
    
    # Create prompt
    prompt = "Ниже 200 строк лога с индексами. Классифицируй КАЖДУЮ как ok/warning/error по уровню (INFO→ok, WARN→warning, ERROR→error). Верни ТОЛЬКО JSON-массив ровно из 200 объектов {\"idx\": int, \"class\": str} в порядке строк, без обёрток.\n\n" + "\n".join(lines)
    
    def check(text):
        try:
            result = parse_json(text)
            
            # Формы ответа, содержательно эквивалентные списку. Режим format='json'
            # у Ollama подталкивает модели к объекту вместо массива, поэтому
            # наказывать за форму — значит мерить оснастку, а не модель.
            note_prefix = ""
            if isinstance(result, dict):
                lists = [v for v in result.values() if isinstance(v, list)]
                if len(result) == 1 and lists:
                    result = lists[0]              # {"data": [...]} и любые синонимы ключа
                    note_prefix = "wrapped, "
                else:
                    # {"000": "error", "001": "ok", ...} — словарь индекс→класс
                    pairs = [(k, v) for k, v in result.items() if isinstance(v, str)]
                    if len(pairs) >= 2:
                        result = [{"idx": k, "class": v} for k, v in pairs]
                        note_prefix = "dict-form, "
                
            if not isinstance(result, list):
                return (0.0, f"{note_prefix}check error: invalid JSON structure")
            
            correct = 0
            seen_idx = set()  # дубликаты idx давали 1.0 за 200 копий одной записи
            for item in result:
                if not isinstance(item, dict) or "idx" not in item or "class" not in item:
                    continue
                    
                try:
                    idx = int(item["idx"])
                    # регистр не значим: "OK" — содержательно тот же ответ, что "ok"
                    got_cls = str(item["class"]).strip().lower()
                    if idx in seen_idx:
                        continue  # повторный ответ по той же строке не засчитывается
                    seen_idx.add(idx)
                    if 0 <= idx < 200 and got_cls == expected_classes[idx]:
                        correct += 1
                except:
                    continue
                    
            score = correct / 200.0
            return (score, f"{note_prefix}{correct}/200, len={len(result)}")
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "bulk200",
        "prompt": prompt,
        # fmt=None намеренно: grammar-constraint режима format='json' закрывает
        # JSON после первого объекта, и пакетная задача обрывается на 1 строке из
        # 200 у ВСЕХ моделей. Проверено на qwen3-coder: format='json' -> 13 токенов
        # и score 0.00; без format -> 2893 токена и 200/200. Режим измерял бы
        # оснастку, а не модель.
        "fmt": None,
        "check": check
    }

def task_needle():
    # Generate text
    paragraphs = [
        "Прошивка устройства WT-P011 была успешно установлена. Система прошла полный цикл тестирования в течение 24 часов без обнаружения ошибок. Все модули функционировали корректно.",
        "В ходе испытаний были зафиксированы данные по производительности. Показатели стабильны, отклонения не превышают допустимых значений. Среднее время отклика составляет 150 мс.",
        "Проверка безопасности показала отсутствие уязвимостей в текущей версии прошивки. Все протоколы шифрования работают корректно. Рекомендуется обновление до версии v1.2.17.",
        "Тестирование на нагрузку проводилось с использованием 1500 тестовых сценариев. Все сценарии завершены успешно. Система демонстрирует высокую надежность при максимальной нагрузке.",
        "В ходе анализа журналов были выявлены незначительные отклонения в работе модуля BLE. Причиной является временная задержка в обработке пакетов, не влияющая на общую производительность.",
        "Проверка ресурсов показала оптимальное использование памяти и процессора. Загрузка CPU составляет 35% при средней нагрузке. Оперативная память используется эффективно.",
        "Система поддерживает все необходимые функции для работы в промышленной среде. Все компоненты соответствуют требованиям стандартов. Рекомендуется продолжение тестирования на длительном сроке.",
        "После завершения тестирования были собраны данные по стабильности работы. Система не имела сбоев в течение 72 часов непрерывной работы. Все показатели находятся в пределах нормы.",
        "Анализ производительности показал, что система способна обрабатывать до 1000 запросов в секунду при минимальной задержке. Показатели соответствуют техническим требованиям.",
        "Проверка совместимости с другими устройствами прошла успешно. Все протоколы взаимодействия работают корректно. Система поддерживает стандартные интерфейсы.",
        "Тестирование на устойчивость к сбоям показало высокую надежность системы. При возникновении ошибок система автоматически восстанавливается без потери данных.",
        "В ходе тестирования были проанализированы данные по энергопотреблению. Среднее потребление составляет 120 мА при активной работе. Показатели соответствуют проектным требованиям."
    ]
    
    # Create text by repeating and shuffling paragraphs
    text = ""
    for i in range(5):
        shuffled = paragraphs.copy()
        rng.shuffle(shuffled)
        text += "\n".join(shuffled) + "\n\n"
    
    # Insert needle at ~60% position
    insert_pos = int(len(text) * 0.6)
    needle = "Серийный номер поверочного эталона — 7F3K-0921-X, поверка действительна до 14.11.2027."
    
    # Find a good place to insert
    while text[insert_pos] != '\n' and insert_pos < len(text) - 1:
        insert_pos += 1
    
    text = text[:insert_pos] + needle + text[insert_pos:]
    
    # Create prompt
    prompt = "В тексте ниже один раз упомянут серийный номер поверочного эталона и дата окончания поверки. Верни ТОЛЬКО JSON {\"serial\": str, \"valid_until\": str}.\n\n" + text
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                return (0.0, "check error: invalid JSON structure")
            
            serial = result.get("serial", "").strip()
            valid_until = result.get("valid_until", "").strip()
            
            expected_serial = "7F3K-0921-X"
            expected_valid_until = "14.11.2027"
            
            score = 0.0
            note_parts = []
            
            # регистр серийника не значим: инструкция его сохранять не требует
            if serial.upper() == expected_serial:
                score += 0.5
                note_parts.append("serial match")
            else:
                note_parts.append(f"serial mismatch: got '{serial}', expected '{expected_serial}'")
                
            if valid_until == expected_valid_until:
                score += 0.5
                note_parts.append("valid_until match")
            else:
                note_parts.append(f"valid_until mismatch: got '{valid_until}', expected '{expected_valid_until}'")
                
            return (score, ", ".join(note_parts))
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "needle",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_code_review_hard():
    # Buggy code
    BUGGY = _load_fixture("buggy_module.py.txt")
    
    # Seeded defects
    SEEDED = [
        ("mutable_default", "defaults={})"),
        ("file_leak", "f = open(path)"),
        ("eq_none", "== None"),
        ("percentile_oob", "int(len(values) * p / 100)"),
        ("ts_format", "%Y-%m-%d %H:%M\")"),
        ("bare_except", "except:"),
        ("last_n_zero", "values[-n:]")
    ]
    
    # Find line numbers for defects
    lines = BUGGY.split('\n')
    defect_lines = {}
    for id, substr in SEEDED:
        found = False
        for i, line in enumerate(lines):
            if substr in line:
                defect_lines[id] = i + 1
                found = True
                break
        if not found:
            # If not found, try to find it in the whole text
            pos = BUGGY.find(substr)
            if pos != -1:
                # Count lines before position
                line_count = BUGGY[:pos].count('\n') + 1
                defect_lines[id] = line_count
    
    # Create prompt with line numbers
    numbered_code = "\n".join([f"{i+1:2d}| {line}" for i, line in enumerate(lines)])
    prompt = "Найди ВСЕ дефекты в модуле (логика, ресурсы, граничные случаи, стиль, ведущий к багам). Нумерация строк — с 1. Точность важна: перечисление заведомо лишних строк снижает оценку, поэтому указывай только те, где дефект действительно есть. Верни ТОЛЬКО JSON {\"bugs\": [{\"line\": int, \"desc\": str}]}.\n\n" + numbered_code
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict) or "bugs" not in result:
                return (0.0, "check error: invalid JSON structure")
            
            bugs = result["bugs"]
            hit = 0
            missed = []
            
            for id, _ in SEEDED:
                found = False
                expected_line = defect_lines[id]
                
                for bug in bugs:
                    if isinstance(bug, dict) and "line" in bug:
                        line = bug["line"]
                        if abs(line - expected_line) <= 1:
                            hit += 1
                            found = True
                            break
                
                if not found:
                    missed.append(id)
            
            # штраф за «дробовик»: перечислить все строки подряд не должно давать 1.0
            precision = min(1.0, 14.0 / max(1, len(bugs)))
            score = (hit / 7.0) * precision
            note = f"hit {hit}/7, reported={len(bugs)}, precision={precision:.2f}"
            if missed:
                note += f", missed=[{', '.join(missed)}]"
                
            return (score, note)
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "code_review_hard",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_codegen_tests():
    # Prompt for code generation
    prompt = "Напиши Python-функцию parse_duration(s: str) -> int: строка вида 'XhYmZs' → секунды. Любой компонент может отсутствовать, порядок h→m→s фиксирован, пробелы вокруг и между компонентами игнорировать, пустая строка → 0. На любой другой формат (лишние символы, неверный порядок, отрицательные, число без единицы) — ValueError. Верни ТОЛЬКО код функции (можно с import re), без пояснений."
    
    # Test cases
    DURATION_CASES = [
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
    
    def check(text):
        try:
            # Extract code from markdown
            code = text.strip()
            if code.startswith("```"):
                code = code[3:]
                if code.startswith("python") or code.startswith("py"):
                    code = code[6:]
                if code.endswith("```"):
                    code = code[:-3]
            
            # Write to temporary file with test harness
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "codegen_runner.py")
            if not os.path.isfile(runner):
                raise HarnessError("нет раннера: " + runner)
            try:
                proc = subprocess.run([sys.executable, runner, temp_file],
                                      capture_output=True, timeout=30, text=True, encoding="utf-8")
                if proc.returncode != 0:
                    return (0.0, "runner error: " + (proc.stderr or "")[:200])
                data = json.loads(proc.stdout)
                ok_count = sum(1 for r in data if r.get("status") == "ok")
                failed = [r.get("case") for r in data if r.get("status") != "ok"]
                return (ok_count / len(data), str(ok_count) + "/" + str(len(data)) + " passed; failed=" + str(failed[:5]))
            except Exception as e:
                raise HarnessError("раннер сорвался: " + str(e))
        except HarnessError:
            raise
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "codegen_tests",
        "prompt": prompt,
        "fmt": None,
        "check": check
    }

def task_csv_stats():
    # Generate CSV data
    subsystems = ["wifi", "flash", "ble", "http"]
    devices = [f"DEV-{i:03d}" for i in range(1, 13)]
    
    rows = []
    for _ in range(60):
        device = rng.choice(devices)
        subsystem = rng.choice(subsystems)
        value = round(rng.uniform(0.5, 99.5), 2)
        rows.append(f"{device},{subsystem},{value}")
    
    # Calculate expected results
    expected = {}
    for sub in subsystems:
        values = [float(row.split(',')[2]) for row in rows if row.split(',')[1] == sub]
        expected[sub] = {
            "mean": round(sum(values) / len(values), 2),
            "max": max(values)
        }
    
    # Create prompt
    csv_content = "device,subsystem,value\n" + "\n".join(rows)
    prompt = "Ниже CSV. Посчитай по каждой подсистеме среднее (2 знака) и максимум поля value. Верни ТОЛЬКО JSON {subsystem: {\"mean\": number, \"max\": number}}.\n\n" + csv_content
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                return (0.0, "check error: invalid JSON structure")
            
            score = 0.0
            note_parts = []
            
            for sub in subsystems:
                if sub not in result:
                    note_parts.append(f"missing {sub}")
                    continue
                    
                data = result[sub]
                if not isinstance(data, dict) or "mean" not in data or "max" not in data:
                    note_parts.append(f"invalid structure for {sub}")
                    continue
                    
                mean_val = data["mean"]
                max_val = data["max"]
                
                expected_mean = expected[sub]["mean"]
                expected_max = expected[sub]["max"]
                
                # Check mean
                if abs(mean_val - expected_mean) <= 0.05:
                    score += 0.125
                    note_parts.append(f"{sub} mean match")
                else:
                    note_parts.append(f"{sub} mean mismatch: got {mean_val}, expected {expected_mean}")
                
                # Check max
                if abs(max_val - expected_max) <= 1e-6:
                    score += 0.125
                    note_parts.append(f"{sub} max match")
                else:
                    note_parts.append(f"{sub} max mismatch: got {max_val}, expected {expected_max}")
            
            return (score, ", ".join(note_parts))
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "csv_stats",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_summarize_facts():
    # Generate report
    facts = [
        "переполнение кольцевого буфера отладочного лога при потере WiFi",
        "wf_offload",
        "debug_log_ring",
        "heartbeat",
        "1601 строк без ошибок CRC",
        "26.65 ч непрерывной записи",
        "добавить esp_reset_reason в строку heartbeat"
    ]
    
    # Create paragraphs
    paragraphs = [
        "В ходе тестирования системы WT-P011 были выявлены аномалии в работе модулей. Система прошла полный цикл тестирования в течение 72 часов без обнаружения критических ошибок. Все компоненты функционировали корректно, кроме одного модуля, который показал отклонения при высокой нагрузке.",
        "Проверка производительности показала, что система способна обрабатывать до 1000 запросов в секунду при минимальной задержке. Среднее время отклика составляет 150 мс. Показатели соответствуют проектным требованиям и стандартам.",
        "В ходе анализа журналов были выявлены незначительные отклонения в работе модуля BLE. Причиной является временная задержка в обработке пакетов, не влияющая на общую производительность. Система демонстрирует высокую надежность при максимальной нагрузке.",
        "Тестирование на устойчивость к сбоям показало высокую надежность системы. При возникновении ошибок система автоматически восстанавливается без потери данных. Все компоненты соответствуют требованиям стандартов.",
        "Проверка безопасности показала отсутствие уязвимостей в текущей версии прошивки. Все протоколы шифрования работают корректно. Рекомендуется обновление до версии v1.2.17 для получения последних исправлений.",
        "В ходе тестирования были собраны данные по стабильности работы. Система не имела сбоев в течение 72 часов непрерывной работы. Все показатели находятся в пределах нормы и соответствуют техническим требованиям.",
        "Анализ производительности показал, что система способна обрабатывать до 1000 запросов в секунду при минимальной задержке. Показатели соответствуют проектным требованиям и стандартам. Среднее потребление энергии составляет 120 мА.",
        "Проверка совместимости с другими устройствами прошла успешно. Все протоколы взаимодействия работают корректно. Система поддерживает стандартные интерфейсы и обеспечивает высокую степень совместимости.",
        "Тестирование на нагрузку проводилось с использованием 1500 тестовых сценариев. Все сценарии завершены успешно. Система демонстрирует высокую надежность при максимальной нагрузке и не показала признаков деградации.",
        "В ходе анализа журналов были выявлены незначительные отклонения в работе модуля BLE. Причиной является временная задержка в обработке пакетов, не влияющая на общую производительность."
    ]
    
    # Insert facts at random positions
    report = []
    for i, para in enumerate(paragraphs):
        if i == 2:  # Insert first fact
            report.append(f"Ключевой факт: {facts[0]}")
            report.append(para)
        elif i == 4:  # Insert second fact
            report.append(para)
            report.append(f"Ключевой факт: {facts[1]}")
        elif i == 6:  # Insert third fact
            report.append(para)
            report.append(f"Ключевой факт: {facts[2]}")
        elif i == 8:  # Insert fourth fact
            report.append(para)
            report.append(f"Ключевой факт: {facts[3]}")
        else:
            report.append(para)
    
    # Add remaining facts
    report.append(f"Ключевой факт: {facts[4]}")
    report.append(f"Ключевой факт: {facts[5]}")
    report.append(f"Ключевой факт: {facts[6]}")
    
    # Create prompt
    prompt = "Суммируй отчёт. Верни ТОЛЬКО JSON {\"root_cause\": str, \"affected_components\": [str], \"key_numbers\": [str], \"recommendations\": [str]}.\n\n" + "\n".join(report)
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                return (0.0, "check error: invalid JSON structure")
            
            # Flatten all values into one string
            flat_text = ""
            for key, value in result.items():
                if isinstance(value, list):
                    flat_text += " ".join(str(v) for v in value)
                else:
                    flat_text += str(value)
            
            flat_text = flat_text.lower()
            
            # Check for each fact
            checks = [
                ("кольцев", "wifi"),
                ("wf_offload",),
                ("debug_log_ring",),
                ("heartbeat",),
                ("1601",),
                ("26.65|26,65",),  # спека допускает и запятую как десятичный разделитель
                ("esp_reset_reason",)
            ]
            
            found = 0
            missed = []
            
            for check_items in checks:
                all_found = True
                for item in check_items:
                    # «a|b» — засчитывается любой из вариантов написания
                    if not any(alt in flat_text for alt in item.split("|")):
                        all_found = False
                        break
                
                if all_found:
                    found += 1
                else:
                    missed.append(check_items[0])
            
            score = found / 7.0
            note = f"found {found}/7"
            if missed:
                note += f", missed=[{', '.join(missed)}]"
                
            return (score, note)
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "summarize_facts",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_strict_schema():
    # Create prompt
    paragraph = "Плата WT-P011 на прошивке v1.2.17 проработала 26.65 часа, зафиксировано 0 ошибок CRC; активны модули WiFi и BLE, OTG отключён."
    prompt = "Из абзаца извлеки данные СТРОГО в схему: {\"device\": str, \"firmware\": str, \"metrics\": {\"uptime_h\": number, \"errors\": int}, \"flags\": [str из набора wifi|ble|otg]}. Никаких других ключей. Верни ТОЛЬКО JSON.\n\nАбзац: '" + paragraph + "'"
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                return (0.0, "check error: invalid JSON structure")
            
            # Check keys
            expected_keys = {"device", "firmware", "metrics", "flags"}
            actual_keys = set(result.keys())
            
            score = 0.0
            note_parts = []
            
            if actual_keys == expected_keys:
                score += 0.2
                note_parts.append("keys match")
            else:
                note_parts.append(f"keys mismatch: got {actual_keys}, expected {expected_keys}")
                
            # Check device
            if result.get("device") == "WT-P011":
                score += 0.2
                note_parts.append("device match")
            else:
                note_parts.append(f"device mismatch: got '{result.get('device')}', expected 'WT-P011'")
                
            # Check firmware
            if "1.2.17" in result.get("firmware", ""):
                score += 0.2
                note_parts.append("firmware match")
            else:
                note_parts.append(f"firmware mismatch: got '{result.get('firmware')}', expected containing '1.2.17'")
                
            # Check metrics
            metrics = result.get("metrics", {})
            if isinstance(metrics, dict):
                uptime_h = metrics.get("uptime_h")
                errors = metrics.get("errors")
                
                # приведение в try: строковый "26.65" не должен ронять ВЕСЬ балл задачи
                try:
                    uptime_ok = uptime_h is not None and abs(float(str(uptime_h).replace(",", ".")) - 26.65) <= 0.01
                except (TypeError, ValueError):
                    uptime_ok = False
                if uptime_ok:
                    score += 0.1
                    note_parts.append("uptime match")
                else:
                    note_parts.append(f"uptime mismatch: got {uptime_h}, expected ~26.65")

                try:
                    errors_ok = errors is not None and int(errors) == 0
                except (TypeError, ValueError):
                    errors_ok = False
                if errors_ok:
                    score += 0.1
                    note_parts.append("errors match")
                else:
                    note_parts.append(f"errors mismatch: got {errors}, expected 0")
            else:
                note_parts.append("metrics invalid structure")
                
            # Check flags
            flags = result.get("flags", [])
            if isinstance(flags, list):
                flag_set = set(str(f).lower() for f in flags)
                expected_flags = {"wifi", "ble"}
                if flag_set == expected_flags:
                    score += 0.2
                    note_parts.append("flags match")
                else:
                    note_parts.append(f"flags mismatch: got {flag_set}, expected {expected_flags}")
            else:
                note_parts.append("flags invalid structure")
                
            return (score, ", ".join(note_parts))
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "strict_schema",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_c_review():
    # C code
    C_CODE = _load_fixture("buggy_ring.c.txt")
    
    # Seeded defects
    SEEDED_C = [
        ("strcpy_overflow", "strcpy(buf, s);"),
        ("check_after_copy", "if (n > MAX_LINE)"),
        ("mod_9", "% 9"),
        ("sprintf_unbounded", "sprintf(out + pos"),
        ("out_len_unused", "int ring_dump(")
    ]
    
    # Find line numbers for defects
    lines = C_CODE.split('\n')
    defect_lines = {}
    for id, substr in SEEDED_C:
        found = False
        for i, line in enumerate(lines):
            if substr in line:
                defect_lines[id] = i + 1
                found = True
                break
        if not found:
            # If not found, try to find it in the whole text
            pos = C_CODE.find(substr)
            if pos != -1:
                # Count lines before position
                line_count = C_CODE[:pos].count('\n') + 1
                defect_lines[id] = line_count
    
    # Create prompt with line numbers
    numbered_code = "\n".join([f"{i+1:2d}| {line}" for i, line in enumerate(lines)])
    prompt = "Найди ВСЕ дефекты безопасности и логики в C-коде. Нумерация строк с 1. Точность важна: перечисление заведомо лишних строк снижает оценку, поэтому указывай только те, где дефект действительно есть. Верни ТОЛЬКО JSON {\"bugs\": [{\"line\": int, \"desc\": str}]}.\n\n" + numbered_code
    
    def check(text):
        try:
            result = parse_json(text)
            if not isinstance(result, dict) or "bugs" not in result:
                return (0.0, "check error: invalid JSON structure")
            
            bugs = result["bugs"]
            hit = 0
            missed = []
            
            for id, _ in SEEDED_C:
                found = False
                expected_line = defect_lines[id]
                
                for bug in bugs:
                    if isinstance(bug, dict) and "line" in bug:
                        line = bug["line"]
                        if abs(line - expected_line) <= 1:
                            hit += 1
                            found = True
                            break
                
                if not found:
                    missed.append(id)
            
            # штраф за «дробовик» (см. code_review_hard)
            precision = min(1.0, 10.0 / max(1, len(bugs)))
            score = (hit / 5.0) * precision
            note = f"hit {hit}/5, reported={len(bugs)}, precision={precision:.2f}"
            if missed:
                note += f", missed=[{', '.join(missed)}]"
                
            return (score, note)
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "c_review",
        "prompt": prompt,
        "fmt": "json",
        "check": check
    }

def task_ru_rewrite_constraints():
    # Create prompt
    paragraph = "ну вот мы очень долго гоняли плату, как бы сутки с лишним, и просто ни одной битой строки не нашли, 1601 строка и все целые, debug_log_ring вел себя нормально."
    prompt = "Перепиши абзац для отчёта заказчику: строго 3 предложения, без слов 'очень', 'просто', 'как бы', каждое предложение начинается с заглавной буквы и заканчивается точкой, упомяни число 1601 и компонент debug_log_ring. Абзац: '" + paragraph + "'"
    
    def check(text):
        try:
            # Split into sentences
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            sentences = [s for s in sentences if s]
            
            score = 0.0
            note_parts = []
            
            # Check number of sentences
            if len(sentences) == 3:
                score += 0.2
                note_parts.append("3 sentences")
            else:
                note_parts.append(f"wrong sentence count: got {len(sentences)}, expected 3")
                
            # Check forbidden words
            forbidden = ["очень", "просто", "как бы"]
            forbidden_found = []
            
            # по ГРАНИЦАМ СЛОВА: иначе законное «простой» ловится как запрещённое «просто»
            for word in forbidden:
                if re.search(r"(?<![А-Яа-яЁёA-Za-z])" + re.escape(word) + r"(?![А-Яа-яЁёA-Za-z])", text.lower()):
                    forbidden_found.append(word)
                    
            if not forbidden_found:
                score += 0.2
                note_parts.append("no forbidden words")
            else:
                note_parts.append(f"forbidden words found: {', '.join(forbidden_found)}")
                
            # Check 1601
            if "1601" in text:
                score += 0.2
                note_parts.append("1601 mentioned")
            else:
                note_parts.append("1601 not mentioned")
                
            # Check debug_log_ring (регистр не значим: Debug_Log_Ring — тот же компонент)
            if "debug_log_ring" in text.lower():
                score += 0.2
                note_parts.append("debug_log_ring mentioned")
            else:
                note_parts.append("debug_log_ring not mentioned")
                
            # Check sentence structure
            valid_sentences = 0
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                    
                # Check starts with capital letter (cyrillic or latin)
                if re.match(r'^[А-ЯЁA-Z]', sent):
                    # Check ends with period
                    if sent.endswith('.'):
                        valid_sentences += 1
                        
            if valid_sentences == 3:
                score += 0.2
                note_parts.append("sentence structure correct")
            else:
                note_parts.append(f"wrong sentence structure: {valid_sentences}/3 valid")
                
            return (score, ", ".join(note_parts))
        except Exception as e:
            return (0.0, f"check error: {str(e)}")
    
    return {
        "name": "ru_rewrite_constraints",
        "prompt": prompt,
        "fmt": None,
        "check": check
    }

# Initialize tasks
TASKS = [
    task_log_extract(),
    task_bulk200(),
    task_needle(),
    task_code_review_hard(),
    task_codegen_tests(),
    task_csv_stats(),
    task_summarize_facts(),
    task_strict_schema(),
    task_c_review(),
    task_ru_rewrite_constraints()
]

def interpretation_block(results, model_labels, task_names):
    import sys
    from statistics import mean
    import collections

    # Сбор данных по задачам и моделям
    task_model_scores = collections.defaultdict(lambda: collections.defaultdict(list))
    task_model_reps = collections.defaultdict(lambda: collections.defaultdict(set))
    model_task_failures = collections.defaultdict(lambda: set())
    model_task_all_none = collections.defaultdict(lambda: set())

    for r in results:
        label, task, rep, score = r['label'], r['task'], r['rep'], r['score']
        task_model_scores[task][label].append(score)
        task_model_reps[task][label].add(rep)
        if score is None:
            model_task_failures[label].add(task)
            model_task_all_none[label].add(task)

    # Проверка 1: вырожденная строка
    anomalies = []
    for task in task_names:
        scores_by_model = task_model_scores[task]
        if not scores_by_model:
            continue
        means = []
        for label in model_labels:
            if label in scores_by_model:
                valid_scores = [s for s in scores_by_model[label] if s is not None]
                if len(valid_scores) >= 1:
                    means.append(mean(valid_scores))
        if len(means) >= 3 and all(abs(m - means[0]) < 0.01 for m in means):
            v = means[0]
            if v >= 0.99:
                anomalies.append(f"[{task}] максимум у всех — задача что-нибудь различает или тривиальна?")
            else:
                anomalies.append(f"[{task}] одинаковый балл {v:.2f} у всех моделей — свойство моделей или дефект стенда? Открыть сырой ответ.")

    # Проверка 3: ноль при непустом ответе
    for r in results:
        if r['score'] == 0.0 and r['response_preview'].strip():
            n = len(r['response_preview'])
            anomalies.append(f"[{r['label']}/{r['task']} rep{r['rep']}] score=0 при непустом ответе ({n} симв.) — модель не справилась или чекер не разобрал? note: {r['note'][:60]}")

    # Проверка 4: сбои среды
    for r in results:
        if r['score'] is None:
            msg = f"[{r['label']}/{r['task']} rep{r['rep']}] сбой среды ({r['note'][:60]}) — исключён из среднего; повторялся ли в обоих повторах?"
            if len(task_model_reps[r['task']][r['label']]) == 2 and all(rep in task_model_reps[r['task']][r['label']] for rep in [0, 1]):
                # Проверка: все повторы None
                all_none = True
                for rep in [0, 1]:
                    if any(res['score'] is not None for res in results if res['label'] == r['label'] and res['task'] == r['task'] and res['rep'] == rep):
                        all_none = False
                        break
                if all_none:
                    msg += " ВСЕ повторы — это уже не транзиент."
            anomalies.append(msg)

    # Проверка 5: разброс между повторами
    for task in task_names:
        for label in model_labels:
            scores = task_model_scores[task][label]
            valid_scores = [s for s in scores if s is not None]
            if len(valid_scores) >= 2 and max(valid_scores) - min(valid_scores) > 0.15:
                mn, mx = min(valid_scores), max(valid_scores)
                anomalies.append(f"[{label}/{task}] разброс между повторами {mn:.2f}..{mx:.2f} при temperature=0 — откуда недетерминизм?")

    # Проверка 6: нулевые счётчики при успехе
    for r in results:
        if r['score'] is not None and r['eval_tokens'] == 0:
            anomalies.append(f"[{r['label']}/{r['task']} rep{r['rep']}] eval_tokens=0 при score={r['score']:.2f} — счётчики API не пришли; tok/s по этой записи недостоверен.")

    # Вывод
    if not anomalies:
        sys.stderr.write("\n=== ТРЕБУЕТ ТОЛКОВАНИЯ: пусто (хороший исход) ===\n")
    else:
        sys.stderr.write(f"\n=== ТРЕБУЕТ ТОЛКОВАНИЯ ({len(anomalies)} пунктов) — прогон НЕ завершён, пока на каждый нет письменного ответа ===\n")
        for a in anomalies:
            sys.stderr.write(f" - {a}\n")

    return anomalies

def main():
    parser = argparse.ArgumentParser(description="ЖЁСТКИЙ бенчмарк локальных моделей Ollama для задач делегирования (трек A, текст)")
    parser.add_argument("--models", type=str, default="", help="Метки моделей через запятую (по умолчанию все)")
    parser.add_argument("--reps", type=int, default=2, help="Количество повторов (по умолчанию 2)")
    parser.add_argument("--tasks", type=str, default="", help="Имена задач через запятую (по умолчанию все)")
    parser.add_argument("--out", type=str, default="", help="Путь к JSON-файлу результата")
    
    args = parser.parse_args()
    
    # Parse model labels
    if args.models:
        model_labels = set(args.models.split(","))
    else:
        model_labels = {m[0] for m in MODELS}
    
    # Filter models
    filtered_models = [m for m in MODELS if m[0] in model_labels]
    
    # Parse task names
    if args.tasks:
        task_names = set(args.tasks.split(","))
    else:
        task_names = {t["name"] for t in TASKS}
    
    # Filter tasks
    filtered_tasks = [t for t in TASKS if t["name"] in task_names]
    
    results = []
    prev_model = None
    
    for label, model, think, est_MB, soft_guard in filtered_models:
        print(f"Processing model {label}...", file=sys.stderr)
        
        # Unload previous model if needed
        if prev_model is not None and prev_model != model:
            unload(prev_model)
            
        for rep in range(args.reps):
            for task in filtered_tasks:
                start_time = time.perf_counter_ns()
                
                try:
                    response = gen(model, task["prompt"], task["fmt"], think, est_MB, soft_guard)
                    end_time = time.perf_counter_ns()
                    
                    wall_s = (end_time - start_time) / 1e9
                    prompt_tokens = response.get("prompt_eval_count", 0)
                    eval_tokens = response.get("eval_count", 0)
                    eval_duration = response.get("eval_duration", 0)
                    tok_s = eval_tokens / (eval_duration / 1e9) if eval_duration > 0 else 0
                    thinking_chars = len(response.get("thinking", "") or "")
                    
                    text = response.get("response", "")
                    # Отсутствие eval_count само по себе НЕ признак обрыва: Ollama иногда
                    # отдаёт полный ответ без счётчиков (nemotron/c_review — 0.80 в
                    # повторе при eval_count=None). Признак обрыва — done=False ИЛИ
                    # пустой ответ при заметном времени. В среднее такие не берём.
                    done_flag = response.get("done", True)
                    if (not done_flag) or (not text.strip() and wall_s > 5):
                        raise HarnessError(
                            f"оборванный/пустой ответ: done={done_flag}, {len(text)} символов, {wall_s:.0f}с")
                    try:
                        score, note = task["check"](text)
                    except HarnessError as he:
                        # НЕ провал модели: помечаем отдельно, из среднего исключается
                        score, note = None, "HARNESS ERROR: " + str(he)
                    
                    result = {
                        "label": label,
                        "model": model,
                        "rep": rep,
                        "task": task["name"],
                        "score": score,
                        "note": note,
                        "wall_s": wall_s,
                        "load_s": 0,  # Placeholder
                        "prompt_tokens": prompt_tokens,
                        "eval_tokens": eval_tokens,
                        "tok_s": tok_s,
                        "thinking_chars": thinking_chars,
                        "response_preview": text[:400]
                    }
                    
                    results.append(result)
                    shown = "ОСНАСТКА" if score is None else f"{score:.2f}"
                    print(f"[{label}] rep={rep} task={task['name']} score={shown} wall={wall_s:.2f}s tok/s={tok_s:.2f}", file=sys.stderr)
                    
                except Exception as e:
                    end_time = time.perf_counter_ns()
                    wall_s = (end_time - start_time) / 1e9
                    
                    result = {
                        "label": label,
                        "model": model,
                        "rep": rep,
                        "task": task["name"],
                        # None, не 0.0: отказ VRAM/сети — сбой инфраструктуры, а не
                        # провал модели; ноль здесь превращал недоступность в «плохую модель»
                        "score": None,
                        "note": "INFRA ERROR: " + str(e),
                        "wall_s": wall_s,
                        "load_s": 0,  # Placeholder
                        "prompt_tokens": 0,
                        "eval_tokens": 0,
                        "tok_s": 0,
                        "thinking_chars": 0,
                        "response_preview": "",
                        "error": str(e)
                    }
                    
                    results.append(result)
                    print(f"[{label}] rep={rep} task={task['name']} ERROR: {str(e)}", file=sys.stderr)
                    traceback.print_exc()
        
        prev_model = model
    
    # Unload last model
    if prev_model is not None:
        unload(prev_model)
    
    # Save results
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if args.out:
        output_file = args.out
    else:
        output_file = f"hard_bench_text_result_{timestamp}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Print summary table
    task_names = [t["name"] for t in filtered_tasks]
    model_labels = [m[0] for m in filtered_models]
    
    print("\nSummary Table:", file=sys.stderr)
    print("Task", end="")
    for label in model_labels:
        print(f"\t{label}", end="")
    print("\tMEAN", end="")
    print()
    
    # Calculate scores
    task_scores = {}
    for task_name in task_names:
        task_scores[task_name] = {}
        for label in model_labels:
            task_scores[task_name][label] = []
    
    for result in results:
        task = result["task"]
        label = result["label"]
        score = result["score"]
        if task in task_scores and label in task_scores[task]:
            task_scores[task][label].append(score)
    
    # Print scores
    for task_name in task_names:
        print(task_name, end="")
        total = 0
        count = 0
        for label in model_labels:
            scores = [s for s in task_scores[task_name][label] if s is not None]
            if scores:
                avg = sum(scores) / len(scores)
                print(f"\t{avg:.2f}", end="")
                total += avg
                count += 1
            else:
                print("\t-", end="")
        if count > 0:
            mean = total / count
            print(f"\t{mean:.2f}")
        else:
            print("\t-")
    
    # Print MEAN row
    print("MEAN", end="")
    for label in model_labels:
        scores = []
        for result in results:
            if result["label"] == label and result.get("score") is not None:
                scores.append(result["score"])

        if scores:
            avg = sum(scores) / len(scores)
            print(f"\t{avg:.2f}", end="")
        else:
            print("\t-", end="")
    
    # Calculate and print tok/s and wall_total_s
    print()
    print("tok/s", end="")
    for label in model_labels:
        total_tok_s = 0
        count = 0
        for result in results:
            # у сорвавшихся вызовов tok_s=0 — включение занижало бы скорость модели
            if result["label"] == label and result.get("score") is not None:
                total_tok_s += result["tok_s"]
                count += 1
        
        if count > 0:
            avg = total_tok_s / count
            print(f"\t{avg:.2f}", end="")
        else:
            print("\t-", end="")
    
    print()
    print("wall_total_s", end="")
    for label in model_labels:
        total_wall = 0
        for result in results:
            if result["label"] == label:
                total_wall += result["wall_s"]
        
        print(f"\t{total_wall:.2f}", end="")
    
    print()
    
    interpretation_block(results, model_labels, task_names)

    # Print output file path to stdout
    print(output_file)

if __name__ == "__main__":
    main()
