import copy
import unittest

from .core import ATTRIBUTE_KEYS, POSITION_KEYS, PROFILE_KEYS, Engine, apply_squad, choose_lineup, map_player


def fictional_player(index):
    return {"uid":index,"unique_id":10000+index,"name":f"Fictional Player {index}","age":25,"height_cm":180,
            "positions":{k:(20 if (index==0 and k=="gk") or (index!=0 and k!="gk") else 1) for k in POSITION_KEYS},
            "raw_attributes":{k:63 for k in ATTRIBUTE_KEYS if not k.startswith("raw_")},
            "raw_left_foot":88,"raw_right_foot":99,"personality":{k:12 for k in PROFILE_KEYS},
            "trait_bits":(1<<48)+3,"ability":{"current":145},"reputation":{"home":6000,"current":6500,"world":5500}}


def tactic():
    phase=[{"position":p} for p in "GK DR DCR DCL DL DMR DML AMC AMR AML ST".split()]
    return {"phases":[phase,copy.deepcopy(phase)],"tactic_name":"Fictional","native_extra_team_bits":"0","mentality":4,"instructions":{}}


class MappingTests(unittest.TestCase):
    def test_raw_attributes_and_trait_bit_width(self):
        result=map_player(fictional_player(1))
        self.assertEqual(len(result["attributes"]),69)
        self.assertEqual(result["attributes"][16],63)
        self.assertEqual(result["attributes"][39:41],[88,99])
        self.assertEqual(result["native_profile"]["traits_low"],3)
        self.assertEqual(result["native_profile"]["traits_high"],1<<16)

    def test_unknown_or_out_of_range_values_fail_closed(self):
        for value in (None,0,101,True):
            player=fictional_player(1);player["raw_attributes"]["passing"]=value
            with self.assertRaises(ValueError):map_player(player)

    def test_lineup_has_keeper_unique_players_and_honors_exclusion(self):
        players=[fictional_player(i) for i in range(26)]
        roster,picks=choose_lineup(players,tactic()["phases"],[1,2])
        self.assertEqual(len({p["uid"] for p in picks}),11)
        self.assertEqual(picks[0]["uid"],0)
        self.assertFalse({1,2}&{p["uid"] for p in roster})
        self.assertLessEqual(len(roster),23)
        with self.assertRaises(ValueError):choose_lineup(players,tactic()["phases"],[0])

    def test_engine_binding_ids_survive_roster_mapping(self):
        team={"players":[{"native_id":9000+i} for i in range(23)],"takers":{},"opposition":{"players":[],"positions":{}}}
        squad={"club":{"name":"Fictional Club"},"players":[fictional_player(i) for i in range(26)]}
        apply_squad(team,squad,tactic())
        self.assertEqual([p["native_id"] for p in team["players"]],list(range(9000,9023)))
        self.assertEqual(team["players"][0]["source_uid"],10000)

    def test_engine_destination_is_strictly_loopback(self):
        for url in ("https://example.com","http://127.0.0.1:80@example.com","http://localhost:80/private","http://localhost:80?target=remote"):
            with self.assertRaises(ValueError):Engine(url)
        self.assertEqual(Engine("http://127.0.0.1:18765").url,"http://127.0.0.1:18765")


if __name__ == "__main__":unittest.main()
