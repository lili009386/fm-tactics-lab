"""Ten explicit, independently authored tactic experiments for a Milan squad.

These are hypotheses to test, not recommended winning tactics. Build fresh team
instructions and roles from the game's catalog, never copy another author's FMF.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
from pathlib import Path

from .core import Engine, write_json


def phase(spec):
    return [tuple(cell.split(":")) for cell in spec.split()]


CONTROL={"PassingDirectness":3,"Tempo":47,"LineOfEngagement":62,"DefensiveLine":57,"TriggerPress":66,
         "Patience":17,"Crossing":12,"ShotsFromDistance":16,"GoalKicks":44,"GoalkeeperDistributionTarget":35,
         "BuildUpStrategy":7,"AttackingWidth":51}
PRESS={**CONTROL,"LineOfEngagement":61,"TriggerPress":65,"DefensiveTransition":70,"AttackingTransition":54,
       "PassReception":5,"GoalkeeperDistributionSpeed":42,"PreventShortGKDistribution":69}
TRANSITION={"PassingDirectness":0,"Tempo":47,"LineOfEngagement":62,"DefensiveLine":0,"TriggerPress":66,
            "DefensiveTransition":71,"AttackingTransition":54,"PassReception":5,"GoalkeeperDistributionSpeed":42,
            "Crossing":12,"Patience":9,"BuildUpStrategy":8,"ProgressThrough":24}

BACK4="GK:BallPlayingGoalkeeper DR:FullBack DCR:BallPlayingCentreBack DCL:CentreBack DL:WingBack"
OOP4="GK:OPSweeperKeeper DR:OPFullBack DCR:OPCentreBack DCL:OPCoveringCentreBack DL:OPFullBack"
BACK3="GK:BallPlayingGoalkeeper DCR:WideCentreBack DC:BallPlayingCentreBack DCL:CentreBack WBR:WingBack WBL:WingBack"
OOP3="GK:OPSweeperKeeper DCR:OPCentreBack DC:OPCoveringCentreBack DCL:OPCentreBack DR:OPFullBack DL:OPFullBack"

DESIGNS=[
 {"key":"D01","name":"4231 Control","hypothesis":"双中场承接、莫德里奇式组织者与单中锋，控制节奏并保留边路宽度。","mentality":5,"settings":CONTROL,
  "ip":BACK4+" DMR:DefensiveMidfielder DML:DeepLyingPlaymaker AMC:AdvancedPlaymaker AMR:InsideForward AML:Winger ST:CentreForward",
  "oop":OOP4+" MCR:OPScreeningCentralMidfielder MCL:OPCentralMidfielder AMC:OPTrackingAttackingMidfielder MR:OPTrackingWideMidfielder ML:OPTrackingWideMidfielder ST:OPCentreForward"},
 {"key":"D02","name":"4231 Fast Channels","hypothesis":"影锋与拉边中锋错位，检验快速纵向推进和更强反抢是否提高创造机会能力。","mentality":6,"settings":{**PRESS,"PassingDirectness":0,"Tempo":46},
  "ip":BACK4+" DMR:DefensiveMidfielder DML:DeepLyingPlaymaker AMC:SecondStriker AMR:WideForward AML:InsideForward ST:ChannelForward",
  "oop":OOP4+" DMR:OPScreeningDefensiveMidfielder DML:OPDefensiveMidfielder AMC:OPAttackingMidfielder AMR:OPTrackingWinger AML:OPTrackingWinger ST:OPTrackingCentreForward"},
 {"key":"D03","name":"433 Midfield Control","hypothesis":"三中场分配组织和前插工作，以单后腰保护中卫，减少对老将连续高压逼抢的依赖。","mentality":5,"settings":{**CONTROL,"Tempo":0},
  "ip":BACK4+" DMC:DefensiveMidfielder MCR:MidfieldPlaymaker MCL:ChannelMidfielder AMR:InsideForward AML:Winger ST:CentreForward",
  "oop":OOP4+" DMC:OPScreeningDefensiveMidfielder MCR:OPScreeningCentralMidfielder MCL:OPCentralMidfielder MR:OPTrackingWideMidfielder ML:OPTrackingWideMidfielder ST:OPCentreForward"},
 {"key":"D04","name":"433 Inverted Press","hypothesis":"右后卫内收到中路，左侧保持宽度，测试高位抢回球权后立即推进。","mentality":5,"settings":PRESS,
  "ip":BACK4.replace("DR:FullBack","DR:InsideWingBack")+" DMC:DeepLyingPlaymaker MCR:CentralMidfielder MCL:ChannelMidfielder AMR:InsideForward AML:WideForward ST:CentreForward",
  "oop":OOP4+" DMC:OPScreeningDefensiveMidfielder MCR:OPPressingCentralMidfielder MCL:OPCentralMidfielder MR:OPTrackingWideMidfielder ML:OPTrackingWideMidfielder ST:OPTrackingCentreForward"},
 {"key":"D05","name":"3421 Stable Base","hypothesis":"利用米兰中卫储备搭建三中卫、双后腰结构，前场一名组织者连接影锋与中锋。","mentality":4,"settings":{**CONTROL,"DefensiveLine":0},
  "ip":BACK3+" DMR:DeepLyingPlaymaker DML:DefensiveMidfielder AMCR:AdvancedPlaymaker AMCL:SecondStriker ST:CentreForward",
  "oop":OOP3+" DMR:OPScreeningDefensiveMidfielder DML:OPDefensiveMidfielder MCR:OPCentralMidfielder MCL:OPCentralMidfielder ST:OPCentreForward"},
 {"key":"D06","name":"3421 Wing Surge","hypothesis":"双翼卫提高进攻站位，前场两人围绕中锋跑动；用三中卫承接丢球后的风险。","mentality":6,"settings":{**TRANSITION,"SupportingRunsSecondary":25,"AttackingWidth":51},
  "ip":BACK3.replace("WBR:WingBack","WBR:AdvancedWingBack").replace("WBL:WingBack","WBL:AdvancedWingBack")+" DMR:DeepLyingPlaymaker DML:DefensiveMidfielder AMCR:AdvancedPlaymaker AMCL:SecondStriker ST:CentreForward",
  "oop":OOP3+" DMR:OPScreeningDefensiveMidfielder DML:OPDefensiveMidfielder MCR:OPCentralMidfielder MCL:OPCentralMidfielder ST:OPCentralOutletCentreForward"},
 {"key":"D07","name":"352 Vertical Pair","hypothesis":"尝试拉莫斯型中锋与第二前锋组合，三中场负责传递，翼卫提供两侧推进路线。","mentality":5,"settings":{**TRANSITION,"PassingDirectness":2,"ProgressThrough":0},
  "ip":BACK3+" DMC:DeepLyingPlaymaker MCR:MidfieldPlaymaker MCL:ChannelMidfielder STR:CentreForward STL:ChannelForward",
  "oop":OOP3+" DMC:OPScreeningDefensiveMidfielder MCR:OPScreeningCentralMidfielder MCL:OPCentralMidfielder STR:OPCentreForward STL:OPSplittingOutletCentreForward"},
 {"key":"D08","name":"442 Diamond Links","hypothesis":"菱形中场为前场组织者提供短传点，双前锋占据禁区，边后卫承担宽度。","mentality":5,"settings":{**CONTROL,"Tempo":0,"AttackingWidth":52,"ProgressThrough":23},
  "ip":BACK4+" DMC:DeepLyingPlaymaker MCR:CentralMidfielder MCL:ChannelMidfielder AMC:AdvancedPlaymaker STR:CentreForward STL:ChannelForward",
  "oop":OOP4+" DMC:OPScreeningDefensiveMidfielder MCR:OPCentralMidfielder MCL:OPCentralMidfielder AMC:OPTrackingAttackingMidfielder STR:OPCentreForward STL:OPSplittingOutletCentreForward"},
 {"key":"D09","name":"41230 Shadow Waves","hypothesis":"独立设计无锋方案，用影锋和两侧内切攻击者制造后插上；与已有少林方案进行对照。","mentality":5,"settings":{**PRESS,"AttackingWidth":52},
  "ip":BACK4+" DMC:DefensiveMidfielder MCR:MidfieldPlaymaker MCL:ChannelMidfielder AMR:InsideForward AMC:SecondStriker AML:WideForward",
  "oop":OOP4+" DMC:OPScreeningDefensiveMidfielder MCR:OPCentralMidfielder MCL:OPCentralMidfielder MR:OPTrackingWideMidfielder AMC:OPAttackingMidfielder ML:OPTrackingWideMidfielder"},
 {"key":"D10","name":"4321 Rossoneri Tree","hypothesis":"圣诞树有球结构保留单中锋和双前腰；无球时前腰回到边路，尝试兼顾中路组合与防守宽度。","mentality":5,"settings":{**CONTROL,"CreativeFreedom":19,"AttackingWidth":52,"PassReception":5},
  "ip":BACK4+" DMC:DefensiveMidfielder MCR:MidfieldPlaymaker MCL:CentralMidfielder AMCR:SecondStriker AMCL:AdvancedPlaymaker ST:CentreForward",
  "oop":OOP4+" DMC:OPScreeningDefensiveMidfielder MCR:OPCentralMidfielder MCL:OPCentralMidfielder MR:OPTrackingWideMidfielder ML:OPTrackingWideMidfielder ST:OPCentreForward"},
]


def construct(design, base, catalog):
    scenario=copy.deepcopy(base);team=scenario["teams"][0]
    groups={g["name"]:g for g in catalog["team_instructions"]}
    team["instructions"]={str(g["id"]):next((o["id"] for o in g["options"] if o["native_bit"]==0),g["options"][1]["id"]) for g in groups.values()}
    for name,bit in design["settings"].items():
        group=groups[name];options=[o for o in group["options"] if o["native_bit"]==bit]
        if len(options)!=1:raise ValueError(f"Catalog option unavailable: {name}:{bit}")
        team["instructions"][str(group["id"])]=options[0]["id"]
    team.update(mentality=design["mentality"],native_extra_team_bits="0",tactic_name=f"Milan Lab {design['key']} - {design['name']}")
    team["phases"]=[]
    masks={p["id"]:p["mask"] for p in catalog["positions"]}
    for index,key in enumerate(("ip","oop")):
        cells=phase(design[key])
        if len(cells)!=11 or len({p for p,r in cells})!=11 or cells[0][0]!="GK":raise ValueError("Invalid authored formation")
        centrebacks=sum(bool(masks[p]&16) for p,r in cells);dms=sum(bool(masks[p]&128) for p,r in cells)
        context=catalog["role_eligibility_context"][f"{3 if centrebacks>=3 else 0}:{int(dms==1)}"]
        for position,role in cells:
            if role not in context[position][index]:raise ValueError(f"Illegal authored role {design['key']} {position}:{role}")
        team["phases"].append([{"position":p,"role":r,"duty":"0","instructions":{str(g["id"]):0 for g in catalog["player_instructions"]},"target_player":255,"target_position":0} for p,r in cells])
    return scenario


def generate(tactics_dir, output, engine=None):
    engine=engine or Engine();tactics_dir,output=Path(tactics_dir),Path(output)
    tactics_dir.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True)
    base,catalog=engine.call("/api/defaults"),engine.call("/api/catalog")
    records=[]
    for design in DESIGNS:
        authored=construct(design,base,catalog)
        # Rules stay 'game': reject invalid inputs rather than weakening validation.
        validated=engine.call("/api/validate",authored)["scenario"]
        for field in ("phases","instructions","mentality","native_extra_team_bits"):
            if validated["teams"][0][field]!=authored["teams"][0][field]:raise ValueError("Authored tactic changed during validation")
        exported=engine.call("/api/export-fmf",{"side":0,"scenario":validated,"name":validated["teams"][0]["tactic_name"]})
        data=base64.b64decode(exported["file_base64"],validate=True)
        if not exported["report"]["native_roundtrip_verified"] or hashlib.sha256(data).hexdigest()!=exported["report"]["sha256"]:raise ValueError("Native export verification failed")
        destination=tactics_dir/exported["filename"]
        if destination.exists() and destination.read_bytes()!=data:raise ValueError(f"Existing different design: {destination}")
        destination.write_bytes(data)
        record={**design,"path":str(destination),"report":exported["report"]}
        write_json(output/(design["key"]+".json"),{"design":record,"scenario":validated})
        records.append(record)
    write_json(output/"designs.json",records)
    return records


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--tactics-dir",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();print(f"Generated {len(generate(args.tactics_dir,args.output))} validated original designs")
