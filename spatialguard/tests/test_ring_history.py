"""Ring Event History import, Smart Alerts vehicles, encrypted video and insight guardrails."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from spatialguard_api import analytics, demo, insights, tracks
from spatialguard_api.person_tracking import RecordingUnreadable
from spatialguard_api.ring_service import ENCRYPTED_VIDEO, configuration_summary, history_kind, history_time
from spatialguard_api.ring_worker import process_one
from test_ring_connection import Engine, mapped, service  # noqa: F401  (pytest fixture)


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat()


def signed(service, kind='motion_detected', sub_type='human', eid='event-x', at=None):
    at = at or datetime.now(timezone.utc)
    payload = {'meta': {'account_id': 'account-a', 'request_id': 'request-' + eid},
               'data': {'id': eid, 'type': kind, 'attributes': {
                   'source': 'device-a', 'timestamp': int(at.timestamp() * 1000), 'sub_type': sub_type}}}
    raw = json.dumps(payload).encode()
    key = service.provider.creds['hmac signature key'].encode()
    return raw, 'sha256=' + hmac.new(key, raw, hashlib.sha256).hexdigest()


def history_provider(service, events, extra_page=None):
    original = service.provider.api

    def api(token, path, method='GET', body=None):
        if path.startswith('/v1/history/devices/device-a/events'):
            service.provider.calls.append((path, method, body))
            if '?page=2' in path:
                return extra_page or {'data': []}
            return {'data': events, 'links': {'next': '/v1/history/devices/device-a/events?page=2' if extra_page
                                              else 'https://example.com/v1/elsewhere'}}
        return original(token, path, method, body)
    service.provider.api = api


def drain(service):
    while process_one(service, Engine()):
        pass


def test_history_types_and_times_are_read_defensively():
    assert history_kind('motion.human') == ('motion_detected', 'human')
    assert history_kind('motion') == ('motion_detected', '')
    assert history_kind('ding') == ('button_press', '')
    assert history_kind('live_view') == (None, None)
    moment = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    assert history_time(int(moment.timestamp() * 1000)) == moment
    assert history_time(str(int(moment.timestamp()))) == moment
    assert history_time('2026-10-18T12:00:00Z') == moment
    assert history_time('not a time') is None and history_time(None) is None


def test_event_history_import_queues_real_past_visits_once(service):
    mapped(service)
    now = datetime.now(timezone.utc)
    delivered_at = now - timedelta(hours=1)
    service.webhook(*signed(service, eid='live-1', at=delivered_at))
    history_provider(service, [
        {'id': 'h1', 'type': 'events', 'attributes': {'event_type': 'motion.human', 'start': iso(now - timedelta(hours=2))}},
        {'id': 'h2', 'type': 'events', 'attributes': {'event_type': 'ding', 'start': int((now - timedelta(hours=3)).timestamp() * 1000)}},
        # The webhook above already delivered this one.
        {'id': 'h3', 'type': 'events', 'attributes': {'event_type': 'motion.human', 'start': iso(delivered_at + timedelta(seconds=3))}},
        {'id': 'old', 'type': 'events', 'attributes': {'event_type': 'motion', 'start': iso(now - timedelta(days=9))}},
        {'id': 'lv', 'type': 'events', 'attributes': {'event_type': 'live_view', 'start': iso(now - timedelta(hours=4))}},
    ])
    result = service.import_history('owner')
    assert result['imported'] == 2 and result['cameras'][0]['found'] == 3
    # Links to other hosts are never followed.
    assert not any('elsewhere' in call[0] for call in service.provider.calls)
    assert service.import_history('owner')['imported'] == 0
    drain(service)
    with service.store.connect() as db:
        rows = [json.loads(r['data']) for r in db.execute('SELECT data FROM incidents')]
        queued = db.execute('SELECT count(*) FROM observation_tracks').fetchone()[0]
    explanations = [o['provenance']['explanation'] for i in rows for o in i['observations']]
    assert sum('Ring Event History' in text for text in explanations) == 2
    assert all(i['evidence_mode'] == 'live' for i in rows) and queued == len(rows)


def test_event_history_needs_a_paired_camera(service):
    from test_ring_connection import connect
    connect(service)
    with pytest.raises(HTTPException) as error:
        service.import_history('owner')
    assert error.value.status_code == 409


def test_event_history_follows_ring_pages(service):
    mapped(service)
    now = datetime.now(timezone.utc)
    history_provider(service, [{'id': 'p1', 'attributes': {'event_type': 'motion.human', 'start': iso(now - timedelta(hours=1))}}],
                     extra_page={'data': [{'id': 'p2', 'attributes': {'event_type': 'motion.vehicle', 'start': iso(now - timedelta(hours=5))}}]})
    assert service.import_history('owner')['imported'] == 2


def test_ring_vehicle_alert_is_counted_and_never_a_visit(service):
    mapped(service)
    service.webhook(*signed(service, sub_type='vehicle', eid='car-1'))
    service.webhook(*signed(service, sub_type='human', eid='person-1'))
    drain(service)
    with service.store.connect() as db:
        cars = [dict(r) for r in db.execute('SELECT * FROM vehicle_events')]
        incidents = db.execute('SELECT count(*) FROM incidents').fetchone()[0]
        analyzed = db.execute('SELECT count(*) FROM observation_tracks').fetchone()[0]
    assert len(cars) == 1 and cars[0]['camera_id'] == 'camera_front' and cars[0]['simulated'] == 0
    assert incidents == 1 and analyzed == 1  # only the person is a visit with a recording to analyze


def test_vehicle_analytics_compare_weeks_and_respect_live_only():
    now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
    site = {'id': 's', 'name': 'Café', 'layout': {'cameras': [{'id': 'lot', 'name': 'Parking lot'}], 'zones': [], 'rooms': []}}
    rows = [{'camera_id': 'lot', 'at': iso(now - timedelta(hours=h)), 'simulated': 0} for h in (1, 2, 2.5)]
    rows += [{'camera_id': 'lot', 'at': iso(now - timedelta(days=8)), 'simulated': 0}]
    rows += [{'camera_id': 'lot', 'at': iso(now - timedelta(hours=3)), 'simulated': 1}]
    everything = analytics.build(site, [], {}, 'UTC', now=now, vehicles=rows)['vehicles']
    assert everything['total'] == 4 and everything['previous'] == 1 and everything['simulated'] == 1
    assert everything['cameras'][0] == {'camera_id': 'lot', 'name': 'Parking lot', 'count': 4, 'previous': 1}
    assert everything['peak_hour'] == 15 and sum(everything['hourly']) == 4
    live = analytics.build(site, [], {}, 'UTC', now=now, vehicles=rows, mode='live')['vehicles']
    assert live['total'] == 3 and live['simulated'] == 1


def test_demo_cars_come_from_the_parking_camera_without_changing_customers():
    parking = [[0, 0], [10, 0], [10, 5], [0, 5]]
    site = {'id': 's', 'layout': {
        'zones': [{'name': 'Parking lot', 'purpose': analytics.ANALYTICS_PURPOSE, 'polygon_xy_m': parking}],
        'cameras': [{'id': 'lot', 'position_m': [5, -1], 'heading_degrees': 90, 'fov_degrees': 110, 'range_m': 12},
                    {'id': 'door', 'position_m': [5, 30], 'heading_degrees': 270, 'fov_degrees': 90, 'range_m': 4}]}}
    start = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    visits = [{'started_at': iso(start + timedelta(minutes=i))} for i in range(200)]
    cars = demo.vehicles(site, visits, seed=3)
    same = demo.vehicles(site, visits, seed=3)
    assert [(c['camera_id'], c['at']) for c in cars] == [(c['camera_id'], c['at']) for c in same]  # deterministic
    assert 60 < len(cars) < 120 and {c['camera_id'] for c in cars} == {'lot'}
    assert all(c['id'].startswith(demo.RUN_PREFIX) for c in cars)
    assert demo.vehicles({'id': 's', 'layout': {'zones': [], 'cameras': site['layout']['cameras']}}, visits) == []


def test_encrypted_camera_keeps_the_visit_and_never_reads_video(service, monkeypatch):
    assert configuration_summary({'e2e_encryption': {'enabled': True}, 'motion_detection': {'enabled': 'on'}})['video_encrypted']
    assert not configuration_summary({'e2e_encryption': {'enabled': False}, 'motion_detection': {'enabled': 'on'}})['video_encrypted']
    original = service.provider.api

    def api(token, path, method='GET', body=None):
        data = original(token, path, method, body)
        if path.startswith('/v1/devices?'):
            for item in data['included']:
                if item['type'] == 'device-configurations':
                    item['attributes']['e2e_encryption'] = {'enabled': True}
        return data
    service.provider.api = api
    mapped(service)
    device = service.devices('owner')[0]
    assert device['configuration']['video_encrypted'] and ENCRYPTED_VIDEO in device['guidance']
    service.webhook(*signed(service, eid='encrypted-1'))
    drain(service)
    fetched = []
    service.provider.clip = lambda *args: (fetched.append(1) or b'clip', {})
    monkeypatch.setattr(tracks, 'MODEL', type('M', (), {'is_file': lambda self: True})())
    with service.store.connect() as db:
        db.execute('UPDATE observation_tracks SET not_before=0')
    assert tracks.process_one(service, service.store) is True
    with service.store.connect() as db:
        state = db.execute('SELECT state FROM observation_tracks').fetchone()['state']
        incidents = db.execute('SELECT count(*) FROM incidents').fetchone()[0]
    assert state == 'encrypted' and incidents == 1 and not fetched


def test_undecodable_recording_is_not_reported_as_an_empty_scene(service, monkeypatch):
    from spatialguard_api import heatmap
    mapped(service)
    service.webhook(*signed(service, eid='garbled-1'))
    drain(service)
    service.provider.clip = lambda *args: (b'\x00\x00\x00\x18ftypisomgarbled', {})
    monkeypatch.setattr(tracks, 'MODEL', type('M', (), {'is_file': lambda self: True})())

    def unreadable(identity, path):
        raise RecordingUnreadable('no frame decoded')
    monkeypatch.setattr(tracks, 'track_video', unreadable)
    with service.store.connect() as db:
        db.execute('UPDATE observation_tracks SET not_before=0')
    assert tracks.process_one(service, service.store) is True
    with service.store.connect() as db:
        row = db.execute('SELECT incident_id, observation_id, state FROM observation_tracks').fetchone()
    assert row['state'] == 'unreadable'
    camera = {'id': 'camera_front', 'position_m': [0, 0], 'heading_degrees': 0, 'fov_degrees': 110, 'range_m': 6}
    kind, _ = heatmap.event_points({'id': row['incident_id']}, {'observation_id': row['observation_id']}, camera,
                                   {(row['incident_id'], row['observation_id']): {'state': 'unreadable', 'points': []}})
    assert kind == 'estimated'  # still counted as a visit


FACTS = {'visits': 412, 'visits_previous': 349, 'simulated_visits': 0, 'change_pct': 18.1, 'peak_hour': '12 PM',
         'average_visit_seconds': 262.0, 'average_visit_seconds_previous': 240.0,
         'daily': [{'date': '2026-10-18', 'visits': 72, 'same_day_previous_week': 61}],
         'busiest_hours': [{'hour': '12 PM', 'visits': 66, 'previous': 55}],
         'zones': [{'zone': 'Counter', 'visits': 264, 'previous': 220, 'average_dwell_seconds': 118.0,
                    'average_dwell_seconds_previous': 95.0}],
         'entrances': [], 'data_quality': {'tracked': 3, 'positioned': 400, 'estimated': 9}, 'layout_changes': []}
GOOD = {'headline': 'Visits up 18% to 412 this week',
        'summary': 'You had 412 visits, up from 349. The Counter saw 64% of visits and people stayed about '
                   '2 minutes (118 s, up from 95 s).',
        'highlights': [{'title': 'Lunch peak', 'detail': '12 PM had 66 visits.', 'trend': 'up'}],
        'recommendation': 'Open a second register at 12 PM.'}


def test_insight_guardrail_passes_grounded_notes_and_catches_invented_ones(monkeypatch):
    assert insights.check(GOOD, FACTS) == []
    invented = {**GOOD, 'headline': 'A record 999 visits'}
    assert any('999' in reason for reason in insights.check(invented, FACTS))
    about_people = {**GOOD, 'summary': 'Two women and a suspicious man waited at the Counter.'}
    reasons = insights.check(about_people, FACTS)
    assert any('women' in r for r in reasons) and any('suspicious' in r for r in reasons)
    assert any('simulated' in r for r in insights.check(GOOD, {**FACTS, 'simulated_visits': 120}))
    monkeypatch.setenv('PATHLIGHT_INSIGHT_BLOCKLIST', 'register')
    assert any("'register'" in r for r in insights.check(GOOD, FACTS))
    plain = insights.Insight.model_validate(insights.fallback({**FACTS, 'simulated_visits': 120}))
    assert '412' in plain.summary and 'simulated' in plain.summary and plain.recommendation


def test_a_failing_bedrock_note_is_replaced_by_the_plain_one(monkeypatch):
    import io
    monkeypatch.setattr(insights, '_settings', lambda: {'AWS_BEARER_TOKEN_BEDROCK': 'k', 'AWS_REGION': 'us-west-2',
                                                         'PATHLIGHT_INSIGHT_MODEL': insights.DEFAULT_MODEL})
    monkeypatch.setattr(insights, '_facts', lambda metrics: FACTS)
    note = {**GOOD, 'summary': 'A face we recognize visited 50 times.'}
    reply = {'output': {'message': {'content': [{'text': json.dumps(note)}]}}, 'usage': {}}
    monkeypatch.setattr(insights.urllib.request, 'urlopen', lambda request, timeout: io.BytesIO(json.dumps(reply).encode()))
    result = insights.generate({})
    assert result['checks']['fallback'] and not result['checks']['passed']
    assert 'face' not in result['summary'].lower() and '412' in result['summary']
    reply['output']['message']['content'][0]['text'] = json.dumps(GOOD)
    result = insights.generate({})
    assert result['checks'] == {'passed': True, 'fallback': False, 'reasons': []} and result['headline'] == GOOD['headline']
