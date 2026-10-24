from gridline.career.engine import build_state
from gridline.career.identity import fingerprint
from gridline.career import market


def test_matching_captures_confirm(career):
    career.race_round(1)
    st = build_state(career.events)
    rec = st.season.race(1)
    assert rec.status == "confirmed"
    assert st.season.next_round() == 2
    total = sum(d.points for d in st.season.drivers)
    assert total == sum(t.points for t in st.season.teams) and 80 <= total <= 101


def test_single_capture_is_provisional(career):
    career.race_round(1, both=False)
    assert build_state(career.events).season.race(1).status == "provisional"


def test_dispute_and_owner_ruling(career):
    career.race_round(1)
    # Jon's PC saw a different order for the race: tamper with his latest race submission
    sub = [e for e in career.events if e.kind == "result_submitted" and e.author == "B"][-1]
    entries = sub.payload["result"]["entries"]
    entries[0]["position"], entries[1]["position"] = 2, 1
    sub.payload["fingerprint"] = fingerprint(sub.payload["result"])
    st = build_state(career.events)
    assert st.season.race(1).status == "disputed"
    assert len(st.disputes) == 1
    # a non-owner ruling is ignored
    career.add("result_resolved", "B", {"season": 1, "round": 1, "session_type": 15, "submission_uid": sub.uid})
    assert build_state(career.events).season.race(1).status == "disputed"
    career.add("result_resolved", "A", {"season": 1, "round": 1, "session_type": 15, "submission_uid": sub.uid})
    st = build_state(career.events)
    assert st.season.race(1).status == "resolved"
    assert st.season.race(1).result["entries"][0]["position"] == 2


def test_ratings_and_earnings_progress(career):
    for r in range(1, 4):
        career.race_round(r)
    st = build_state(career.events)
    assert len(st.ratings["A"]) == 3
    assert st.earnings["A"] > 0
    assert 35 <= st.rating_of("A") <= 99


def test_offer_accept_moves_driver_next_season(career):
    for r in range(1, 7):
        career.race_round(r)
    st = build_state(career.events)
    offers = st.open_offers("A") + st.open_offers("B")
    assert offers, "season-end offers expected for expiring one-year deals"
    o = offers[0]
    career.add("offer_response", o.member_id, {"offer": o.__dict__, "accept": True})
    st = build_state(career.events)
    nxt = st.contract_for(o.member_id, 2)
    assert nxt.team_key == o.team_key and nxt.salary == o.salary
    assert all(x.status != "open" for x in st.offers.values() if x.member_id == o.member_id)
    # season rollover keeps both drivers seated
    career.add("season_advanced", "A", {"to_season": 2})
    st = build_state(career.events)
    assert st.current_season == 2
    assert st.contract_for(o.member_id).team_key == o.team_key
    other = "B" if o.member_id == "A" else "A"
    assert st.contract_for(other) is not None   # auto-renewed if nothing signed


def test_response_from_someone_else_is_ignored(career):
    for r in range(1, 7):
        career.race_round(r)
    st = build_state(career.events)
    o = st.open_offers("A")[0]
    career.add("offer_response", "B", {"offer": o.__dict__, "accept": True})
    assert build_state(career.events).offers[o.id].status == "open"


def test_market_value_curve():
    assert market.market_value(50) < market.market_value(70) < market.market_value(90)
    assert market.offer_windows(24) == [8, 16, 24]
