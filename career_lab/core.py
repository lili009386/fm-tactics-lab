"""Read-only save import, explicit field mapping, and reproducible native tests.

No game assets or save data are bundled. The official local engine server is used
without weakening its validation. Selection scores are a heuristic, not learned
FM attribute weights or a proof of optimal team selection.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
import warnings
from urllib.parse import urlsplit

import requests

POSITION_KEYS = "gk sw dl dc dr dm ml mc mr aml amc amr stc wbl wbr".split()
ATTRIBUTE_KEYS = "crossing dribbling finishing heading long_shots marking off_the_ball passing penalty_taking tackling vision handling aerial_reach command_of_area communication kicking throwing anticipation decisions one_on_ones positioning reflexes first_touch technique raw_left_foot raw_right_foot flair corners teamwork work_rate long_throws eccentricity rushing_out punching acceleration free_kick_taking strength stamina pace jumping_reach leadership dirtiness balance bravery consistency aggression agility important_matches injury_proneness versatility natural_fitness determination composure concentration".split()
PROFILE_KEYS = "professionalism loyalty sportsmanship temperament pressure ambition adaptability".split()
TACTIC_FIELDS = ("tactic_name", "native_extra_team_bits", "mentality", "instructions", "phases")
LIMITATIONS = [
    "存档解析值尚未在当前 FM27 构建中逐项对照游戏验证；结构校验通过不等于全部语义正确。",
    "引擎统一满体能、满比赛状态、满士气及固定磨合；伤停、停赛和今日可用性须手动排除。",
    "未读取的体重统一设为门将 80 kg、其他球员 75 kg；不冒充存档体重。",
    "自动首发使用公开的位置与属性评分启发式；没有学习或证明原版属性权重。",
    "对手阵容来自存档，对手战术使用明确选择的 FMF 测试模板，不代表其存档 AI 战术。",
    "定位球使用同侧默认套路，不随战术 FMF 导入；未复现存档全部比赛背景与临场指挥。",
]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def import_save(source, destination, club_names):
    """Snapshot a stable save and import selected senior squads, entirely locally."""
    import fmsave
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source.suffix.lower() != ".fm" or not source.is_file():
        raise ValueError("请选择存在的 .fm 存档")
    before = source.stat()
    if before.st_size > 1024**3:
        raise ValueError("第一版最多读取 1 GB 的存档")
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = destination / "source.fm"
    if source == snapshot:
        raise ValueError("源存档不能是导入目标")
    shutil.copy2(source, snapshot)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("游戏正在写入存档，请等待保存结束再导入")
    sha = digest(snapshot)
    if digest(source) != sha:
        raise ValueError("存档复制期间发生变化，请重新导入")
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        with fmsave.open(snapshot, strict=True) as save:
            if str(save.info.game) != "FM27":
                raise ValueError("本入口只接受 FM27 存档")
            managed = save.managed_clubs().to_dicts()
            if not managed:
                raise ValueError("未识别到执教球队；暂不支持无业或未识别的多人存档")
            all_clubs = save.clubs().to_dicts()
            chosen = {managed[0]["club_uid"]}
            for name in club_names:
                matches = [c for c in all_clubs if name in (c["name"], c["short_name"])]
                if len(matches) != 1:
                    raise ValueError(f"球队名称未唯一匹配：{name}")
                chosen.add(matches[0]["uid"])
            players = save.players()
            teams = []
            for club in all_clubs:
                if club["uid"] not in chosen:
                    continue
                squad = players.where(club_uid=club["uid"]).filter(lambda p: p.team_slot == 0).to_dicts()
                if len(squad) < 11:
                    raise ValueError(f"{club['name']} 读取的一线队少于 11 人")
                for player in squad:
                    map_player(player)  # Fail closed on missing/out-of-range needed fields.
                teams.append({"club": club, "players": squad})
            info = {key: str(getattr(save.info, key)) for key in ("game", "build", "db_version", "game_date")}
            info["known_build"] = save.info.known_build
    document = {"schema": 1, "reader": "fmsave 0.10.0", "source_filename": source.name,
                "source_sha256": sha, "source_bytes": before.st_size, "info": info,
                "managed": managed, "teams": teams,
                "reader_warnings": [str(n.message) for n in notices], "limitations": LIMITATIONS}
    write_json(destination / "squads.json", document)
    return document


def bounded(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{label} 缺失或超出支持范围 {lo}–{hi}：{value!r}")
    return value


def map_player(player):
    """Use raw 1–100 attributes; never multiply rounded UI values by five."""
    name = player.get("name")
    if not name:
        raise ValueError("球员姓名缺失")
    positions = [bounded(player["positions"].get(k), 0, 20, name+"."+k) for k in POSITION_KEYS]
    attributes = [bounded(player.get(k) if k.startswith("raw_") else player["raw_attributes"].get(k),
                          1, 100, name+"."+k) for k in ATTRIBUTE_KEYS]
    personality = player.get("personality") or {}
    profile = {k: bounded(personality.get(k), 1, 20, name+"."+k) for k in PROFILE_KEYS}
    bits = bounded(player.get("trait_bits"), 0, 2**64-1, name+".traits")
    profile.update(height_cm=bounded(player.get("height_cm"), 140, 220, name+".height"),
                   age=bounded(player.get("age"), 14, 60, name+".age"),
                   traits_low=bits & 0xffffffff, traits_high=bits >> 32,
                   current_ability=bounded(player["ability"]["current"], 0, 200, name+".CA"),
                   weight_kg=80 if positions[0] >= 15 else 75)
    for native, source in (("home_reputation", "home"), ("current_reputation", "current"), ("world_reputation", "world")):
        profile[native] = bounded(player["reputation"][source], 0, 10000, name+"."+source)
    return {"name": name, "attributes": positions + attributes, "native_profile": profile,
            "source_uid": bounded(player.get("unique_id"), 0, 0xffffffff, name+".unique_id")}


def position_key(position):
    if position in ("GK", "DR", "DL", "WBR", "WBL", "MR", "ML", "AMR", "AML"):
        return position.lower()
    for prefix, key in (("DC", "dc"), ("DM", "dm"), ("AMC", "amc"), ("MC", "mc"), ("ST", "stc")):
        if position.startswith(prefix):
            return key
    raise ValueError("未支持的位置：" + position)


WEIGHTS = {
    "gk": {"reflexes": 3, "handling": 2, "one_on_ones": 2, "aerial_reach": 1, "positioning": 1, "agility": 1},
    "dc": {"marking": 2, "tackling": 2, "positioning": 2, "jumping_reach": 1, "heading": 1, "pace": 1, "anticipation": 1},
    "fullback": {"tackling": 2, "positioning": 2, "pace": 2, "stamina": 1, "crossing": 1, "work_rate": 1},
    "dm": {"tackling": 2, "positioning": 2, "passing": 2, "decisions": 1, "anticipation": 1, "work_rate": 1},
    "mc": {"passing": 2, "decisions": 2, "first_touch": 1, "vision": 1, "stamina": 1, "work_rate": 1},
    "wing": {"dribbling": 2, "acceleration": 2, "pace": 1, "off_the_ball": 1, "crossing": 1, "passing": 1},
    "amc": {"passing": 2, "vision": 2, "first_touch": 1, "technique": 1, "off_the_ball": 1, "decisions": 1},
    "stc": {"finishing": 2, "off_the_ball": 2, "composure": 1, "anticipation": 1, "acceleration": 1, "heading": 1},
}


def fit_score(player, phases, slot):
    values = []
    for phase in phases:
        key = position_key(phase[slot]["position"])
        familiarity = player["positions"][key]
        if key == "gk" and familiarity < 15:
            return -1e9
        if key != "gk" and player["positions"]["gk"] >= 15:
            return -1e9
        group = "fullback" if key in ("dl", "dr", "wbl", "wbr") else "wing" if key in ("ml", "mr", "aml", "amr") else key
        weights = WEIGHTS[group]
        ability = sum(player["raw_attributes"][k]*v for k,v in weights.items())/sum(weights.values())
        values.append(ability * (.35+.65*familiarity/20))
    return sum(values)/len(values)


def choose_lineup(players, phases, excluded=()):
    """Exact maximum assignment for the declared heuristic, via subset DP."""
    eligible = [p for p in players if p["uid"] not in set(excluded)]
    if len(eligible) < 11:
        raise ValueError("可选球员不足 11 人")
    best = {0: (0., ())}
    for index, player in enumerate(eligible):
        scores = [fit_score(player, phases, slot) for slot in range(11)]
        updated = best.copy()
        for mask, (value, assignment) in best.items():
            for slot, score in enumerate(scores):
                if mask & (1 << slot) or score < -1e8:
                    continue
                new_mask, new_value = mask | (1 << slot), value+score
                if new_value > updated.get(new_mask, (-float("inf"), ()))[0]:
                    updated[new_mask] = new_value, assignment+((slot,index),)
        best = updated
    if 2047 not in best:
        raise ValueError("无法为阵型选出完整首发；检查门将和排除名单")
    _, picks = best[2047]
    starters = [eligible[index] for slot,index in sorted(picks)]
    starter_ids = {p["uid"] for p in starters}
    bench = sorted((p for p in eligible if p["uid"] not in starter_ids),
                   key=lambda p: (p["positions"]["gk"] >= 15, p["ability"]["current"]), reverse=True)
    # Prefer one reserve goalkeeper; remaining places rank by CA.
    keepers = [p for p in bench if p["positions"]["gk"] >= 15][:1]
    keeper_ids = {p["uid"] for p in keepers}
    others = sorted((p for p in bench if p["uid"] not in keeper_ids), key=lambda p:p["ability"]["current"], reverse=True)
    roster = (starters + keepers + others)[:23]
    details = [{"slot": i, "name": p["name"], "uid": p["uid"], "positions": [x[i]["position"] for x in phases],
                "fit_score": round(fit_score(p, phases, i), 3)} for i,p in enumerate(starters)]
    return roster, details


class Engine:
    def __init__(self, url="http://127.0.0.1:18765"):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or not parsed.port or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("只允许连接本机比赛引擎")
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False

    def call(self, route, value=None):
        r = self.session.get(self.url+route, timeout=90) if value is None else self.session.post(self.url+route, json=value, timeout=90)
        if not r.ok:
            raise RuntimeError(f"引擎 {route}: {r.status_code} {r.text}")
        return r.json()

    def import_tactic(self, path, base):
        result = self.call("/api/import-fmf", {"side":0, "scenario":base,
                    "file_base64":base64.b64encode(Path(path).read_bytes()).decode()})
        return result["scenario"]["teams"][0], result["report"]


def apply_squad(team, squad, tactic, excluded=()):
    for field in TACTIC_FIELDS:
        team[field] = copy.deepcopy(tactic[field])
    roster, picks = choose_lineup(squad["players"], team["phases"], excluded)
    if len(roster) > len(team["players"]):
        raise ValueError("阵容超过引擎侧人数上限")
    for index, player in enumerate(roster):
        team["players"][index].update(map_player(player))
        # native_id intentionally stays bound to the original fixture slot.
    team["roster_size"] = len(roster)
    team["name"] = squad["club"]["name"]
    team["lineup"] = list(range(11))
    team["captains"] = sorted(range(11), key=lambda i:roster[i]["raw_attributes"]["leadership"], reverse=True)
    team["takers"] = {k:[] for k in team["takers"]}
    for row in team["opposition"]["players"]:
        row.update(press=0, mark=0, tackle=0, foot=0, personal=False)
    for row in team["opposition"]["positions"].values():
        row.update(press=0, mark=0, tackle=0, foot=0, personal=False)
    return picks


def compare(snapshot, candidates, opponents, output, *, engine=None, seeds=range(271000,271010), excluded=(), progress=None):
    """Each opponent entry holds club_uid and an explicitly selected tactic path."""
    engine = engine or Engine()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "state.json").exists():
        raise ValueError("输出目录已有实验；请使用新目录以保留记录")
    seeds = list(seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("种子不能为空或重复")
    status = engine.call("/api/status")
    if not status["engine_compatibility"]["can_simulate"]:
        raise ValueError("引擎兼容性检查未通过")
    base = engine.call("/api/defaults")
    squads = {t["club"]["uid"]:t for t in snapshot["teams"]}
    club_uid = snapshot["managed"][0]["club_uid"]
    if not candidates or not opponents or club_uid in [o["club_uid"] for o in opponents]:
        raise ValueError("请选择候选战术以及不同于执教球队的对手")
    tactics = {}
    for path in dict.fromkeys([str(p) for p in candidates]+[str(o["tactic"]) for o in opponents]):
        tactic, report = engine.import_tactic(path, base)
        tactics[path] = tactic
        write_json(output / "imports" / (Path(path).stem+".json"), {"tactic":tactic,"report":report})
    state = {"status":"running", "completed":0, "total":len(candidates)*len(opponents)*2*len(seeds), "legs":[],
             "club":squads[club_uid]["club"]["name"], "source_sha256":snapshot["source_sha256"], "limitations":LIMITATIONS,
             "seeds":seeds, "excluded_uids":list(excluded), "opponents":opponents, "candidates":[str(p) for p in candidates]}
    def persist():
        write_json(output/"state.json",state)
        if progress:
            progress(state)
    persist()
    try:
        for candidate in candidates:
            candidate = str(candidate)
            for opponent in opponents:
                for tested_side in (0,1):
                    scenario = copy.deepcopy(base)
                    own_picks = apply_squad(scenario["teams"][tested_side], squads[club_uid], tactics[candidate], excluded)
                    apply_squad(scenario["teams"][1-tested_side], squads[opponent["club_uid"]], tactics[str(opponent["tactic"])])
                    scenario = engine.call("/api/validate", scenario)["scenario"]
                    job_id = engine.call("/api/run", {"scenario":scenario,"seeds":seeds,"workers":min(4,status["batch"]["maximum"]),"event_details":False})["id"]
                    leg = {"id":job_id,"candidate":candidate,"opponent":opponent["club_uid"],"tested_side":tested_side,"lineup":own_picks,"completed":0}
                    state["legs"].append(leg)
                    while True:
                        job = engine.call("/api/jobs/"+job_id)
                        leg.update(completed=job["completed"], status=job["status"], failures=len(job.get("failures",[])))
                        write_json(output/"jobs"/(job_id+".json"),job)
                        state["completed"] = sum(l["completed"] for l in state["legs"])
                        persist()
                        if job["status"] not in ("queued","running"):
                            if job["status"] != "complete" or job["completed"] != len(seeds) or job.get("failures"):
                                raise RuntimeError("原生比赛失败，已保留现场并停止；不静默重跑")
                            break
                        time.sleep(2)
        state["status"] = "completed"
        results = summarize(state, output)
        write_json(output/"results.json",results)
        state["ranking"] = results["ranking"]
        persist()
        return results
    except Exception as exc:
        state.update(status="error",error=str(exc));persist();raise


def summarize(state, output):
    table = {}
    for leg in state["legs"]:
        candidate = leg["candidate"]
        row = table.setdefault(candidate,{"tactic":Path(candidate).stem,"path":candidate,"matches":0,"wins":0,"draws":0,"losses":0,"goals_for":0,"goals_against":0,"xg_for":0.,"xg_against":0.})
        job = json.loads((Path(output)/"jobs"/(leg["id"]+".json")).read_text(encoding="utf-8"))
        seen = set()
        for run in job["runs"]:
            if run["seed"] in seen or not run["verified"] or not run["result"]["full_match_completed"]:
                raise ValueError("比赛结果重复或未通过校验")
            seen.add(run["seed"])
            side = leg["tested_side"]
            a,b = run["result"]["score"][side],run["result"]["score"][1-side]
            row["matches"]+=1;row["goals_for"]+=a;row["goals_against"]+=b
            row["wins" if a>b else "draws" if a==b else "losses"]+=1
            row["xg_for"]+=run["statistics"]["teams"][side]["xg"]
            row["xg_against"]+=run["statistics"]["teams"][1-side]["xg"]
            if digest(Path(job["output_dir"])/run["log"]) != run["log_sha256"]:
                raise ValueError("原生日志校验和不一致")
        if seen != set(state["seeds"]):
            raise ValueError("种子集合不完整")
    for row in table.values():
        row["win_rate"] = row["wins"]/row["matches"]
        row["points_per_game"] = (3*row["wins"]+row["draws"])/row["matches"]
    ranking = sorted(table.values(),key=lambda r:(r["points_per_game"],r["goals_for"]-r["goals_against"]),reverse=True)
    return {"matches":sum(r["matches"] for r in ranking),"club":state["club"],"ranking":ranking,"limitations":LIMITATIONS,
            "native_logs_verified":True,"seed_sets_verified":True,"selection_warning":"这是所测候选中的排名；需另用新种子复测，不能宣称全局最高胜率。"}
