#!/usr/bin/env python3
"""Independent LH1/LH4 source host: local evidence first, ordinal 1 only.

No import performs network, serial, camera or relay I/O.  The immutable source
consumption claim is shared by every package/output using the same white action.
An interrupted request is never retried and a claim is never removed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CLAIM_ROOT = ROOT / '.test-output/hardware/.mf1750_lh1_lh4_source_claims'
WHITE_CLAIM_ROOT = ROOT / '.test-output/hardware/.mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_claims'
WHITE_BIN = 'dc93c95a956eecf7d9cb753e5fb82ea16e5f2142694a8fcd22157481570d2de6'
WHITE_ELF = 'ff3793efde294bf981f3b1932799fdc574917fe33c0f1d15bf636367c5aba067'
WHITE_ACTION = '677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19'
WHITE_CAMPAIGN = 'EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1'
EVIDENCE_MAX_AGE_SECONDS = 900
REQUEST_TIMEOUT_SECONDS = 65
POLL_INITIAL_DELAY_SECONDS = 45
POLL_INTERVAL_SECONDS = 2
MAX_STATUS_POLLS = 90
HEX = re.compile(r'^[0-9a-f]{64}$')
NONCE = re.compile(r'^[0-9a-f]{16}$')


class RunnerError(RuntimeError):
    """Fail closed without replaying a request."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(value: dict) -> dict:
    value = deepcopy(value)
    value['integrity'] = {'algorithm': 'sha256-canonical-json-without-integrity',
                          'sha256': digest(canonical(value))}
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunnerError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse_json(data: bytes) -> dict:
    try:
        value = json.loads(data, object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               RunnerError('non-finite JSON: ' + value)))
    except (ValueError, UnicodeError) as exc:
        raise RunnerError('invalid JSON') from exc
    if not isinstance(value, dict):
        raise RunnerError('JSON object required')
    return value


def _regular(path: Path) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RunnerError('missing or unsafe file: ' + str(path))
    return path.read_bytes()


def file_binding(path: Path) -> dict:
    path = Path(path).resolve()
    payload = _regular(path)
    return {'path': str(path), 'bytes': len(payload), 'sha256': digest(payload)}


def read_bound(binding: dict) -> bytes:
    if not isinstance(binding, dict) or set(binding) != {'path', 'bytes', 'sha256'}:
        raise RunnerError('file binding must contain path/bytes/sha256')
    path = Path(binding['path'])
    if not path.is_absolute():
        path = ROOT / path
    payload = _regular(path)
    if type(binding['bytes']) is not int or len(payload) != binding['bytes'] or digest(payload) != binding['sha256']:
        raise RunnerError('file binding differs: ' + str(path))
    return payload


def verify_integrity(value: dict) -> None:
    body = deepcopy(value)
    integrity = body.pop('integrity', None)
    actual = digest(canonical(body))
    if not isinstance(integrity, dict):
        raise RunnerError('integrity missing')
    if integrity.get('algorithm') == 'sha256-canonical-json-without-integrity':
        good = integrity.get('sha256') == actual
    else:
        good = integrity.get('canonical_sha256') == actual and isinstance(integrity.get('scope'), str)
    if not good:
        raise RunnerError('canonical integrity differs')


def read_record(path: Path) -> dict:
    value = parse_json(_regular(path))
    verify_integrity(value)
    return value


def _require(value: dict, expected: dict, label: str) -> None:
    for key, wanted in expected.items():
        found = value.get(key)
        if type(found) is not type(wanted) or canonical(found) != canonical(wanted):
            raise RunnerError(f'{label} {key} differs')


def _string(source: str, name: str) -> str:
    match = re.search(r'\b' + re.escape(name) + r'\s*=\s*"((?:\\.|[^"\\])*)"\s*;', source)
    if not match:
        raise RunnerError('compiled string missing: ' + name)
    return json.loads('"' + match.group(1) + '"')


def validate_package(package: Path) -> dict:
    package = Path(package).resolve()
    manifest = read_record(package / 'manifest.json')
    build = read_record(package / 'build-report.json')
    contract = parse_json(_regular(package / 'contract.json'))
    contract_body = deepcopy(contract)
    contract_id = contract_body.pop('contract_id', None)
    if contract_id != digest(canonical(contract_body)):
        raise RunnerError('contract ID differs')
    if Path(build['manifest']['path']).resolve() != package / 'manifest.json':
        raise RunnerError('build report must bind this package manifest')
    for binding in manifest.get('inputs', []) + manifest.get('outputs', []):
        read_bound(binding)
    for binding in [build['manifest'], build['log']] + build['artifacts']:
        read_bound(binding)
    _require(build, {'result': 'PASS', 'contract_id': contract['contract_id'],
                     'hardware_accessed': False, 'firmware_flashed': False,
                     'compiled_actions': 3}, 'build')
    _require(manifest, {'contract_id': contract['contract_id']}, 'manifest')
    if len(contract.get('actions', [])) != 3:
        raise RunnerError('dedicated three-action contract required')
    _require(contract, {'action_count': 3, 'startup_refresh': False, 'autochain': False,
                        'retry': False, 'white_or_repeat_action': False,
                        'nvs': {'namespace': 'lhist_v1', 'cursor': 'cur_lh1', 'boot': 'boot_lh1'}}, 'contract')
    source = contract['source_white']
    _require(source, {'campaign_id': WHITE_CAMPAIGN, 'action_id': WHITE_ACTION,
                      'firmware_sha256': WHITE_BIN, 'firmware_elf_sha256': WHITE_ELF,
                      'nvs_namespace': 'p2catwsv1', 'nvs_key': 'used_p2cw1',
                      'complete_cursor': 2}, 'source white')
    for key in ('terminal_evidence', 'claim_evidence', 'clean_white_review'):
        read_bound(source.get(key))
    if 'binding_generator' in source:
        read_bound(source['binding_generator'])
    cfg_path = package / 'generated/ec5_lightness_history_v1_main_config.inc'
    # Contract, generated config and frame bytes must be actual manifest outputs.
    outputs = {Path(item['path']).resolve() for item in manifest['outputs']}
    for required in (package / 'contract.json', package / 'platformio.ini', cfg_path,
                     package / 'generated/ec5_lightness_history_v1_main.cpp',
                     package / 'generated/ec5_lightness_history_v1_driver.inc',
                     package / 'generated/ec5_lightness_history_v1_identity.inc',
                     package / 'generated/frozen_epd_driver.cpp.inc'):
        if required not in outputs:
            raise RunnerError('package output not sealed: ' + str(required))
    cfg = _regular(cfg_path).decode('utf-8')
    identity = {_name: _string(cfg, key) for _name, key in (
        ('build_tag', 'kBuildTag'), ('test_id', 'kTestId'),
        ('campaign_id', 'kCampaignId'), ('contract_id', 'kContractId'),
        ('device_api_version', 'kDeviceApiVersion'), ('identity_revision', 'kIdentityRevision'),
        ('compiled_identity_marker', 'kCompiledIdentityMarker'), ('classification', 'kClassification'))}
    if identity['contract_id'] != contract['contract_id']:
        raise RunnerError('compiled contract differs')
    artifacts = {Path(item['path']).suffix: item for item in build['artifacts']}
    if set(artifacts) != {'.bin', '.elf'}:
        raise RunnerError('exact BIN and ELF required')
    for artifact in artifacts.values():
        if not Path(artifact['path']).resolve().is_relative_to(package / 'build'):
            raise RunnerError('artifact is outside this package build')
        if read_bound(artifact).count(identity['compiled_identity_marker'].encode()) != 1:
            raise RunnerError('compiled marker count differs')
    for index, action in enumerate(contract['actions'], 1):
        if action['ordinal'] != index or action['global_header'] != ('commented' if index == 2 else 'active'):
            raise RunnerError('action order/tuple differs')
        frame = package / (action['stage'].lower() + '.frame4bpp')
        if frame not in outputs or digest(_regular(frame)) != action['frame']['sha256']:
            raise RunnerError('sealed frame differs')
        for key in ('action_id', 'descriptor_id'):
            if not HEX.fullmatch(action[key]) or action[key] not in cfg:
                raise RunnerError('compiled action differs')
    return {'package': package, 'contract': contract, 'identity': identity,
            'firmware': artifacts['.bin'], 'elf': artifacts['.elf'],
            'routes': {suffix: _string(cfg, 'k' + suffix.capitalize() + 'Route')
                       for suffix in ('version', 'manifest', 'status', 'report', 'arm', 'execute')},
            'arm_intent': _string(cfg, 'kArmIntent'), 'execute_intent': _string(cfg, 'kExecuteIntent'),
            'source': source, 'build_binding': file_binding(package / 'build-report.json')}


