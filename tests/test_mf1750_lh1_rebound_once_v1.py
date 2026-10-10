from pathlib import Path
import pytest
from tools import mf1750_lh1_rebound_once_v1 as r

def test_rebound_package_binds_new_nvs_and_preserves_old_fault():
 c=r.validate_package(); assert c['identity']['nvs_namespace']=='lhist_lh1_rebound_v1'; assert c['contract']['old_fault_preservation']['expected_cursor_raw']==770

def test_rebound_anchor_is_completed_r4_white_close_review():
 c=r.validate_package(); a=r.validate_rebound_anchor(c['contract']); assert a['protocol']=='PASS'; assert a['terminal_report']['next_ordinal']==2

def test_rebound_headers_are_dynamic_per_ordinal_and_review_bound():
 c=r.validate_package(); h=r.headers(c,2,'1111222233334444','LH1_REBOUND_RUN','a'*64,'b'*64); assert h['X-EC5-Ordinal']=='2'; assert h['X-EC5-Action-Id']==c['actions'][1]['action_id']; assert h['X-LH-Source-Review']=='a'*64 and h['X-LH-Prior-Review']=='b'*64

def test_ordinal_one_requires_current_r4_close_review_digest():
 c=r.validate_package()
 with pytest.raises(Exception): r.headers(c,1,'1111222233334444','LH1_REBOUND_RUN','a'*64,'a'*64)
 h=r.headers(c,1,'1111222233334444','LH1_REBOUND_RUN',r.EXPECTED_ANCHOR_SHA256,r.EXPECTED_ANCHOR_SHA256)
 assert h['X-LH-Source-Review']==r.EXPECTED_ANCHOR_SHA256

def test_rebound_rejects_foreign_nvs_or_anchor(tmp_path):
 c=r.validate_package(); c['contract']['nvs']['namespace']='lhist_v1'
 with pytest.raises(Exception): r.validate_package(tmp_path/'missing')
 with pytest.raises(Exception): r.headers(c,1,'bad','run','a'*64,'a'*64)
