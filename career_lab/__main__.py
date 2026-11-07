"""Loopback-only desktop companion; all saves and results stay on this machine."""
from __future__ import annotations
import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import uuid

from .core import Engine, LIMITATIONS, apply_squad, choose_lineup, compare, digest, import_save, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-dir", type=Path, required=True)
    parser.add_argument("--tactics-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--watch-run", type=Path)
    parser.add_argument("--engine", default="http://127.0.0.1:18765")
    parser.add_argument("--port", type=int, default=18766)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    session_path = args.data_dir/"session.json"
    saved = json.loads(session_path.read_text(encoding="utf-8")) if session_path.exists() else {}
    initial_snapshot = args.snapshot or (Path(saved["snapshot_path"]) if saved.get("snapshot_path") else None)
    initial_run = args.watch_run or (Path(saved["run"]) if saved.get("run") else None)
    lock = threading.RLock()
    context = {"snapshot":None, "snapshot_path":initial_snapshot, "import_status":"idle", "compare_pending":False,
               "error":None, "run":initial_run, "external_watch":bool(args.watch_run) or saved.get("external_watch",False)}
    if initial_snapshot:
        context["snapshot"] = json.loads(initial_snapshot.read_text(encoding="utf-8"))
    if initial_run and not context["external_watch"] and (initial_run/"state.json").exists():
        previous = json.loads((initial_run/"state.json").read_text(encoding="utf-8"))
        if previous["status"] == "running":
            previous.update(status="interrupted",error="上轮程序退出，测试未完整结束。记录已保留；待引擎当前任务结束后可新建测试。")
            write_json(initial_run/"state.json",previous)
    engine = Engine(args.engine)

    def save_session():
        with lock:
            write_json(session_path,{k:context[k] for k in ("snapshot_path","run","external_watch")})
    save_session()

    def file_in(directory, name, suffix):
        path = (directory / str(name)).resolve()
        if path.parent != directory.resolve() or path.suffix.lower() != suffix or not path.is_file():
            raise ValueError("请选择列表中的文件")
        return path

    def snapshot_required():
        with lock:
            snapshot = context["snapshot"]
        if snapshot is None:
            raise ValueError("请先导入存档")
        return snapshot

    def run_state():
        with lock:
            directory = context["run"]
        if directory and (Path(directory)/"state.json").exists():
            return json.loads((Path(directory)/"state.json").read_text(encoding="utf-8"))
        return {"status":"running" if context["compare_pending"] else "idle", "completed":0, "total":0}

    def busy():
        return context["import_status"] == "running" or context["compare_pending"] or run_state()["status"] == "running"

    def import_task(source, clubs, destination):
        try:
            document = import_save(source, destination, clubs)
            with lock:
                context.update(snapshot=document, snapshot_path=destination/"squads.json", import_status="completed", error=None)
            save_session()
        except Exception as exc:
            with lock:
                context.update(import_status="error",error=str(exc))

    def compare_task(snapshot, candidates, opponents, destination, seeds, excluded):
        try:
            compare(snapshot,candidates,opponents,destination,engine=Engine(args.engine),seeds=seeds,excluded=excluded)
        except Exception as exc:
            with lock:
                context["error"] = str(exc)
            if not (destination/"state.json").exists():
                write_json(destination/"state.json",{"status":"error","completed":0,"total":0,"error":str(exc)})
        finally:
            with lock:
                context["compare_pending"] = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def send(self, value, status=200, content_type="application/json; charset=utf-8"):
            data = value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers();self.wfile.write(data)

        def do_GET(self):
            if self.headers.get("Host") not in {f"127.0.0.1:{args.port}",f"localhost:{args.port}"}:
                return self.send({"error":"只允许本机访问"},403)
            try:
                if self.path in ("/","/app.js","/style.css"):
                    file = Path(__file__).parent/"web"/("index.html" if self.path=="/" else self.path[1:])
                    mime = "text/html" if self.path=="/" else "text/javascript" if self.path.endswith(".js") else "text/css"
                    return self.send(file.read_bytes(),content_type=mime+"; charset=utf-8")
                if self.path == "/api/state":
                    with lock:
                        snapshot, error, import_status = context["snapshot"],context["error"],context["import_status"]
                    own = None
                    if snapshot:
                        own = next(t for t in snapshot["teams"] if t["club"]["uid"]==snapshot["managed"][0]["club_uid"])
                    return self.send({"saves":[p.name for p in sorted(args.save_dir.glob("*.fm"),key=lambda p:p.stat().st_mtime,reverse=True)],
                        "tactics":[p.name for p in args.tactics_dir.glob("*.fmf")],"import_status":import_status,"error":error,
                        "snapshot":None if not snapshot else {"info":snapshot["info"],"source_filename":snapshot["source_filename"],"source_sha256":snapshot["source_sha256"],
                            "managed":snapshot["managed"],"teams":[{"uid":t["club"]["uid"],"name":t["club"]["name"],"count":len(t["players"])} for t in snapshot["teams"]],
                            "players":[{"uid":p["uid"],"name":p["name"],"age":p["age"],"positions":p["natural_positions"],"condition":p["raw_condition"],"ca":p["ability"]["current"]} for p in own["players"]]},
                        "run":run_state(),"limitations":LIMITATIONS})
                if self.path == "/api/results":
                    with lock:
                        directory = context["run"]
                    if not directory or not (Path(directory)/"results.json").exists():
                        raise ValueError("本轮还没有完整结果")
                    return self.send((Path(directory)/"results.json").read_bytes())
                return self.send({"error":"Not found"},404)
            except Exception as exc:
                return self.send({"error":str(exc)},400)

        def do_POST(self):
            origin = self.headers.get("Origin")
            allowed = {f"http://127.0.0.1:{args.port}",f"http://localhost:{args.port}"}
            if origin and origin not in allowed:
                return self.send({"error":"不接受其他网站发起的请求"},403)
            if self.headers.get("Host") not in {f"127.0.0.1:{args.port}",f"localhost:{args.port}"}:
                return self.send({"error":"只允许本机访问"},403)
            try:
                length = int(self.headers.get("Content-Length","0"))
                if length > 100000 or not self.headers.get("Content-Type","").startswith("application/json"):
                    raise ValueError("请求格式或大小不受支持")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/import-save":
                    if busy():
                        raise ValueError("当前导入或测试尚未结束")
                    source = file_in(args.save_dir,data["save_name"],".fm")
                    clubs = [str(x).strip() for x in data.get("opponents",[]) if str(x).strip()]
                    if len(clubs)>12:
                        raise ValueError("一次最多导入 12 支对手球队")
                    destination = args.data_dir/"snapshots"/uuid.uuid4().hex[:12]
                    with lock:
                        if busy():
                            raise ValueError("已有任务正在运行")
                        context.update(import_status="running",error=None,run=None,external_watch=False)
                    threading.Thread(target=import_task,args=(source,clubs,destination),daemon=True).start()
                    return self.send({"started":True},202)
                if self.path == "/api/preview":
                    snapshot = snapshot_required()
                    path = file_in(args.tactics_dir,data["candidate"],".fmf")
                    tactic, report = engine.import_tactic(path,engine.call("/api/defaults"))
                    own = next(t for t in snapshot["teams"] if t["club"]["uid"]==snapshot["managed"][0]["club_uid"])
                    roster,picks = choose_lineup(own["players"],tactic["phases"],data.get("excluded",[]))
                    return self.send({"lineup":picks,"bench":[p["name"] for p in roster[11:]],"import_report":report})
                if self.path == "/api/compare":
                    if busy():
                        raise ValueError("当前导入或测试尚未结束")
                    snapshot = snapshot_required()
                    candidates = [file_in(args.tactics_dir,n,".fmf") for n in data["candidates"]]
                    if len(candidates)!=len(set(candidates)):
                        raise ValueError("候选战术重复")
                    opponents = [{"club_uid":int(o["club_uid"]),"tactic":str(file_in(args.tactics_dir,o["tactic"],".fmf"))} for o in data["opponents"]]
                    if len(opponents)!=len({o["club_uid"] for o in opponents}):
                        raise ValueError("对手球队重复")
                    per_leg, seed = int(data.get("per_leg",10)),int(data.get("seed",271000))
                    total = 2*len(candidates)*len(opponents)*per_leg
                    if not 1<=per_leg<=100 or not 1<=total<=5000 or not 1<=seed<2**31-1000:
                        raise ValueError("测试场数或随机种子超出范围")
                    destination = args.data_dir/"runs"/uuid.uuid4().hex[:12]
                    with lock:
                        if busy():
                            raise ValueError("已有任务正在运行")
                        context.update(run=destination,error=None,compare_pending=True,external_watch=False)
                    save_session()
                    threading.Thread(target=compare_task,args=(snapshot,candidates,opponents,destination,range(seed,seed+per_leg),data.get("excluded",[])),daemon=True).start()
                    return self.send({"started":True,"total":total},202)
                if self.path == "/api/export-winner":
                    snapshot = snapshot_required()
                    state = run_state()
                    if state["status"] != "completed":
                        raise ValueError("测试尚未全部完成")
                    winner = state["ranking"][0]
                    path = file_in(args.tactics_dir,Path(winner["path"]).name,".fmf")
                    base = engine.call("/api/defaults")
                    tactic, _ = engine.import_tactic(path,base)
                    own = next(t for t in snapshot["teams"] if t["club"]["uid"]==snapshot["managed"][0]["club_uid"])
                    picks = apply_squad(base["teams"][0],own,tactic,state.get("excluded_uids",[]))
                    result = engine.call("/api/export-fmf",{"side":0,"scenario":base,"name":f"FM27 Career {state['total']} - {path.stem}"})
                    payload = base64.b64decode(result["file_base64"],validate=True)
                    import hashlib
                    if not result["report"]["native_roundtrip_verified"] or hashlib.sha256(payload).hexdigest()!=result["report"]["sha256"]:
                        raise ValueError("战术导出回读校验失败")
                    destination = args.tactics_dir/result["filename"]
                    if destination.exists() and destination.read_bytes()!=payload:
                        destination = destination.with_stem(destination.stem+"-"+result["report"]["sha256"][:8])
                    destination.write_bytes(payload)
                    proof = {"path":str(destination),"report":result["report"],"lineup":picks}
                    write_json(Path(context["run"])/"winner_export.json",proof)
                    return self.send(proof)
                return self.send({"error":"Not found"},404)
            except Exception as exc:
                return self.send({"error":str(exc)},400)

    server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Career squad lab: http://127.0.0.1:{args.port}",flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
