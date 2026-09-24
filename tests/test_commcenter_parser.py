from carrierbundlelab.activation.binding import _status_for
from carrierbundlelab.activation.commcenter import correlate_attempts
from carrierbundlelab.models import BindingStatus


def test_resolved_path_and_override_success_correlate():
    attempts = correlate_attempts(
        [
            '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 1"}',
            '{"process":"CommCenter","message":"Resolved path        : /var/mobile/Library/Carrier Bundles/CarrierLab.bundle"}',
            '{"process":"CommCenter","message":"Linking Path: /var/mobile/Library/Carrier Bundles/BundleLinks/Carrier1Bundle.bundle"}',
            '{"process":"CommCenter","message":"kOverrideBundleSuccess"}',
        ]
    )
    assert len(attempts) == 1
    assert attempts[0].slot == 1
    assert attempts[0].resolved_path == "CarrierLab.bundle"
    assert attempts[0].override_success is True


def test_override_failure():
    attempts = correlate_attempts(['{"process":"CommCenter","message":"kOverrideBundleFailure"}'])
    assert attempts[0].override_failure
    status, _ = _status_for(attempts, "CarrierLab.bundle", timed_out=False)
    assert status == BindingStatus.FAILED


def test_generic_success_not_accepted():
    assert correlate_attempts(['{"process":"CommCenter","message":"successful connection"}']) == []
    assert correlate_attempts(['{"process":"backboardd","message":"kOverrideBundleSuccess"}']) == []


def test_dual_sim_correlation():
    attempts = correlate_attempts(
        [
            '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 1"}',
            '{"process":"CommCenter","message":"Resolved path: /x/CarrierLab.bundle slot 1"}',
            '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 2"}',
            '{"process":"CommCenter","message":"Resolved path: /x/MTS_ru.bundle slot 2"}',
        ]
    )
    assert [attempt.slot for attempt in attempts] == [1, 2]
    assert attempts[0].resolved_path == "CarrierLab.bundle"
    assert attempts[1].resolved_path == "MTS_ru.bundle"


def test_resolved_path_is_only_observed():
    attempts = correlate_attempts(
        [
            '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 1"}',
            '{"process":"CommCenter","message":"Resolved path: /x/CarrierLab.bundle"}',
        ]
    )
    status, observed = _status_for(attempts, "CarrierLab.bundle", timed_out=False)
    assert status == BindingStatus.OBSERVED
    assert observed == "CarrierLab.bundle"


def test_success_required_for_verified():
    attempts = correlate_attempts(
        [
            '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 1"}',
            '{"process":"CommCenter","message":"Resolved path: /x/CarrierLab.bundle"}',
            '{"process":"CommCenter","message":"kOverrideBundleSuccess"}',
        ]
    )
    status, _ = _status_for(attempts, "CarrierLab.bundle", timed_out=False)
    assert status == BindingStatus.VERIFIED


def test_timeout_status():
    status, _ = _status_for([], "CarrierLab.bundle", timed_out=True)
    assert status == BindingStatus.TIMEOUT
