import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app

def run_tests():
    print("=" * 60)
    print("  SMART TKA SCANNER v1.1 COMPREHENSIVE VERIFICATION")
    print("=" * 60)
    
    client = app.test_client()
    
    # 1. Signatures & Stamp Master Data
    print("\n[TEST 1] Signatures & Stamp Master Endpoint (/api/signatures)")
    res = client.get('/api/signatures')
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.get_json()
    assert data.get("success"), "Expected success=True"
    
    prof = data.get("school_profile", {})
    stamp = data.get("stamp", {})
    officers = data.get("officers", [])
    
    print(f"  [+] School: {prof.get('nama_sekolah')} (NPSN: {prof.get('npsn')})")
    print(f"  [+] Headmaster: {prof.get('nama_kepsek')}")
    print(f"  [+] Stamp Status: {'ACTIVE' if stamp.get('has_file') else 'MISSING'} (file: {stamp.get('file_name')})")
    print(f"  [+] Total Officers: {len(officers)}")
    
    assert stamp.get("has_file"), "Stamp must be marked has_file=True"
    assert len(officers) >= 8, f"Expected at least 8 officers, got {len(officers)}"
    
    for off in officers:
        has_sig = off.get("has_signature")
        fn = off.get("signature_filename")
        print(f"      - {off.get('name')} [{off.get('role')}]: {'HAS SIG' if has_sig else 'NO SIG'} ({fn})")
        assert has_sig, f"Officer {off.get('name')} missing signature!"

    # 2. Image Serving & Previews
    print("\n[TEST 2] Image Serving Endpoint (/preview/...)")
    stamp_res = client.get(f"/preview/stamps/{stamp.get('file_name')}")
    assert stamp_res.status_code == 200, f"Failed serving stamp: {stamp_res.status_code}"
    print(f"  [+] Stamp image served OK ({len(stamp_res.data)} bytes)")
    
    for off in officers:
        fn = off.get("signature_filename")
        sig_res = client.get(f"/preview/signatures/{fn}")
        assert sig_res.status_code == 200, f"Failed serving signature {fn}: {sig_res.status_code}"
        print(f"  [+] Signature served OK: {fn} ({len(sig_res.data)} bytes)")

    # 3. Dynamic Assignments
    print("\n[TEST 3] Dynamic Assignments Matrix (/api/assignments)")
    res_ass = client.get('/api/assignments')
    assert res_ass.status_code == 200
    d_ass = res_ass.get_json()
    assignments = d_ass.get("assignments", [])
    print(f"  [+] Loaded {len(assignments)} assignment slots")
    assert len(assignments) > 0, "Assignments matrix must not be empty"
    sample = assignments[0]
    print(f"  [+] Sample slot 0: G{sample.get('gelombang')} H{sample.get('hari')} S{sample.get('sesi')} {sample.get('nm_ruang')} - {sample.get('tanggal')}")
    print(f"      Proktor: {sample.get('proktor_name')} (Sig: {sample.get('proktor_has_sig')})")
    print(f"      Pengawas: {sample.get('pengawas_name')} (Sig: {sample.get('pengawas_has_sig')})")

    # 4. Document Generation (BAP & DH)
    print("\n[TEST 4] Official Stamped Document Generation (/api/document/generate)")
    gen_bap = client.post('/api/document/generate', json={
        'doc_type': 'BAP', 'gelombang': 1, 'hari': 1, 'sesi': 1, 'lab_num': 1
    })
    assert gen_bap.status_code == 200, f"BAP generate failed: {gen_bap.data}"
    bap_data = gen_bap.get_json()
    print(f"  [+] BAP Generated: {bap_data.get('filename')} -> {bap_data.get('preview_url')}")

    # 5. Native Edge Vector PDF Rendering
    print("\n[TEST 5] Native Vector PDF Rendering (/document/pdf/...)")
    pdf_bap = client.get('/document/pdf/BAP/1/1/1/1')
    assert pdf_bap.status_code == 200, f"PDF BAP failed: {pdf_bap.status_code}"
    print(f"  [+] Vector PDF BAP: {len(pdf_bap.data)} bytes (ContentType: {pdf_bap.content_type})")
    
    pdf_dh = client.get('/document/pdf/DH/1/1/1/1')
    assert pdf_dh.status_code == 200, f"PDF DH failed: {pdf_dh.status_code}"
    print(f"  [+] Vector PDF DH: {len(pdf_dh.data)} bytes (ContentType: {pdf_dh.content_type})")

    # 6. Direct Print Endpoint
    print("\n[TEST 6] Direct Print Endpoint (/document/print/...)")
    prt_bap = client.get('/document/print/BAP/1/1/1/1?autoprint=1')
    assert prt_bap.status_code == 200, f"Print BAP failed: {prt_bap.status_code}"
    assert "window.print()" in prt_bap.get_data(as_text=True), "Autoprint script missing from print template"
    print(f"  [+] Direct Print BAP HTML rendered with autoprint script ({len(prt_bap.data)} bytes)")

    print("\n" + "=" * 60)
    print("  ALL 6 TESTS PASSED SUCCESSFULLY! (100% GREEN)")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
