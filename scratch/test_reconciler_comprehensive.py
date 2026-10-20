import sys, os
sys.path.insert(0, os.path.abspath("."))
from shared.schemas import Alert
from self_healing.alert_reconciler import AlertReconciler

def test_reconciler_isolation_and_matching():
    print("=== Test 1: Simultaneous faults on DIFFERENT links (D-E vs E-F) ===")
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=False)

    # Alert from ML on D-E at t=100.0
    ml_de = Alert(timestamp=100.0, source="ml_engine", link="D-E", predicted_state="congested", confidence=0.85)
    r1 = reconciler.process_alert(ml_de)
    assert r1 is None, "r1 should be buffered"

    # Alert from TRAP on E-F at t=100.5 (within 2s, but DIFFERENT link!)
    trap_ef = Alert(timestamp=100.5, source="snmp_trap", link="E-F", predicted_state="failed", confidence=None)
    r2 = reconciler.process_alert(trap_ef)
    assert r2 is None, "r2 should NOT match ml_de because link is E-F != D-E!"

    # Flush after window expires
    flushed = reconciler.flush_pending(current_time=105.0)
    assert len(flushed) == 2, f"Expected 2 flushed records, got {len(flushed)}"
    stats = reconciler.get_summary_stats()
    print(f"Stats after different link alerts: {stats}")
    assert stats["agreements"] == 0, f"Expected 0 agreements, got {stats['agreements']}"
    assert stats["agreement_rate"] == 0.0, f"Expected 0.0 rate, got {stats['agreement_rate']}"
    print("PASS: Cross-link false agreement prevented! Agreement is strictly 0.0%.\n")

    print("=== Test 2: Single-fault scenario (Only TRAP on B-C) ===")
    reconciler_single = AlertReconciler(window_sec=2.0, auto_subscribe=False)
    solo_trap = Alert(timestamp=200.0, source="snmp_trap", link="B-C", predicted_state="failed", confidence=None)
    reconciler_single.process_alert(solo_trap)
    reconciler_single.flush_pending(current_time=205.0)
    stats_single = reconciler_single.get_summary_stats()
    print(f"Stats for single TRAP fault: {stats_single}")
    assert stats_single["agreements"] == 0
    assert stats_single["agreement_rate"] == 0.0
    print("PASS: Single-fault scenario yields 0.0% agreement.\n")

    print("=== Test 3: Genuine agreement on IDENTICAL link (D-E TRAP + D-E ML within window) ===")
    reconciler_agree = AlertReconciler(window_sec=2.0, auto_subscribe=False)
    trap_agree = Alert(timestamp=300.0, source="snmp_trap", link="D-E", predicted_state="failed", confidence=None)
    ml_agree = Alert(timestamp=300.4, source="ml_engine", link="D-E", predicted_state="failed", confidence=0.92)

    rec1 = reconciler_agree.process_alert(trap_agree)
    assert rec1 is None
    rec2 = reconciler_agree.process_alert(ml_agree)
    assert rec2 is not None, "rec2 should match on identical link!"
    assert rec2.agreement is True
    assert rec2.time_delta_sec == 0.4
    stats_agree = reconciler_agree.get_summary_stats()
    print(f"Stats for genuine agreement on same link: {stats_agree}")
    assert stats_agree["agreements"] == 1
    assert stats_agree["agreement_rate"] == 1.0
    print("PASS: Genuine agreement on identical link yields 100% agreement!\n")

    print("=== Test 4: Genuine agreement on IDENTICAL link with reversed endpoints (E-D TRAP + D-E ML) ===")
    reconciler_rev = AlertReconciler(window_sec=2.0, auto_subscribe=False)
    trap_rev = Alert(timestamp=400.0, source="snmp_trap", link="E-D", predicted_state="failed", confidence=None)
    ml_rev = Alert(timestamp=400.3, source="ml_engine", link="D-E", predicted_state="failed", confidence=0.88)

    reconciler_rev.process_alert(trap_rev)
    rec_rev = reconciler_rev.process_alert(ml_rev)
    assert rec_rev is not None, "rec_rev should match normalized undirected link!"
    assert rec_rev.agreement is True
    assert rec_rev.time_delta_sec == 0.3
    stats_rev = reconciler_rev.get_summary_stats()
    print(f"Stats for reversed endpoints: {stats_rev}")
    assert stats_rev["agreements"] == 1
    assert stats_rev["agreement_rate"] == 1.0
    print("PASS: Bidirectional link normalization matches perfectly!\n")

if __name__ == "__main__":
    test_reconciler_isolation_and_matching()
    print("ALL TESTS PASSED SUCCESSFULLY!")