def origin(value: str) -> str:
    parts = urlsplit(value)
    try:
        address = ipaddress.IPv4Address(parts.hostname or '')
        private = any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
        port = parts.port
    except ValueError as exc:
        raise RunnerError('literal private HTTP IPv4 required') from exc
    if not private or parts.scheme != 'http' or parts.username or parts.password or port not in (None, 80) or parts.path not in ('', '/') or parts.query or parts.fragment:
        raise RunnerError('literal private HTTP/80 origin required')
    return 'http://' + str(address)


def _fresh(value: str, now: datetime) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        age = (now - timestamp).total_seconds()
    except (TypeError, ValueError, AttributeError) as exc:
        raise RunnerError('timezone-aware evidence timestamp required') from exc
    if timestamp.tzinfo is None or not 0 <= age <= EVIDENCE_MAX_AGE_SECONDS:
        raise RunnerError('evidence expired or future-dated')
    return timestamp


def claim_path(ctx: dict) -> Path:
    source = ctx['source']
    key = digest(('MF1750_LH1_SOURCE_CONSUMPTION_V1|' + source['campaign_id'] + '|' + source['action_id']).encode())
    return CLAIM_ROOT / (key + '.json')


def validate_ipv4_mac_raw(binding: dict, base_url: str, now: datetime) -> None:
    value = parse_json(read_bound(binding))
    verify_integrity(value)
    address = urlsplit(base_url).hostname
    _require(value, {'kind': 'mf1750-exact-ipv4-mac-binding-attempt-v1',
        'candidate_ipv4': address, 'expected_mac': 'A4-CB-8F-D9-FC-D4',
        'candidate_count': 1, 'single_candidate_confirmed': True, 'active_probe_authorized': True,
        'binding_passed': True, 'fresh_binding_passed': True, 'device_application_identity_proven': False,
        'network_layer_mac_binding_observed': True, 'device_api_requests': 0, 'http_requests': 0,
        'mutation_requests': 0, 'visible_refresh_requests': 0, 'retry': False, 'scan': False,
        'fallback': False, 'outcome': 'active_exact_mac_binding_pass',
        'output_contract': 'O_EXCL_TERMINAL'}, 'raw IPv4/MAC')
    _fresh(value.get('finished_at'), now)
    bound_path = Path(binding['path'])
    if not bound_path.is_absolute():
        bound_path = ROOT / bound_path
    if Path(value.get('output_file', '')).resolve() != bound_path.resolve():
        raise RunnerError('raw IPv4/MAC output path differs')
    probe = value.get('active_probe', {})
    _require(probe, {'attempts': 1, 'kind': 'one_icmp_echo_to_exact_literal_ipv4', 'returncode': 0}, 'exact ICMP probe')
    for name in ('stdout', 'stderr'):
        text = probe.get(name + '_utf8')
        if not isinstance(text, str) or len(text.encode()) != probe.get(name + '_bytes') or digest(text.encode()) != probe.get(name + '_sha256'):
            raise RunnerError('ICMP raw byte binding differs')
    if address not in probe['stdout_utf8']:
        raise RunnerError('probe does not mention exact candidate')
    neighbours = value.get('neighbour_entries')
    if not isinstance(neighbours, list) or len(neighbours) != 1:
        raise RunnerError('one exact neighbour required')
    neighbour = neighbours[0]
    _require(neighbour, {'IPAddress': address, 'LinkLayerAddress': 'A4-CB-8F-D9-FC-D4'}, 'neighbour')
    local_match = False
    for row in value.get('local_ipv4', []):
        try:
            interface = ipaddress.IPv4Interface(f"{row['IPAddress']}/{row['PrefixLength']}")
            local_match |= row['InterfaceIndex'] == neighbour['ifIndex'] and ipaddress.IPv4Address(address) in interface.network
        except (ValueError, KeyError, TypeError):
            continue
    if not local_match:
        raise RunnerError('neighbour has no matching local interface/subnet')


