"""Screen original designs, then retest finalists against a reference on new seeds."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from .core import Engine, compare, write_json
from .designs import generate


def search(snapshot, designs, opponents, reference, output, progress=None):
    output=Path(output)
    if (output/"state.json").exists():raise ValueError("实验目录已存在，请保留旧结果并指定新目录")
    output.mkdir(parents=True,exist_ok=True)
    candidates=[d["path"] for d in designs]
    first_total=len(candidates)*len(opponents)*2*5
    second_total=(min(4,len(candidates))+1)*len(opponents)*2*10
    state={"status":"running","completed":0,"total":first_total+second_total,"stage":"初筛",
           "club":snapshot["managed"][0]["club_name"],"source_sha256":snapshot["source_sha256"],"excluded_uids":[],
           "ranking_metric":"win_rate","selection_policy":"position-and-role-heuristic-v2",
           "ranking_notice":"先初筛，再用新随机种子复测。最终排名仅使用复测样本；初筛场次不混入复测胜率。"}
    protocol={"designs":designs,"opponents":opponents,"reference":str(reference),"screen_seeds":list(range(273000,273005)),
              "validation_seeds":list(range(274000,274010)),"screen_matches":first_total,"validation_matches":second_total,
              "selection":"Top four original designs by win rate, then points per game, then goal difference; add reference",
              "ranking":"Validation win rate, then points per game, then goal difference",
              "source_sha256":snapshot["source_sha256"],"selection_policy":state["selection_policy"],
              "code_sha256":{n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ("core.py","designs.py","search.py")}}
    write_json(output/"protocol.json",protocol)
    def persist():
        write_json(output/"state.json",state)
        if progress:progress(state)
    def screening(s):
        state.update(stage="初筛",completed=s["completed"]);persist()
    def validation(s):
        state.update(stage="复测",completed=first_total+s["completed"]);persist()
    persist()
    try:
        screened=compare(snapshot,candidates,opponents,output/"screening",seeds=range(273000,273005),progress=screening,ranking_metric="win_rate")
        finalists=[r["path"] for r in screened["ranking"][:4]]+[str(reference)]
        write_json(output/"shortlist.json",{"finalists":finalists,"screening_ranking":screened["ranking"]})
        validated=compare(snapshot,finalists,opponents,output/"validation",seeds=range(274000,274010),progress=validation,ranking_metric="win_rate")
        report={**validated,"matches":first_total+second_total,"screening_matches":first_total,"validation_matches":second_total,
                "screening_ranking":screened["ranking"],"reference":str(reference),"ranking_metric":"win_rate",
                "ranking_sample":"new-seed validation only","selection_policy":state["selection_policy"]}
        write_json(output/"results.json",report)
        state.update(status="completed",stage="完成",completed=state["total"],ranking=validated["ranking"])
        persist();return report
    except Exception as exc:
        state.update(status="error",error=str(exc));persist();raise


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",type=Path,required=True);p.add_argument("--designs",type=Path,required=True)
    p.add_argument("--opponents-from",type=Path,required=True);p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    read=lambda f:json.loads(f.read_text(encoding="utf-8"))
    last=[None]
    def report(s):
        now=(s["stage"],s["completed"],s["status"])
        if now!=last[0]:
            print(json.dumps({k:s.get(k) for k in ("stage","status","completed","total","error")},ensure_ascii=False),flush=True);last[0]=now
    result=search(read(a.snapshot),read(a.designs),read(a.opponents_from)["opponents"],a.reference,a.output,progress=report)
    print(json.dumps(result["ranking"],ensure_ascii=False),flush=True)