def _source_evidence(ctx: dict) -> dict:
    source = ctx['source']
    terminal = parse_json(read_bound(source['terminal_evidence']))
    claim = parse_json(read_bound(source['claim_evidence']))
    review = parse_json(read_bound(source['clean_white_review']))
    for value in (terminal, claim, review):
        verify_integrity(value)
    expected_claim = WHITE_CLAIM_ROOT / (source['action_id'] + '.json')
    if Path(source['claim_evidence']['path']).resolve() != expected_claim.resolve():
        raise RunnerError('white source must bind original permanent claim')
    for value in (terminal, claim):
        _require(value, {'firmware_sha256': WHITE_BIN, 'running_app_elf_sha256': WHITE_ELF}, 'source artifact')
        if value.get('action', {}).get('action_id') != source['action_id']:
            raise RunnerError('white source action differs')
    _require(terminal, {'outcome': 'complete_pass', 'claim_state': 'permanently_consumed_by_this_invocation'}, 'white terminal')
    if Path(terminal['claim_file']).resolve() != expected_claim.resolve() or terminal.get('boot_nonce') != claim.get('boot_nonce'):
        raise RunnerError('white claim/terminal boot differs')
    _require(claim, {'state': 'permanently_claimed_after_j2_on_preflight_before_first_arm'}, 'white claim')
    report = terminal.get('terminal_report', {})
    _require(report, {'valid': True, 'result': True, 'terminal_state': 'COMPLETE',
                      'action_id': WHITE_ACTION, 'driver_call_count_for_action': 1,
                      'total_driver_call_count': 1}, 'white terminal report')
    _require(terminal, {'visible_refreshes': 1}, 'white refresh count')
    _require(report.get('driver', {}), {'valid': True, 'sequence_ok': True, 'running': False,
              'wait_timeout': False, 'failure_code': 0, 'pon_busy_seen': True,
              'drf_busy_seen': True, 'pof_busy_seen': True}, 'white driver')
    if terminal.get('action') != claim.get('action'):
        raise RunnerError('white action/claim descriptors differ')
    # Historical audit HOLD is legitimate offline evidence, never live admission.
    _require(review.get('judgement', {}), {'protocol_and_artifact_identity': 'PASS',
              'historical_white_terminal_usable_for_offline_source_binding': 'PASS',
              'live_authorization_granted_by_audit': False}, 'historical source audit')
    _require(review.get('white_terminal', {}), {'action_id': WHITE_ACTION,
              'firmware_bin_sha256': WHITE_BIN, 'firmware_elf_sha256': WHITE_ELF}, 'historical white')
    return review


def validate_evidence(ctx: dict, evidence_path: Path, base_url: str, *, phase: str = 'off', now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    base_url = origin(base_url)
    _source_evidence(ctx)
    if claim_path(ctx).exists():
        raise RunnerError('white source already permanently claimed for LH1')
    evidence = read_record(evidence_path)
    _require(evidence, {'kind': 'mf1750-lh1-lh4-field-evidence-v1', 'contract_id': ctx['contract']['contract_id'],
                        'base_url': base_url}, 'field evidence')
    _fresh(evidence.get('recorded_at'), now)
    boot = evidence.get('boot_nonce')
    boot_valid = (phase == 'off' and boot is None) or (isinstance(boot, str) and NONCE.fullmatch(boot))
    if not boot_valid or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', evidence.get('run_id', '')):
        raise RunnerError('run/boot identity missing')
    bound = {}
    for key in ('current_white_review', 'ipv4_mac_binding', 'app_flash_record', 'external_electrical', 'user_release', 'relay_off') + (('relay_on',) if phase == 'on' else ()):
        value = parse_json(read_bound(evidence.get(key)))
        verify_integrity(value)
        # The user's exact authorization persists; it is not a 15-minute lease.
        if key != 'user_release':
            _fresh(value.get('recorded_at'), now)
        bound[key] = value
    current = bound['current_white_review']
    if evidence.get('source_review_sha256') != evidence['current_white_review']['sha256']:
        raise RunnerError('review header must bind current white review, not historical HOLD audit')
    _require(current, {'kind': 'mf1750-lh1-current-white-review-v1', 'verdict': 'PASS',
              'source_action_id': WHITE_ACTION, 'source_firmware_sha256': WHITE_BIN,
              'full_panel_camera_coverage': True, 'all_four_edges_visible': True,
              'camera_usb_id': 'VID_32E4:PID_4801', 'no_intervening_visible_refresh': True}, 'current white review')
    if not current.get('reviewer') or not current.get('human_observation'):
        raise RunnerError('actual current human white observation required')
    if current.get('source_terminal') != ctx['source']['terminal_evidence'] or current.get('source_claim') != ctx['source']['claim_evidence']:
        raise RunnerError('current review must bind original white terminal and permanent claim')
    read_bound(current.get('photo'))
    sidecar = parse_json(read_bound(current.get('capture_sidecar')))
    verify_integrity(sidecar)
    if sidecar.get('kind') == 'mf1750-lh1-camera-capture':
        _require(sidecar, {'stage': 'CURRENT_CAMERA_OBSERVATION', 'output_write_contract': 'O_EXCL'}, 'current capture')
        anchor = sidecar.get('historical_action_anchor', {})
        anchor_binding = {'path': anchor.get('path'), 'bytes': anchor.get('bytes'), 'sha256': anchor.get('file_sha256')}
        anchor_value = parse_json(read_bound(anchor_binding))
        verify_integrity(anchor_value)
        if Path(anchor_binding['path']).resolve() != Path(ctx['source']['terminal_evidence']['path']).resolve() or anchor_binding['sha256'] != ctx['source']['terminal_evidence']['sha256']:
            raise RunnerError('camera anchor must bind actual original white terminal')
        anchor_body = {key: item for key, item in anchor_value.items() if key != 'integrity'}
        if anchor.get('canonical_sha256') != digest(canonical(anchor_body)):
            raise RunnerError('camera anchor canonical hash differs')
        _require(anchor_value, {'firmware_sha256': WHITE_BIN, 'running_app_elf_sha256': WHITE_ELF}, 'capture historical white')
        if anchor_value.get('action', {}).get('action_id') != WHITE_ACTION:
            raise RunnerError('camera historical anchor is not white action')
        camera = sidecar.get('camera', {})
        _require(camera, {'usb_vid': '32E4', 'usb_pid': '4801'}, 'camera USB')
        before, after = camera.get('authenticated_before'), camera.get('authenticated_after')
        if not isinstance(before, dict) or before != after:
            raise RunnerError('camera authenticated identity changed or absent')
        _require(before, {'usb_vid': '32E4', 'usb_pid': '4801'}, 'authenticated camera')
        for key in ('pnp_instance_id', 'alternative_name'):
            if not before.get(key):
                raise RunnerError('authenticated camera device binding absent')
        photo = sidecar.get('photo', {})
        _require(photo, {'sha256': current['photo']['sha256'], 'bytes': current['photo']['bytes']}, 'capture photo')
        if Path(photo.get('path', '')).resolve() != Path(current['photo']['path']).resolve():
            raise RunnerError('current photo path differs')
        _fresh(sidecar.get('capture_timing', {}).get('frame_retrieved_at_utc'), now)
        # UNKNOWN sidecar coverage is resolved only by the independent current
        # review above, never by the capture request's requested coverage scope.
    else:
        _require(sidecar, {'firmware_sha256': WHITE_BIN, 'action_id': WHITE_ACTION}, 'current white capture')
        if sidecar.get('image_sha256') != current['photo']['sha256']:
            raise RunnerError('current photo/sidecar differs')
    successor = parse_json(read_bound(evidence.get('post_test_successor')))
    verify_integrity(successor)
    _require(successor, {'kind': 'mf1750-lh1-source-post-test-white-seal-v1', 'result': 'PASS',
              'source_contract_id': ctx['contract']['contract_id'], 'accepted_source_ordinals': [1],
              'live_action_authorized': False}, 'post-test white successor')
    read_bound(successor.get('firmware'))
    read_bound(successor.get('elf'))
    if successor.get('source_action_id') != ctx['contract']['actions'][0]['action_id']:
        raise RunnerError('post-test successor source action differs')
    successor_build = parse_json(read_bound(successor.get('build_report')))
    successor_review = parse_json(read_bound(successor.get('independent_review')))
    for item in (successor_build, successor_review):
        verify_integrity(item)
        _require(item, {'result': 'PASS', 'contract_id': successor.get('contract_id')}, 'successor verification')
    if successor_build.get('artifacts') != [successor['firmware'], successor['elf']]:
        raise RunnerError('post-test successor build artifacts differ')
    if not successor_review.get('test_evidence'):
        raise RunnerError('independent successor test evidence missing')
    for item in successor_review['test_evidence']:
        read_bound(item)
    applicability = parse_json(read_bound(evidence.get('profile_applicability_review')))
    verify_integrity(applicability)
    a = ctx['contract']['actions'][0]
    _require(applicability, {'verdict': 'PASS', 'profile_id': a['profile_id'],
              'profile_sha256': a['profile_sha256'], 'unresolved_applicability_questions': []}, 'PWR/PLL/OTP applicability')
    if not applicability.get('reviewer') or not applicability.get('mode_applicability_reasoning') or not applicability.get('reference_documents'):
        raise RunnerError('evidence-backed PWR/PLL/OTP applicability review required')
    for item in applicability['reference_documents']:
        read_bound(item)
    ip = bound['ipv4_mac_binding']
    _require(ip, {'base_url': base_url, 'candidate_ipv4': urlsplit(base_url).hostname,
                  'expected_mac': 'A4-CB-8F-D9-FC-D4', 'fresh_binding_passed': True,
                  'device_api_requests': 0, 'mutation_requests': 0,
                  'visible_refresh_requests': 0, 'outcome': 'active_exact_mac_binding_pass'}, 'IPv4/MAC')
    if not ip.get('raw_evidence'):
        raise RunnerError('IPv4/MAC raw evidence missing')
    validate_ipv4_mac_raw(ip['raw_evidence'], base_url, now)
    flash = bound['app_flash_record']
    _require(flash, {'offset': '0x10000', 'app_only': True, 'verify_result': 'PASS',
                     'firmware_sha256': ctx['firmware']['sha256'],
                     'running_app_elf_sha256': ctx['elf']['sha256'], 'nvs_written': False}, 'flash')
    if flash.get('post_flash_boot_nonce') not in (None, evidence['boot_nonce']):
        raise RunnerError('flash receipt boot differs')
    read_bound(flash.get('raw_evidence'))
    electrical = bound['external_electrical']
    for key in ('instrument', 'ground_reference', 'operator', 'acceptance_basis'):
        if not isinstance(electrical.get(key), str) or not electrical[key].strip():
            raise RunnerError('external measurement missing: ' + key)
    readings = electrical.get('readings')
    if not isinstance(readings, list) or not readings:
        raise RunnerError('actual external electrical readings required')
    for reading in readings:
        if not isinstance(reading, dict) or not reading.get('point') or not reading.get('unit') or type(reading.get('value')) not in (int, float) or not math.isfinite(reading['value']):
            raise RunnerError('actual numeric measurement missing')
        _fresh(reading.get('recorded_at'), now)
    _require(electrical, {'verdict': 'PASS', 'boot_nonce': evidence['boot_nonce'],
                         'phase': phase, 'external_measurement': True}, 'external electrical')
    _require(electrical, {'run_id': evidence['run_id'], 'app_flash_record': evidence['app_flash_record']}, 'electrical session')
    release = bound['user_release']
    _require(release, {'contract_id': ctx['contract']['contract_id'], 'action_id': ctx['contract']['actions'][0]['action_id'],
                       'ordinal': 1, 'run_id': evidence['run_id'], 'release': 'SOURCE_ONCE_THEN_STOP'}, 'user release')
    if not release.get('operator') or not release.get('actual_user_instruction'):
        raise RunnerError('actual user release evidence required')
    for key in ('relay_off',) + (('relay_on',) if phase == 'on' else ()):
        relay = bound[key]
        _require(relay, {'commanded_state': 'ON' if key == 'relay_on' else 'OFF',
                         'independently_queried': True, 'channel': 1,
                         'run_id': evidence['run_id'], 'app_flash_record': evidence['app_flash_record']}, key)
        allowed_boots = (None, evidence['boot_nonce']) if key == 'relay_off' else (evidence['boot_nonce'],)
        if relay.get('boot_nonce') not in allowed_boots:
            raise RunnerError('relay session boot differs')
        if not relay.get('pnp_instance') or not relay.get('usb_location'):
            raise RunnerError('exact relay physical binding required')
        read_bound(relay.get('raw_evidence'))
    return evidence


def evidence_template(ctx: dict) -> dict:
    """Unfilled records only; output is not sealed or admissible field evidence."""
    binding = {'path': None, 'bytes': None, 'sha256': None}
    field = {'kind': 'mf1750-lh1-lh4-field-evidence-v1', 'recorded_at': None,
             'contract_id': ctx['contract']['contract_id'], 'run_id': None, 'boot_nonce': None,
             'base_url': None, 'source_review_sha256': None}
    for key in ('current_white_review', 'ipv4_mac_binding', 'app_flash_record',
                'external_electrical', 'user_release', 'relay_off', 'relay_on',
                'post_test_successor', 'profile_applicability_review'):
        field[key] = deepcopy(binding)
    return {'status': 'UNFILLED_NOT_AUTHORIZATION', 'field_evidence': field,
            'external_electrical_record': {'recorded_at': None, 'instrument': None,
                'ground_reference': None, 'operator': None, 'acceptance_basis': None,
                'readings': [{'point': None, 'value': None, 'unit': None, 'recorded_at': None}],
                'verdict': None, 'boot_nonce': None, 'run_id': None,
                'app_flash_record': deepcopy(binding), 'phase': None, 'external_measurement': None},
            'user_release_record': {'recorded_at': None, 'original_instruction_at': None,
                'operator': None, 'actual_user_instruction': None,
                'contract_id': ctx['contract']['contract_id'], 'action_id': ctx['contract']['actions'][0]['action_id'],
                'ordinal': 1, 'run_id': None, 'release': 'SOURCE_ONCE_THEN_STOP'},
            'required_record_schemas': {
                'current_white_review': ['recorded_at', 'kind', 'verdict', 'source_action_id',
                    'source_firmware_sha256', 'full_panel_camera_coverage', 'all_four_edges_visible',
                    'camera_usb_id', 'no_intervening_visible_refresh', 'reviewer', 'human_observation',
                    'source_terminal', 'source_claim', 'photo', 'capture_sidecar'],
                'ipv4_mac_binding': ['recorded_at', 'base_url', 'candidate_ipv4', 'expected_mac',
                    'fresh_binding_passed', 'device_api_requests', 'mutation_requests',
                    'visible_refresh_requests', 'outcome', 'raw_evidence'],
                'app_flash_record': ['recorded_at', 'offset', 'app_only', 'verify_result',
                    'firmware_sha256', 'running_app_elf_sha256', 'post_flash_boot_nonce', 'nvs_written', 'raw_evidence'],
                'relay_off_and_on': ['recorded_at', 'commanded_state', 'independently_queried',
                    'channel', 'boot_nonce', 'run_id', 'app_flash_record', 'pnp_instance', 'usb_location', 'raw_evidence'],
                'post_test_successor': ['kind', 'result', 'contract_id', 'source_contract_id',
                    'source_action_id', 'accepted_source_ordinals', 'live_action_authorized',
                    'firmware', 'elf', 'build_report', 'independent_review'],
                'profile_applicability_review': ['verdict', 'profile_id', 'profile_sha256',
                    'reviewer', 'mode_applicability_reasoning', 'reference_documents', 'unresolved_applicability_questions']},
            'running_elf_evidence_limit': 'R1 HTTP does not report running ELF SHA; bind sealed app-only write/verify and new boot. No independent device ELF self-report claimed.',
            'record_sealing': 'Each referenced JSON record requires canonical integrity; every file ref uses path/bytes/sha256. Unknown actual facts remain null.'}


def expected_action(ctx: dict, index: int = 0) -> dict:
    a = ctx['contract']['actions'][index]
    return {'ordinal': a['ordinal'], 'descriptor_id': a['descriptor_id'], 'action_id': a['action_id'],
            'role': a['role'], 'round': 1, 'branch': a['branch'],
            'controller_tuple_dispatch': 'CC' if index == 1 else 'AA',
            'cs1_profile': a['profile']['cs1'], 'cs2_profile': a['profile']['cs2'],
            'driver_entry': 'epdDisplayCompiledChromaGrid', 'global_header': a['global_header'],
            'palette_source': 'L535_RUNTIME', 'profile_id': a['profile_id'],
            'profile_sha256': a['profile_sha256'], 'source_state': a['source_state'], 'target_state': a['target_state']}


def _identity(ctx: dict, value: dict, evidence: dict, *, latched: bool = False) -> None:
    _require(value, ctx['identity'], 'device identity')
    _require(value, {'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
                     'source_nvs_complete': True, 'review_digests_are_host_assertions_only': True,
                     'run_id': evidence['run_id'] if latched else '',
                     'source_review_sha256': evidence['source_review_sha256'] if latched else '',
                     'prior_review_sha256': evidence['source_review_sha256'] if latched else ''}, 'device review')
    if 'boot_nonce' in value and value['boot_nonce'] != evidence['boot_nonce']:
        raise RunnerError('device boot changed')
    if 'running_app_elf_sha256' in value and value['running_app_elf_sha256'] != ctx['elf']['sha256']:
        raise RunnerError('running ELF differs')


def _nvs(value: dict) -> None:
    _require(value.get('nvs_contract', {}), {'namespace': 'lhist_v1', 'key': 'cur_lh1',
             'campaign_boot_key': 'boot_lh1', 'current_boot_exact_match_required': True,
             'reboot_resume_allowed': False, 'post_containment_resume_allowed': False,
             'initial_next_ordinal': 1, 'terminal_next_ordinal': 4}, 'NVS')


def validate_four_get(ctx: dict, values: dict, evidence: dict, *, busy: int) -> None:
    for name, value in values.items():
        _identity(ctx, value, evidence)
        _require(value, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-' + name}, name)
    for name in ('version', 'manifest'):
        value = values[name]
        _require(value, {'action_count': 3, 'automatic_chaining': False, 'startup_refresh': False,
                         'raw_frame_ingress': False, 'runtime_lut_write': True,
                         'caller_electrical_parameter_write': False, 'fixed_profile_parameter_write': True,
                         'dither': False, 'spatial_mixing': False, 'retry': False, 'recovery': False,
                         'layout_id': 'LH1_HISTORY_POSITION_BALANCED_8X8',
                         'profile_source': 'complete_symmetric_L535_active_commented_tuples',
                         'partial_refresh': False, 'full_screen_global_refresh': True,
                         'lightness_qualification': False, 'local_hold_claimed': False,
                         'identical_target_repeat': False, 'device_enforced_same_boot': True,
                         'main_campaign_resume_after_containment': False}, name)
        _nvs(value)
    _require(values['version'], {'automatic_execute': False, 'driver_api_version': 'MF1750_R16_CASCADE_V3'}, 'version')
    _require(values['manifest'], {'one_driver_call_per_action': True, 'synchronous_both_controllers': True,
               'round_count': 1, 'factory_otp': False, 'custom_lut_or_waveform': True}, 'manifest')
    actions = values['manifest'].get('actions')
    if not isinstance(actions, list) or len(actions) != 3:
        raise RunnerError('manifest action count differs')
    for index, action in enumerate(actions):
        a = ctx['contract']['actions'][index]
        _require(action, expected_action(ctx, index), 'manifest action')
        _require(action, {'frame_sha256': a['frame']['sha256'], 'cs1_dtm_sha256': a['cs1_dtm']['sha256'],
                         'cs2_dtm_sha256': a['cs2_dtm']['sha256'], 'transport_code_histogram': a['frame']['histogram'],
                         'prior_static_action_id': a['prior_action_id']}, 'manifest frame')
    status = values['status']
    _require(status, {'boot_nonce': evidence['boot_nonce'], 'state': 'ready', 'phase': 0, 'phase_name': 'READY',
                      'cursor_raw': 1, 'next_ordinal': 1, 'current_action': None,
                      'campaign_complete': False, 'fixture_self_check_passed': True, 'cursor_valid': True,
                      'persistent_key_present': False, 'campaign_boot_key_present': True,
                      'persisted_campaign_boot_nonce': evidence['boot_nonce'], 'campaign_boot_matches_current': True,
                      'execute_pending': False, 'arm_request_count': 0, 'execute_request_count': 0,
                      'total_driver_call_count': 0, 'gpio_initialized': True, 'busy': busy}, 'fresh status')
    _nvs(status)
    _require(values['report'], {'boot_nonce': evidence['boot_nonce'], 'valid': False, 'terminal_state': 'NOT_EXECUTED',
                               'ordinal': None, 'action_id': None, 'result': False, 'driver_called': False,
                               'driver_call_count_for_action': 0, 'total_driver_call_count': 0,
                               'phase': 0, 'next_ordinal': 1}, 'fresh report')


def _http(method: str, url: str, headers: dict, timeout: int) -> tuple[int, bytes]:
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, 80, timeout=timeout)
    try:
        conn.request(method, parts.path, body=None, headers={'Connection': 'close', **headers})
        response = conn.getresponse()
        payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise RunnerError('HTTP response too large')
        return response.status, payload
    finally:
        conn.close()


def write_new(path: Path, value: dict | bytes) -> None:
    payload = canonical(value) + b'\n' if isinstance(value, dict) else value
    with Path(path).open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


class Session:
    def __init__(self, ctx: dict, evidence: dict, output: Path, base_url: str, transport: Callable | None):
        self.ctx, self.evidence, self.base_url = ctx, deepcopy(evidence), origin(base_url)
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.transport = transport or _http
        self.counts = {'get': 0, 'post': 0}
        self.index = 0

    def request(self, method: str, route: str, expected_status: int, headers: dict | None = None) -> dict:
        self.index += 1
        self.counts[method.lower()] += 1
        started = datetime.now(timezone.utc).isoformat()
        metadata = {'method': method, 'url': self.base_url + self.ctx['routes'][route],
                    'headers': headers or {}, 'started_at': started, 'request_body_bytes': 0}
        stem = f'{self.index:03d}-{method.lower()}-{route}'
        try:
            status, raw = self.transport(method, metadata['url'], headers or {}, REQUEST_TIMEOUT_SECONDS)
            if not isinstance(raw, bytes):
                raise RunnerError('transport must return original response bytes')
            write_new(self.output / (stem + '.body.bin'), raw)
            metadata.update(status=status, finished_at=datetime.now(timezone.utc).isoformat(),
                            response_body=file_binding(self.output / (stem + '.body.bin')))
            write_new(self.output / (stem + '.json'), seal(metadata))
        except Exception as exc:
            error_path = self.output / (stem + '.error.json')
            write_new(error_path, seal({**metadata, 'finished_at': datetime.now(timezone.utc).isoformat(),
                                      'error': type(exc).__name__, 'no_retry': True}))
            raise RunnerError('request failed; do not retry: ' + route) from exc
        if type(status) is not int or status != expected_status:
            raise RunnerError(f'{route} HTTP {status}; expected {expected_status}; do not retry')
        return parse_json(raw)

    def four_get(self, busy: int) -> dict:
        values = {name: self.request('GET', name, 200) for name in ('version', 'manifest', 'status', 'report')}
        if busy == 0 and self.evidence['boot_nonce'] is None:
            boot = values['status'].get('boot_nonce')
            if not isinstance(boot, str) or not NONCE.fullmatch(boot) or values['report'].get('boot_nonce') != boot:
                raise RunnerError('four-GET first boot binding differs between status and report')
            self.evidence['boot_nonce'] = boot
        validate_four_get(self.ctx, values, self.evidence, busy=busy)
        return values


def diagnose(package: Path, evidence_path: Path, output: Path, base_url: str, transport: Callable | None = None) -> dict:
    ctx = validate_package(package)
    evidence = validate_evidence(ctx, evidence_path, base_url, phase='off')
    session = Session(ctx, evidence, output, base_url, transport)
    values = session.four_get(0)
    evidence = session.evidence
    result = seal({'kind': 'mf1750-lh1-lh4-j2-off-diagnostic-v1', 'result': 'PASS',
                   'recorded_at': datetime.now(timezone.utc).isoformat(), 'contract_id': ctx['contract']['contract_id'],
                   'package_build': ctx['build_binding'], 'firmware': ctx['firmware'], 'elf': ctx['elf'],
                   'base_url': origin(base_url), 'boot_nonce': evidence['boot_nonce'], 'run_id': evidence['run_id'],
                   'source_review_sha256': evidence['source_review_sha256'], 'evidence': file_binding(evidence_path),
                   'network': session.counts, 'busy': 0, 'driver_calls': 0, 'visible_refreshes': 0,
                   'claim_created': False, 'responses': values,
                   'transcripts': [file_binding(p) for p in sorted(session.output.glob('*')) if p.is_file()]})
    write_new(session.output / 'diagnostic.json', result)
    return result


def _diagnostic(ctx: dict, evidence: dict, path: Path, base_url: str) -> dict:
    value = read_record(path)
    _fresh(value.get('recorded_at'), datetime.now(timezone.utc))
    _require(value, {'kind': 'mf1750-lh1-lh4-j2-off-diagnostic-v1', 'result': 'PASS',
                     'contract_id': ctx['contract']['contract_id'], 'package_build': ctx['build_binding'],
                     'firmware': ctx['firmware'], 'elf': ctx['elf'], 'base_url': origin(base_url),
                     'boot_nonce': evidence['boot_nonce'], 'run_id': evidence['run_id'],
                     'source_review_sha256': evidence['source_review_sha256'],
                     'network': {'get': 4, 'post': 0}, 'busy': 0, 'driver_calls': 0,
                     'visible_refreshes': 0, 'claim_created': False}, 'diagnostic')
    off_evidence = parse_json(read_bound(value['evidence']))
    verify_integrity(off_evidence)
    for key in ('run_id', 'source_review_sha256', 'app_flash_record', 'current_white_review'):
        if off_evidence.get(key) != evidence.get(key):
            raise RunnerError('on evidence changed diagnostic session binding: ' + key)
    transcripts = value.get('transcripts', [])
    if len(transcripts) != 8:
        raise RunnerError('diagnostic must bind four exact body/metadata pairs')
    for binding in transcripts:
        read_bound(binding)
    by_name = {Path(binding['path']).name: binding for binding in transcripts}
    for index, route in enumerate(('version', 'manifest', 'status', 'report'), 1):
        stem = f'{index:03d}-get-{route}'
        raw = read_bound(by_name[stem + '.body.bin'])
        metadata = parse_json(read_bound(by_name[stem + '.json']))
        verify_integrity(metadata)
        _require(metadata, {'method': 'GET', 'url': origin(base_url) + ctx['routes'][route],
                           'status': 200, 'request_body_bytes': 0, 'headers': {},
                           'response_body': by_name[stem + '.body.bin']}, 'diagnostic raw transcript')
        if parse_json(raw) != value['responses'][route]:
            raise RunnerError('diagnostic parsed response differs from original bytes')
    validate_four_get(ctx, value['responses'], evidence, busy=0)
    return value


def mutation_headers(ctx: dict, evidence: dict, *, arm_nonce: str | None = None) -> dict:
    action = ctx['contract']['actions'][0]
    headers = {'X-EC5-Build-Tag': ctx['identity']['build_tag'], 'X-EC5-Test-Id': ctx['identity']['test_id'],
               'X-EC5-Campaign-Id': ctx['identity']['campaign_id'], 'X-EC5-Action-Id': action['action_id'],
               'X-EC5-Ordinal': '1', 'X-EC5-Descriptor-Id': action['descriptor_id'],
               'X-EC5-Boot-Nonce': evidence['boot_nonce'],
               'X-EC5-Intent': ctx['execute_intent'] if arm_nonce else ctx['arm_intent'],
               'X-LH-Run-Id': evidence['run_id'], 'X-LH-Source-Review': evidence['source_review_sha256'],
               'X-LH-Prior-Review': evidence['source_review_sha256']}
    if arm_nonce:
        headers['X-EC5-Arm-Nonce'] = arm_nonce
    return headers


def validate_terminal(ctx: dict, value: dict, status: dict, evidence: dict) -> None:
    _identity(ctx, value, evidence, latched=True)
    _identity(ctx, status, evidence, latched=True)
    _require(value, expected_action(ctx), 'terminal action/profile')
    _require(value, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-report',
                     'boot_nonce': evidence['boot_nonce'], 'valid': True, 'terminal_state': 'COMPLETE',
                     'result': True, 'driver_called': True, 'driver_call_count_for_action': 1,
                     'total_driver_call_count': 1, 'job_id': 1, 'phase': 0, 'phase_name': 'READY',
                     'next_ordinal': 2, 'campaign_complete': False, 'no_retry': True, 'no_recovery': True}, 'terminal')
    _require(status, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-status',
                      'boot_nonce': evidence['boot_nonce'], 'state': 'ready', 'phase': 0, 'phase_name': 'READY',
                      'cursor_raw': 2, 'next_ordinal': 2, 'arm_request_count': 1, 'execute_request_count': 1,
                      'total_driver_call_count': 1, 'execute_pending': False, 'current_action': None,
                      'cursor_valid': True, 'persistent_key_present': True, 'campaign_boot_matches_current': True,
                      'persisted_campaign_boot_nonce': evidence['boot_nonce']}, 'terminal status')
    driver = value.get('driver', {})
    a = ctx['contract']['actions'][0]
    _require(driver, {'driver_evidence_schema_version': 2, 'valid': True, 'running': False, 'sequence_ok': True,
                      'wait_timeout': False, 'busy_assertion_missing': False, 'pre_command_idle_failure': False,
                      'mapping_applied': True, 'pon_busy_seen': True, 'drf_busy_seen': True, 'pof_busy_seen': True,
                      'input_fnv1a': a['frame']['fnv1a'], 'cs1_dtm_fnv1a': a['cs1_dtm']['fnv1a'],
                      'cs2_dtm_fnv1a': a['cs2_dtm']['fnv1a'], 'failure_code': 0,
                      'spi_hz': 1000000, 'operation_id': 1}, 'driver')
    for key in ('failure_stage', 'timeout_stage', 'busy_missing_stage', 'pre_command_busy_stage'):
        if driver.get(key) not in ('', 'none'):
            raise RunnerError('driver failure stage present')
    stages = driver.get('busy_stage_samples', {})
    _require(stages, {'unreached_level_sentinel': 255}, 'BUSY schema')
    for name in ('pon', 'drf', 'pof'):
        stage = stages.get(name, {})
        _require(stage, {'pre_command_level': 1, 'pre_command_idle_ok': True,
                         'assertion_after_idle': True, 'wait_exit_level': 1}, name + ' BUSY')
        for key in ('gate_entry_level', 'wait_entry_level'):
            if type(stage.get(key)) is not int or stage[key] not in (0, 1):
                raise RunnerError('missing raw BUSY sample')
        for key in ('pre_command_wait_ms', 'wait_ms', 'assertion_latency_ms'):
            if type(stage.get(key)) is not int or not 0 <= stage[key] <= 60000:
                raise RunnerError('BUSY timing outside sealed gate')
    reset = stages.get('reset', {})
    if type(reset.get('wait_entry_level')) is not int or reset['wait_entry_level'] not in (0, 1) or type(reset.get('wait_exit_level')) is not int or reset['wait_exit_level'] != 1:
        raise RunnerError('reset BUSY completion missing')
    post = stages.get('post_psr', {})
    _require(post, {'pre_command_level': 1, 'pre_command_idle_ok': True, 'wait_exit_level': 1}, 'post-PSR BUSY')
    _require(driver.get('safe_finish', {}), {'busy_before_pins_low': 1,
              'busy_after_pins_low': 1, 'busy_after_5ms': 1,
              'final_gpio': {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}}, 'safe finish')
    _require(status, {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}, 'final GPIO')
    times = [value.get(key) for key in ('job_queued_at_ms', 'job_started_at_ms', 'job_finished_at_ms')]
    if any(type(t) is not int or t < 0 for t in times) or times != sorted(times):
        raise RunnerError('terminal chronology differs')


def run_source(package: Path, evidence_path: Path, diagnostic_path: Path, output: Path, base_url: str,
               ordinal: int = 1, transport: Callable | None = None) -> dict:
    if type(ordinal) is not int or ordinal != 1:
        raise RunnerError('this release permits only SOURCE ordinal 1; ordinals 2/3 rejected')
    ctx = validate_package(package)
    evidence = validate_evidence(ctx, evidence_path, base_url, phase='on')
    _diagnostic(ctx, evidence, diagnostic_path, base_url)
    session = Session(ctx, evidence, output, base_url, transport)
    session.four_get(1)
    claim = claim_path(ctx)
    claim.parent.mkdir(parents=True, exist_ok=True)
    write_new(claim, seal({'kind': 'mf1750-lh1-lh4-source-consumption-claim-v1',
                          'state': 'permanently_consumed_before_first_arm',
                          'source_campaign_id': ctx['source']['campaign_id'], 'source_action_id': ctx['source']['action_id'],
                          'contract_id': ctx['contract']['contract_id'], 'action_id': ctx['contract']['actions'][0]['action_id'],
                          'boot_nonce': evidence['boot_nonce'], 'run_id': evidence['run_id'],
                          'firmware': ctx['firmware'], 'elf': ctx['elf'], 'output': str(session.output),
                          'evidence': file_binding(evidence_path), 'diagnostic': file_binding(diagnostic_path),
                          'recorded_at': datetime.now(timezone.utc).isoformat(), 'write_contract': 'O_EXCL'}))
    try:
        armed = session.request('POST', 'arm', 201, mutation_headers(ctx, evidence))
        _identity(ctx, armed, evidence, latched=True)
        _require(armed, expected_action(ctx), 'ARM action')
        _require(armed, {'accepted': True, 'armed': True, 'phase': 1, 'phase_name': 'ARMED',
                         'boot_nonce': evidence['boot_nonce'], 'not_hardware_authorization': True}, 'ARM')
        if not NONCE.fullmatch(armed.get('arm_nonce', '')):
            raise RunnerError('invalid ARM nonce')
        executed = session.request('POST', 'execute', 202, mutation_headers(ctx, evidence, arm_nonce=armed['arm_nonce']))
        _identity(ctx, executed, evidence, latched=True)
        _require(executed, expected_action(ctx), 'EXECUTE action')
        _require(executed, {'accepted': True, 'job_id': 1, 'phase': 2, 'phase_name': 'CONSUMED',
                            'execute_consumed': True, 'boot_nonce': evidence['boot_nonce'],
                            'no_retry': True, 'no_recovery': True}, 'EXECUTE')
        time.sleep(POLL_INITIAL_DELAY_SECONDS)
        for _ in range(MAX_STATUS_POLLS):
            status = session.request('GET', 'status', 200)
            _identity(ctx, status, evidence, latched=True)
            _require(status, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-status',
                              'boot_nonce': evidence['boot_nonce'], 'arm_request_count': 1,
                              'execute_request_count': 1, 'cursor_valid': True,
                              'campaign_boot_matches_current': True,
                              'persisted_campaign_boot_nonce': evidence['boot_nonce']}, 'poll status')
            if type(status.get('total_driver_call_count')) is not int or status['total_driver_call_count'] not in (0, 1):
                raise RunnerError('driver count invalid during poll')
            if status.get('state') == 'fault_locked' or status.get('phase') == 3:
                raise RunnerError('FAULT; permanent claim retained, no retry')
            if status.get('phase') == 0 and status.get('next_ordinal') == 2:
                terminal = session.request('GET', 'report', 200)
                validate_terminal(ctx, terminal, status, evidence)
                result = seal({'kind': 'mf1750-lh1-lh4-source-result-v1', 'outcome': 'complete_pass',
                               'recorded_at': datetime.now(timezone.utc).isoformat(), 'ordinal': 1,
                               'contract_id': ctx['contract']['contract_id'], 'source_action_id': ctx['source']['action_id'],
                               'claim': file_binding(claim), 'network': session.counts,
                               'driver_calls': 1, 'visible_refreshes': 1, 'qualified_count': 0,
                               'next_action_authorized': False, 'stop_and_review_required': True,
                               'terminal': terminal, 'status': status})
                write_new(session.output / 'result.json', result)
                return result
            if status.get('phase') not in (1, 2) or status.get('next_ordinal') != 1:
                raise RunnerError('unexpected in-flight cursor')
            time.sleep(POLL_INTERVAL_SECONDS)
        raise RunnerError('terminal deadline exceeded; no retry')
    except Exception as exc:
        write_new(session.output / 'STOP.json', seal({'outcome': 'STOP_UNCERTAIN_OR_FAILED',
                    'error': str(exc), 'claim': file_binding(claim), 'network': session.counts,
                    'no_retry': True, 'no_recovery': True, 'next_action_authorized': False}))
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'evidence-template', 'diagnose', 'run-source'))
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--diagnostic', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--base-url')
    parser.add_argument('--ordinal', type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.ordinal != 1:
            raise RunnerError('only ordinal 1 is released')
        if args.command in ('validate', 'evidence-template'):
            ctx = validate_package(args.package)
            _source_evidence(ctx)
            value = evidence_template(ctx) if args.command == 'evidence-template' else {
                'result': 'PASS', 'contract_id': ctx['contract']['contract_id'],
                'device_requests': 0, 'live_ready': False,
                'running_elf_device_self_report': False,
                'elf_admission_basis': 'sealed BIN/ELF plus exact app-only write/verify evidence and post-flash boot binding'}
        else:
            if not all((args.evidence, args.output, args.base_url)):
                raise RunnerError('evidence, output, and base-url are required')
            if args.command == 'diagnose':
                value = diagnose(args.package, args.evidence, args.output, args.base_url)
            else:
                if not args.diagnostic:
                    raise RunnerError('sealed J2-OFF diagnostic required')
                value = run_source(args.package, args.evidence, args.diagnostic, args.output, args.base_url, args.ordinal)
    except (RunnerError, OSError, ValueError, KeyError, TypeError) as exc:
        print('LH1 stopped: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
